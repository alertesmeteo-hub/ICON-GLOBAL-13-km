import json,sys,unittest,tempfile
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import update_icon_global as m
from icon_global_maps import MAP_STEPS, PRODUCTS, REGIONS

class ContractTests(unittest.TestCase):
 def test_map_contract(self):
  self.assertEqual(MAP_STEPS,(24,48,72,120,180))
  self.assertEqual(set(PRODUCTS),{'temperature','precipitation','rafales','nuages','vent'})
  self.assertEqual(set(REGIONS),{'france','europe'})
 def test_exact_arome_columns(self):
  ref=json.loads((ROOT/'tests/reference-schema.json').read_text())
  self.assertEqual(list(m.schema.VALUE_COLUMNS),ref['values'])
  self.assertEqual(len(ref['values']),33)
 def test_hourly_interpolation_conserves_cumuls_and_gust_periods(self):
  steps=[0,1,4]
  raw={'t_2m':np.array([[270.],[271.],[277.]]),'tot_prec':np.array([[0.],[1.],[7.]]),'snow_gsp':np.array([[0.],[0.],[3.]]),'vmax_10m':np.array([[0.],[4.],[10.]])}
  out,periods=m.hourly(raw,[0,0,1],steps)
  np.testing.assert_array_equal(out['t_2m'][:,0],[270,271,273,275,277])
  np.testing.assert_array_equal(np.diff(out['tot_prec'][:,0]),[1,2,2,2])
  self.assertEqual(periods,[None,1,3,3,3])
  self.assertTrue(np.isnan(out['vmax_10m'][0,0]))
  np.testing.assert_array_equal(out['vmax_10m'][1:,0],[4,10,10,10])
  raw['tot_prec'][2]=0
  with self.assertRaises(ValueError):m.hourly(raw,[0,0,1],steps)
 def test_native_gust_gaps_remain_null(self):
  raw={'t_2m':np.array([[270.],[271.],[277.]]),'vmax_10m':np.array([[0.],[4.],[10.]])}
  out,periods=m.hourly(raw,[0,0,3],[0,1,4])
  self.assertEqual(periods,[None,1,None,None,1])
  self.assertTrue(np.isnan(out['vmax_10m'][2:4]).all())
 def test_department_local_ids(self):
  path=ROOT/'config/communes-france.json'
  communes=json.loads(path.read_text(encoding='utf-8-sig'))['communes']
  lat=np.array([c[5] for c in communes]);lon=np.array([c[6] for c in communes])
  catalog=m.make_catalog(path,lat,lon)
  self.assertEqual(len(catalog.departments),96)
  for d in catalog.departments.values():
   for c in d.communes:
    point=d.points[c[6]]
    self.assertAlmostEqual(point[1],c[4],places=4)
    self.assertAlmostEqual(point[2],c[5],places=4)
   self.assertEqual(len(d.points),len(set(c[6] for c in d.communes)))
 def test_transform_and_nulls(self):
  vals={'t_2m':273.15,'td_2m':271.15,'relhum_2m':90,'u_10m':3,'v_10m':4,'vmax_10m':10,'tot_prec':5,'snow_gsp':2,'snow_con':1,'cape_ml':600,'clct':20,'clcl':10,'clcm':0,'clch':0,'ps':100000,'pmsl':101300}
  raw={k:np.array([v]) for k,v in vals.items()}
  d,_=m.transform(raw,np.array([100.]),{'rain_total':np.array([2.]),'snow_total':np.array([1.])},2)
  row=m.schema.compact_rows(d,np.array([0]))[0];v=dict(zip(m.schema.VALUE_COLUMNS,row))
  self.assertEqual(v['precipitation_mm'],3);self.assertEqual(v['snowfall_mm'],2)
  self.assertEqual(v['wind_speed_kmh'],18);self.assertEqual(v['wind_gust_kmh'],36)
  self.assertEqual(v['pressure_hpa'],1013);self.assertEqual(v['cloud_cover_pct'],20)
  self.assertEqual(v['condition_code'],7)
  for key in m.UNAVAILABLE:self.assertIsNone(v[key])
  json.dumps(row,allow_nan=False)
 def test_run_selection_requires_all_fields_and_steps(self):
  listings={v:{('2026090800',s):'url' for s in ([0] if v in m.STATIC else m.STEPS)} for v in m.FIELDS}
  listings['t_2m']['2026090812',0]='url'
  self.assertEqual(m.select_run(listings),'2026090800')
  del listings['snow_con']['2026090800',180]
  with self.assertRaises(ValueError):m.select_run(listings)
 def test_spherical_nearest_neighbour(self):
  # Longitude wrap must select 179.9 rather than an apparently closer planar coordinate.
  tree=m.cKDTree(m.xyz(np.array([0.,0.]),np.array([179.9,170.])))
  _,idx=tree.query(m.xyz(np.array([0.]),np.array([-179.9])))
  self.assertEqual(idx[0],0)
 def test_time_units(self):
  self.assertEqual(m.step_hours('180m'),3)
  with self.assertRaises(ValueError):m.step_hours('90m')

if __name__=='__main__':unittest.main()
