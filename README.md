# ICON-GLOBAL 13 km — Alertes Météo

Prévisions du DWD sur la grille native mondiale ICON 13 km, extraites pour les 34 746 communes de France métropolitaine et de Corse. **Même contrat JSON départemental v3 que le module AROME : 33 colonnes dans le même ordre.**

## Lancer le run

Dans **Actions → Mise à jour ICON-GLOBAL 13 km → Run workflow**, choisir `main`, puis lancer. Cocher `force` uniquement pour reconstruire un calcul déjà publié. Le workflow vérifie également les nouveaux calculs chaque heure, avec les délais éventuels du planificateur GitHub.

Le dernier calcul complet à +180 h parmi les cycles 00, 06, 12 et 18 UTC est sélectionné. Tous les champs doivent appartenir au même calcul et à la grille native DWD numéro 26, de 2 949 120 cellules. Une erreur ou une publication amont incomplète conserve la dernière branche `data` valide. Aucune clé API n'est nécessaire.

## WordPress / Avada

Télécharger le ZIP WordPress dans [Releases](https://github.com/alertesmeteo-hub/ICON-GLOBAL-13-km/releases). Dans WordPress : **Extensions → Ajouter → Téléverser → Activer**. Le module v2 produit 50 cartes France/Europe et 50 grilles de valeurs interactives. Placer ce shortcode dans un bloc texte Avada :

```text
[icon_global_meteo]
[icon_global_meteo code="75056" departement="75" ville="Paris" heures="180"]
```

Recherche de commune, prévisions générales, orages, neige et graphiques. Les préfixes sont distincts des modules AROME, AROME-IFS et ICON-EU, pour permettre leur coexistence. Cette version ne comprend pas les cartes.

## Données départementales au format AROME

La branche [`data`](https://github.com/alertesmeteo-hub/ICON-GLOBAL-13-km/tree/data) contient `index.json` et `departements/01.json`, etc. :

- `schema_version: 3` et les mêmes clés départementales qu'AROME.
- `points` : `[model_index, latitude, longitude, altitude_m]`.
- `communes` : `[code_insee, name, postal_codes, population, latitude, longitude, point_id]`.
- `forecast` : `[[date_iso, [valeurs_point_0, valeurs_point_1, ...]], ...]`.
- `columns.values` : les 33 colonnes de la [référence AROME](tests/reference-schema.json), inchangées et dans le même ordre.

Le `point_id` est local au département. Plusieurs communes partagent une cellule ICON. La recherche utilise la distance sur la sphère, sans rééchantillonnage spatial vers une grille plus fine. Les points et leur altitude viennent directement des fichiers DWD `CLAT`, `CLON` et `HSURF`.

```javascript
const commune = department.communes.find(c => c[0] === '75056');
const values = department.forecast[0][1][commune[6]];
const temperature = values[department.columns.values.indexOf('temperature_c')];
```

## Échéances, unités et champs indisponibles

181 échéances de +0 à +180 h. Les sorties natives sont horaires jusqu'à +78 h, puis espacées de trois heures. Après +78 h, les champs instantanés sont interpolés linéairement et les cumuls de pluie et neige répartis uniformément sur les heures de l'intervalle. Cette interpolation ne constitue pas une sortie horaire native. Les rafales ne sont affichées que sur les heures couvertes par leur intervalle GRIB ; les trous restent `null`. `index.diagnostics` décrit les échéances natives et les périodes de rafales.

Température en °C, vent et rafales en km/h, pression en hPa, pluie et neige en équivalent eau en mm. Neige totale = composantes convective et de grande échelle DWD. Les centimètres de neige fraîche sont estimés selon la convention du module AROME. `snow_depth_cm` cumule cette estimation sans fonte ni tassement : ce n'est pas une hauteur de neige observée au sol.

CAPE de couche mélangée directement fournie par ICON ; le risque orage est un diagnostic indicatif basé sur CAPE et rafales, pas une vigilance officielle. Réflectivité, visibilité, graupel, score foudre, risque grêle, précipitations convectives et type d'orage restent `null` dans cette version. Aucune colonne n'est supprimée ou décalée.

## Sources et tests

Données : [DWD Open Data ICON](https://opendata.dwd.de/weather/nwp/icon/grib/), attribution Deutscher Wetterdienst. [Documentation officielle ICON](https://www.dwd.de/SharedDocs/downloads/DE/modelldokumentationen/nwv/icon/icon_dbbeschr_aktuell.pdf). Communes : API Découpage administratif. Schéma et transformations communes : `alertesmeteo-hub/arome-meteofrance`, commit `fcace746879935fa8c5087eac85ab5cbb11abfdf`.

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -v
python scripts/update_icon_global.py --force
```

Les tests portent sur les colonnes AROME, les conversions, les cumuls et les rafales, les distances sphériques et la sélection de calculs complets. Avant publication, les 96 JSON sont vérifiés : chaque commune a un `point_id` valide et chaque échéance a exactement une ligne de 33 valeurs par point.
