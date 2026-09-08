=== ICON-GLOBAL 13 km ===
Contributors: alertesmeteo-hub
Requires at least: 5.8
Requires PHP: 7.4
Stable tag: 1.0.0
License: GPLv2 or later

Prévisions communales ICON-GLOBAL 13 km de DWD.

== Installation ==
Téléverser le ZIP dans Extensions, puis activer.
Dans un bloc texte Avada : [icon_global_meteo]
Exemple Paris : [icon_global_meteo code="75056" departement="75" ville="Paris" heures="180"]

== Données ==
Les JSON départementaux sont publiés par GitHub Actions dans la branche data du dépôt alertesmeteo-hub/ICON-GLOBAL-13-km.
Schéma v3 partagé : communes et point_id, points de grille, échéances et 33 valeurs par point.
Les valeurs indisponibles sont affichées par un tiret. Les risques sont indicatifs, pas des vigilances officielles.
La neige fraîche en cm et son cumul sont estimés, sans fonte ni tassement.
Cette version comporte des tableaux et graphiques ; les cartes ne sont pas incluses.

== Services externes ==
Données : raw.githubusercontent.com/alertesmeteo-hub/ICON-GLOBAL-13-km/data
Recherche de communes : geo.api.gouv.fr (la recherche saisie est transmise à cette API publique).
Sources : DWD, CC BY 4.0 ; API Découpage administratif.
