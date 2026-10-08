"""Cartes interactives ICON-GLOBAL, au format commun des dépôts AROME / ARPEGE / GFS / ECMWF.

Produit, dans `maps/` du dossier de sortie :

- `index.json` : run, emprise, couches (palette) et liste des échéances ;
- `values/<couche>/<lead>.hkv.gz` : grille de valeurs (en-tête CEV1, largeur, hauteur, min, max, puis uint16,
  65535 = manquant), lignes régulières en projection Mercator du nord au sud ;
- `<couche>/<lead>.webp` : image colorée de la couche (même grille).

Domaine : Europe de l'Ouest (38–57° N, 12° W–18° E), comme les autres modèles. Les valeurs ICON (grille
icosaédrique à 13 km) sont interpolées sur la grille régulière par les trois points natifs les plus proches.
"""
from __future__ import annotations

import gzip
import json
import struct
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.spatial import cKDTree

BOUNDS = {"south": 38.0, "west": -12.0, "north": 57.0, "east": 18.0}
WIDTH = 300  # 0,1° en longitude (ICON est à ~0,12°) : au-delà, les fichiers grossissent sans gain visible
PROBE_MAGIC = b"CEV1"
# Champs ICON nécessaires aux couches interactives (voir FIELDS dans update_icon_global.py).
VARIABLES = ("t_2m", "relhum_2m", "u_10m", "v_10m", "vmax_10m", "tot_prec", "pmsl", "clct")
# Grilles de valeurs publiées sans image (composantes du vent pour les traits animés).
VECTOR_RANGE = (-200.0, 200.0)
# Arrondi des valeurs avant encodage : la compression gzip y gagne beaucoup, l'affichage rien.
QUANTUM = {"temperature": 0.1, "humidite": 1.0, "vent": 1.0, "rafales": 1.0, "pluie_1h": 0.1, "pluie_cumul": 0.1, "pression": 0.1, "nebulosite": 1.0}


def _mercator(lat):
    return np.log(np.tan(np.pi / 4.0 + np.radians(np.clip(lat, -85.0, 85.0)) / 2.0))


def _inverse_mercator(y):
    return np.degrees(2.0 * np.arctan(np.exp(y)) - np.pi / 2.0)


def _xyz(lat, lon):
    lat, lon = np.deg2rad(lat), np.deg2rad(lon)
    return np.column_stack((np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)))


def grid_shape():
    height = int(round(WIDTH * float(_mercator(BOUNDS["north"]) - _mercator(BOUNDS["south"])) / np.radians(BOUNDS["east"] - BOUNDS["west"])))
    return WIDTH, height


def prepare_interactive(native_lat, native_lon):
    """Points natifs utiles (`candidates`, indices dans la grille ICON) et poids d'interpolation de la grille régulière."""
    native_lon = (np.asarray(native_lon) + 180) % 360 - 180
    native_lat = np.asarray(native_lat)
    width, height = grid_shape()
    lons = BOUNDS["west"] + (np.arange(width) + 0.5) / width * (BOUNDS["east"] - BOUNDS["west"])
    top, bottom = float(_mercator(BOUNDS["north"])), float(_mercator(BOUNDS["south"]))
    lats = _inverse_mercator(top - (np.arange(height) + 0.5) / height * (top - bottom))
    lon_grid, lat_grid = np.meshgrid(lons, lats)
    candidates = np.flatnonzero(
        (native_lat >= BOUNDS["south"] - 1) & (native_lat <= BOUNDS["north"] + 1) & (native_lon >= BOUNDS["west"] - 1) & (native_lon <= BOUNDS["east"] + 1)
    )
    tree = cKDTree(_xyz(native_lat[candidates], native_lon[candidates]))
    distance, nearest = tree.query(_xyz(lat_grid.ravel(), lon_grid.ravel()), k=3)
    weights = 1.0 / np.maximum(distance, 1e-5) ** 2
    weights /= weights.sum(axis=1, keepdims=True)
    return {"candidates": candidates, "nn": nearest.astype(np.int32), "w": weights.astype(np.float32), "width": width, "height": height}


def _write_probe(values, minimum, maximum, destination: Path):
    encoded = np.full(values.shape, 65535, dtype="<u2")
    valid = np.isfinite(values)
    encoded[valid] = np.rint((np.clip(values[valid], minimum, maximum) - minimum) / (maximum - minimum) * 65534.0).astype("<u2")
    destination.parent.mkdir(parents=True, exist_ok=True)
    header = struct.pack("<4sHHff", PROBE_MAGIC, encoded.shape[1], encoded.shape[0], float(minimum), float(maximum))
    with destination.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0) as gz:
        gz.write(header)
        gz.write(encoded.tobytes(order="C"))


def _hex(color):
    return np.array([int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)], dtype=np.float32)


def _write_image(values, spec, destination: Path):
    stops = spec["stops"]
    levels = np.array([s["value"] for s in stops], dtype=np.float32)
    colors = np.stack([_hex(s["color"]) for s in stops])
    clipped = np.clip(np.nan_to_num(values, nan=levels[0]), levels[0], levels[-1])
    rgb = np.stack([np.interp(clipped, levels, colors[:, c]) for c in range(3)], axis=-1)
    alpha = np.full(values.shape, 244, dtype=np.uint8)
    below = spec.get("transparent_below")
    if below is not None:
        alpha[~np.isfinite(values) | (values < below)] = 0
    else:
        alpha[~np.isfinite(values)] = 0
    rgba = np.concatenate([rgb.astype(np.uint8), alpha[..., None]], axis=-1)
    destination.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, "RGBA").save(destination, "WEBP", quality=80, method=4)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_interactive(raw, steps, run_date, output, grid, generated, config_dir):
    """Écrit maps/index.json, les grilles de valeurs et les images pour chaque échéance.

    `raw[variable]` : tableau (échéances × points candidats) des valeurs natives ; NaN = absent (rafale au pas 0).
    """
    layers = json.loads((Path(config_dir) / "interactive-layers.json").read_text(encoding="utf-8"))
    out = Path(output) / "maps"
    width, height = grid["width"], grid["height"]
    nn, w = grid["nn"], grid["w"]

    def field(variable, i):
        values = raw[variable][i]
        if not np.all(np.isfinite(values)):
            return None
        return (values[nn] * w).sum(axis=1).reshape(height, width).astype(np.float32)

    def bounds_of(key):
        spec = layers[key]
        below = spec.get("transparent_below")
        minimum = 0.0 if below is not None and below >= 0 else float(spec["stops"][0]["value"])
        return minimum, float(spec["stops"][-1]["value"])

    entries = []
    previous_total = None
    for i, lead in enumerate(steps):
        temperature = field("t_2m", i)
        u = field("u_10m", i)
        v = field("v_10m", i)
        total = field("tot_prec", i)
        if temperature is None or u is None or v is None or total is None:
            continue
        u, v = u * 3.6, v * 3.6
        gust = field("vmax_10m", i)
        fields = {
            "temperature": temperature - 273.15,
            "humidite": field("relhum_2m", i),
            "vent": np.hypot(u, v),
            "rafales": gust * 3.6 if gust is not None else None,
            "pluie_1h": np.maximum(total - previous_total, 0.0) if previous_total is not None else np.zeros_like(total),
            "pluie_cumul": total,
            "pression": (lambda p: p / 100.0 if p is not None else None)(field("pmsl", i)),
            "nebulosite": field("clct", i),
        }
        previous_total = total
        name = f"{lead:03d}"
        files, probes = {}, {}
        for key, values in fields.items():
            if values is None or key not in layers:
                continue
            minimum, _ = bounds_of(key)
            q = QUANTUM.get(key, 0.1)
            # Plage = exactement 65534 pas de `q` : chaque code uint16 vaut un multiple de q, l'octet haut reste
            # presque toujours nul et gzip divise la taille par 5 à 7 (mesuré sur un run réel).
            _write_probe(np.round(values / q) * q, minimum, minimum + 65534.0 * q, out / "values" / key / f"{name}.hkv.gz")
            _write_image(values, layers[key], out / key / f"{name}.webp")
            files[key] = f"maps/{key}/{name}.webp"
            probes[key] = f"maps/values/{key}/{name}.hkv.gz"
        for key, values in (("vent_u", u), ("vent_v", v)):
            _write_probe(np.round(values), VECTOR_RANGE[0], VECTOR_RANGE[0] + 65534.0, out / "values" / key / f"{name}.hkv.gz")
            probes[key] = f"maps/values/{key}/{name}.hkv.gz"
        entries.append({"lead_hour": int(lead), "valid_time": _iso(run_date + timedelta(hours=int(lead))), "files": files, "probes": probes})
    if not entries:
        raise ValueError("Aucune échéance interactive produite")
    index = {
        "generated_at": generated,
        "run_time": _iso(run_date),
        "model": {"name": "ICON-GLOBAL 13 km", "provider": "DWD", "resolution_km": 13},
        "bounds": BOUNDS,
        "width": width,
        "height": height,
        "layers": layers,
        "steps": entries,
    }
    (out / "index.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return len(entries)
