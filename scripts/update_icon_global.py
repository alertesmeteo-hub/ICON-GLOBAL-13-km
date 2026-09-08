#!/usr/bin/env python3
"""DWD ICON native global 13 km -> shared AROME department contract v3."""
from __future__ import annotations
import argparse,bz2,concurrent.futures,json,re,tempfile,threading,time,urllib.request,urllib.error
from collections import defaultdict
from datetime import datetime,timedelta,timezone
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
import schema_v3 as schema

BASE='https://opendata.dwd.de/weather/nwp/icon/grib/'
VERSION='1.0.0'
STEPS=list(range(79))+list(range(81,181,3))
GRID_UUID='a27b8de618c411e4820ab5b098c6a5c0'
GRID_SIZE=2949120
LOCK=threading.Lock()
# Explicit field identities, level and units checked on official DWD samples.
FIELDS={
 't_2m':('2t','K','heightAboveGround',2),
 'td_2m':('2d','K','heightAboveGround',2),
 'relhum_2m':('2r','%','heightAboveGround',2),
 'u_10m':('10u','m s**-1','heightAboveGround',10),
 'v_10m':('10v','m s**-1','heightAboveGround',10),
 'vmax_10m':('max_i10fg','m s**-1','heightAboveGround',10),
 'tot_prec':('tp','kg m**-2','surface',0),
 'snow_gsp':('lsfwe','kg m**-2','surface',0),
 'snow_con':('csfwe','kg m**-2','surface',0),
 'cape_ml':('CAPE_ML','J kg-1','unknown',0),
 'clct':('CLCT','%','surface',0),
 'clcl':('CLCL','%','unknown',800),
 'clcm':('CLCM','%','isobaricLayer',400),
 'clch':('CLCH','%','isobaricLayer',0),
 'ps':('sp','Pa','surface',0),
 'pmsl':('prmsl','Pa','meanSea',0),
 'clat':('tlat','Degree N','surface',0),
 'clon':('tlon','Degree E','surface',0),
 'hsurf':('HSURF','m','unknown',0),
}
STATIC=('clat','clon','hsurf')
VARIABLES=tuple(k for k in FIELDS if k not in STATIC)
UNAVAILABLE=['visibility_km','reflectivity_dbz','graupel_mm','lightning_score','hail_risk_code','convective_precipitation_mm','storm_type_code']

def download(url):
 for attempt in range(4):
  try:
   with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'AlertesMeteo-ICON-GLOBAL/1.0'}),timeout=90) as r:return r.read()
  except urllib.error.HTTPError as e:
   if e.code==404:raise
   if attempt==3:raise
   time.sleep(2**attempt)
  except Exception:
   if attempt==3:raise
   time.sleep(2**attempt)

def available(hour,variable):
 url=f'{BASE}{hour:02d}/{variable}/'
 html=download(url).decode()
 if variable in STATIC:
  pattern=r'href="(icon_global_icosahedral_time-invariant_(\d{10})_'+variable.upper()+r'\.grib2\.bz2)"'
  return {(run,0):url+name for name,run in re.findall(pattern,html)}
 pattern=r'href="(icon_global_icosahedral_single-level_(\d{10})_(\d{3})_'+variable.upper()+r'\.grib2\.bz2)"'
 return {(run,int(step)):url+name for name,run,step in re.findall(pattern,html)}

def select_run(listings):
 for run in sorted({r for r,_ in listings['t_2m']},reverse=True):
  if all(all((run,s) in listings[v] for s in ([0] if v in STATIC else STEPS[1:] if v=='vmax_10m' else STEPS)) for v in FIELDS):return run
 raise ValueError('Aucun calcul ICON-GLOBAL complet à +180 h : publication précédente conservée.')

def step_hours(value):
 m=re.fullmatch(r'(\d+(?:\.\d+)?)([smhd]?)',str(value).lower())
 if not m:raise ValueError('Unité de temps GRIB inconnue')
 h=float(m[1])*{'':1,'s':1/3600,'m':1/60,'h':1,'d':24}[m[2]]
 if not h.is_integer():raise ValueError('Échéance non horaire')
 return int(h)

def decode(payload,run,step,variable,indices=None):
 from eccodes import codes_new_from_message,codes_get,codes_get_values,codes_get_double_elements,codes_release
 message=bz2.decompress(payload)
 if message[:4]!=b'GRIB' or message[7]!=2 or int.from_bytes(message[8:16],'big')!=len(message) or message[-4:]!=b'7777':raise ValueError('Message GRIB2 invalide')
 # ecCodes definitions are initialized lazily and are not safe to initialize concurrently.
 with LOCK:
  g=codes_new_from_message(message)
  try:
   expected=FIELDS[variable]
   actual=tuple(codes_get(g,k) for k in ('shortName','units','typeOfLevel','level'))
   if actual!=expected:raise ValueError(f'Champ {variable} inattendu : {actual}')
   if codes_get(g,'gridType')!='unstructured_grid' or codes_get(g,'numberOfDataPoints')!=GRID_SIZE or codes_get(g,'uuidOfHGrid')!=GRID_UUID:raise ValueError('Grille ICON-GLOBAL différente')
   actual_run=f"{int(codes_get(g,'dataDate')):08d}{int(codes_get(g,'dataTime'))//100:02d}"
   if actual_run!=run or step_hours(codes_get(g,'endStep'))!=step:raise ValueError('Mélange de calculs ou échéances')
   start=step_hours(codes_get(g,'startStep'))
   if variable in ('tot_prec','snow_gsp','snow_con') and start!=0:raise ValueError('Cumul non initialisé au début du calcul')
   if variable=='vmax_10m' and step>0 and not 0<=start<step:raise ValueError('Période de rafale invalide')
   values=np.asarray(codes_get_values(g) if indices is None else codes_get_double_elements(g,'values',indices),dtype=float)
   missing=float(codes_get(g,'missingValue'))
   if np.any(~np.isfinite(values)|(np.abs(values)>1e20)|np.isclose(values,missing,rtol=0,atol=1e-9)):raise ValueError(f'Valeurs absentes dans {variable}')
   return values,start
  finally:codes_release(g)

def xyz(lat,lon):
 lat,lon=np.deg2rad(lat),np.deg2rad(lon)
 return np.column_stack((np.cos(lat)*np.cos(lon),np.cos(lat)*np.sin(lon),np.sin(lat)))

def make_catalog(path,lat,lon):
 payload=json.loads(Path(path).read_text(encoding='utf-8-sig'));communes=payload['communes']
 if len(communes)<34000 or len({c[0] for c in communes})!=len(communes):raise ValueError('Catalogue communal incomplet ou dupliqué')
 coords=np.array([[c[5],c[6]] for c in communes]);lon=(lon+180)%360-180
 # A bounding rectangle with a two-degree margin keeps every possible nearest cell.
 candidates=np.flatnonzero((lat>=coords[:,0].min()-2)&(lat<=coords[:,0].max()+2)&(lon>=coords[:,1].min()-2)&(lon<=coords[:,1].max()+2))
 tree=cKDTree(xyz(lat[candidates],lon[candidates]))
 distance,nearest=tree.query(xyz(coords[:,0],coords[:,1]))
 if np.max(distance)*6371>20:raise ValueError('Commune trop éloignée du point ICON sélectionné')
 model=candidates[nearest];indexes,inverse=np.unique(model,return_inverse=True)
 by_dept=defaultdict(list)
 for c,gid in zip(communes,inverse):by_dept[str(c[2]).upper()].append((c,int(gid)))
 departments={}
 for code,entries in sorted(by_dept.items()):
  global_ids=sorted({g for _,g in entries});local={g:i for i,g in enumerate(global_ids)}
  points=[[int(indexes[g]),round(float(lat[indexes[g]]),5),round(float(lon[indexes[g]]),5)] for g in global_ids]
  rows=[[str(c[0]),str(c[1]),list(c[3]),int(c[4]),float(c[5]),float(c[6]),local[g]] for c,g in entries]
  departments[code]=schema.DepartmentData(code,np.array(global_ids),points,rows)
 if len(departments)!=96:raise ValueError('Couverture départementale incomplète')
 return schema.NationalCatalog(str(payload.get('catalog_version','1'))+'-icon-global-0026',indexes.tolist(),lat[indexes],lon[indexes],['']*len(indexes),departments,len(communes))

def hourly(raw,starts,steps=STEPS):
 hours=np.arange(steps[-1]+1);out={}
 for variable,array in raw.items():
  if variable=='vmax_10m':continue
  if variable in ('tot_prec','snow_gsp','snow_con') and np.any(np.diff(array,axis=0)<-.05):raise ValueError('Cumul décroissant')
  out[variable]=np.stack([np.interp(hours,steps,row) for row in array.T],axis=1)
 gust=np.full_like(out['t_2m'],np.nan);periods=[None]*len(hours)
 for i,end in enumerate(steps):
  if end==0:continue
  start=starts[i]
  # Only fill the actual forecast period; gaps remain unavailable, never invented.
  first=max(start+1,steps[i-1]+1)
  gust[first:end+1]=raw['vmax_10m'][i]
  periods[first:end+1]=[end-start]*max(0,end+1-first)
 out['vmax_10m']=gust
 return out,periods

def transform(raw,altitude,previous,lead):
 mapping={'t_2m':'temperature_k','td_2m':'dewpoint_k','relhum_2m':'humidity_pct','u_10m':'wind_u_ms','v_10m':'wind_v_ms','vmax_10m':'gust_speed_ms','tot_prec':'precipitation_total_mm','clcl':'cloud_low_pct','clcm':'cloud_mid_pct','clch':'cloud_high_pct','ps':'surface_pressure_pa','cape_ml':'cape_jkg'}
 values={target:raw[source] for source,target in mapping.items()}
 values['snow_total_mm']=raw['snow_gsp']+raw['snow_con']
 data,state=schema.transform_step(values,altitude,previous,lead)
 data['dewpoint_c']=schema.rounded(raw['td_2m']-273.15,1)
 data['lcl_m']=schema.rounded(np.clip(125*(raw['t_2m']-raw['td_2m']),0,5000),0)
 data['pressure_hpa']=schema.rounded(raw['pmsl']/100,0)
 data['cloud_cover_pct']=schema.rounded(np.clip(raw['clct'],0,100),0)
 condition=data['condition_code'].copy();cloud=raw['clct']
 sky=np.select([cloud<=20,cloud<=55,cloud<=85],[1,2,3],default=4)
 condition[condition<=4]=sky[condition<=4]
 data['condition_code']=condition
 for name in UNAVAILABLE:data[name]=np.full(altitude.shape,np.nan)
 return data,state

def validate_product(root):
 root=Path(root);ref=json.loads((Path(__file__).resolve().parents[1]/'tests/reference-schema.json').read_text())
 index=json.loads((root/'index.json').read_text());count=0;total_rows=0
 files=list((root/'departements').glob('*.json'))
 assert len(files)==len(index['departments'])==96
 for path in files:
  d=json.loads(path.read_text(),parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
  assert d['schema_version']==3 and d['status']=='ok' and d['department']==path.stem
  assert d['columns']=={k:ref[k] for k in ('points','communes','values')}
  assert all(len(p)==4 for p in d['points'])
  assert all(len(c)==7 and type(c[6])==int and 0<=c[6]<len(d['points']) for c in d['communes'])
  assert len(d['forecast'])==181
  for h,(date,rows) in enumerate(d['forecast']):
   assert datetime.fromisoformat(date.replace('Z','+00:00'))==datetime.fromisoformat(index['model']['run_time'].replace('Z','+00:00'))+timedelta(hours=h)
   assert len(rows)==len(d['points']) and all(len(r)==33 and all(v is None or type(v) in (int,float) for v in r) for r in rows)
   total_rows+=len(rows)
  assert len(d['communes'])==index['departments'][path.stem]['communes']
  count+=len(d['communes'])
 assert count==index['coverage']['communes'] and count>=34000
 print(f'Contrat v3 vérifié : {count} communes, 96 départements, {total_rows} lignes, 33 colonnes.',flush=True)

def build(catalog_path,output,repository,force=False):
 listings={v:{} for v in FIELDS}
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
  jobs={pool.submit(available,h,v):v for h in (0,6,12,18) for v in FIELDS}
  for job in concurrent.futures.as_completed(jobs):listings[jobs[job]].update(job.result())
 run=select_run(listings);run_date=datetime.strptime(run,'%Y%m%d%H').replace(tzinfo=timezone.utc)
 if datetime.now(timezone.utc)-run_date>timedelta(hours=30):raise ValueError('Calcul ICON-GLOBAL trop ancien')
 try:current=json.loads(download(f'https://raw.githubusercontent.com/{repository}/data/index.json'))
 except urllib.error.HTTPError as e:
  if e.code!=404:raise
  current={}
 if not force and current.get('model',{}).get('run_time')==schema.iso_utc(run_date) and current['model'].get('pipeline_version')==VERSION:
  print('Calcul déjà publié.',flush=True);return
 print('Calcul ICON-GLOBAL sélectionné :',run,flush=True)
 lat,_=decode(download(listings['clat'][run,0]),run,0,'clat')
 lon,_=decode(download(listings['clon'][run,0]),run,0,'clon')
 catalog=make_catalog(catalog_path,lat,lon);del lat,lon
 altitude,_=decode(download(listings['hsurf'][run,0]),run,0,'hsurf',catalog.model_indexes)
 for d in catalog.departments.values():
  for p,g in zip(d.points,d.global_point_ids):p.append(schema.json_number(altitude[g],True))
 raw={v:np.full((len(STEPS),len(catalog.model_indexes)),np.nan) for v in VARIABLES};starts=[0]*len(STEPS)
 def fetch(v,i,s):return v,i,decode(download(listings[v][run,s]),run,s,v,catalog.model_indexes)
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
  jobs=[pool.submit(fetch,v,i,s) for i,s in enumerate(STEPS) for v in VARIABLES if not (v=='vmax_10m' and s==0)]
  try:
   for n,job in enumerate(concurrent.futures.as_completed(jobs),1):
    v,i,(values,start)=job.result();raw[v][i]=values
    if v=='vmax_10m':starts[i]=start
    if n%100==0:print(f'Champs téléchargés et validés : {n}/{len(jobs)}',flush=True)
  except Exception:
   for job in jobs:job.cancel()
   raise
 raw,periods=hourly(raw,starts)
 output=Path(output);output.mkdir(parents=True,exist_ok=True);generated=schema.iso_utc(datetime.now(timezone.utc));state={}
 with tempfile.TemporaryDirectory() as temp:
  temp=Path(temp);handles={code:(temp/f'{code}.ndjson').open('w',encoding='utf-8') for code in catalog.departments}
  try:
   for lead in range(181):
    data,state=transform({v:a[lead] for v,a in raw.items()},altitude,state,lead)
    for code,d in catalog.departments.items():
     json.dump([schema.iso_utc(run_date+timedelta(hours=lead)),schema.compact_rows(data,d.global_point_ids)],handles[code],ensure_ascii=False,separators=(',',':'),allow_nan=False);handles[code].write('\n')
  finally:
   for f in handles.values():f.close()
  department_index,total=schema.write_departments(output,temp,catalog,generated)
 index={'schema_version':3,'status':'ok','generated_at':generated,'model':{'name':'ICON-GLOBAL 13 km','provider':'DWD','dataset':'ICON global native icosahedral','domain':'Monde (extraction France métropolitaine et Corse)','resolution_km':13,'grid_uuid':GRID_UUID,'forecast_hours_requested':180,'run_time':schema.iso_utc(run_date),'pipeline_version':VERSION,'catalog_version':catalog.version,'storm_diagnostics':True,'snow_diagnostics':True,'source_url':BASE,'license':'CC BY 4.0 — DWD'},'coverage':{'label':'France métropolitaine et Corse','communes':catalog.commune_count,'departments':96},'condition_codes':schema.CONDITION_CODES,'diagnostics':{'unavailable':UNAVAILABLE,'native_steps_hours':STEPS,'hourly_interpolated_after':78,'gust_period_hours':periods,'note':'Au-delà de +78 h, champs instantanés interpolés linéairement ; cumuls de pluie et neige répartis uniformément sur trois heures ; rafales uniquement sur les heures couvertes par leur intervalle GRIB ; les heures manquantes restent null. Risques orage et neige indicatifs, pas des vigilances officielles. snow_depth_cm suit le cumul estimé de neige fraîche sans fonte ni tassement, pas une hauteur observée au sol. null signifie indisponible.'},'search':{'provider':'API Découpage administratif','endpoint':'https://geo.api.gouv.fr/communes'},'maps':{'status':'unavailable'},'departments':department_index,'total_department_bytes':total}
 (output/'index.json').write_text(json.dumps(index,ensure_ascii=False,separators=(',',':')),encoding='utf-8');validate_product(output)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--catalog',default='config/communes-france.json');p.add_argument('--output-dir',default='build/national');p.add_argument('--repository',default='alertesmeteo-hub/ICON-GLOBAL-13-km');p.add_argument('--force',action='store_true');a=p.parse_args()
 build(a.catalog,a.output_dir,a.repository,a.force)
