"""Cartes fixes et grilles interactives ICON-GLOBAL France/Europe."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree


REGIONS = {
    "france": (-6.0, 10.5, 41.0, 52.0, 0.18),
    "europe": (-25.0, 45.0, 30.0, 72.0, 0.32),
}
MAP_STEPS = (24, 48, 72, 120, 180)
PRODUCTS = {
    "temperature": {"label": "Température à 2 m", "unit": "°C", "variables": ("t_2m",),
                    "levels": np.arange(-30, 43, 3), "cmap": "turbo"},
    "precipitation": {"label": "Précipitations totales", "unit": "mm", "variables": ("tot_prec",),
                      "levels": np.array([0.1, 1, 2, 5, 10, 15, 20, 30, 40, 50, 70, 100, 150, 200]), "cmap": "turbo"},
    "rafales": {"label": "Rafales maximales à l’échéance", "unit": "km/h", "variables": ("vmax_10m",),
                "levels": np.arange(0, 181, 5), "cmap": "turbo"},
    "nuages": {"label": "Couverture nuageuse totale", "unit": "%", "variables": ("clct",),
               "levels": np.arange(0, 110, 10), "cmap": "Blues"},
    "vent": {"label": "Vent moyen à 10 m", "unit": "km/h", "variables": ("u_10m", "v_10m"),
             "levels": np.arange(0, 121, 5), "cmap": "viridis"},
}


def xyz(lat, lon):
    lat, lon = np.deg2rad(lat), np.deg2rad(lon)
    return np.column_stack((np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)))


def prepare_grids(native_lat, native_lon):
    """Associe chaque point d'une grille régulière au point ICON icosaédrique le plus proche."""
    native_lon = (np.asarray(native_lon) + 180) % 360 - 180
    native_lat = np.asarray(native_lat)
    grids = {}
    for region, (west, east, south, north, resolution) in REGIONS.items():
        lons = np.arange(west, east + resolution / 2, resolution)
        lats = np.arange(south, north + resolution / 2, resolution)
        lon_grid, lat_grid = np.meshgrid(lons, lats)
        candidates = np.flatnonzero((native_lat >= south - 2) & (native_lat <= north + 2) &
                                    (native_lon >= west - 2) & (native_lon <= east + 2))
        tree = cKDTree(xyz(native_lat[candidates], native_lon[candidates]))
        _, nearest = tree.query(xyz(lat_grid.ravel(), lon_grid.ravel()))
        grids[region] = {"lons": lons, "lats": lats, "indices": candidates[nearest]}
    return grids


def _draw_boundaries(ax, config_dir):
    import shapefile
    for name, width in (("ne_50m_coastline", .58), ("ne_50m_admin_0_boundary_lines_land", .42)):
        reader = shapefile.Reader(str(Path(config_dir) / "natural-earth" / name))
        for shape in reader.shapes():
            points = np.asarray(shape.points)
            parts = list(shape.parts) + [len(points)]
            for start, end in zip(parts, parts[1:]):
                ax.plot(points[start:end, 0], points[start:end, 1], color="#48545a", linewidth=width, zorder=3)


def _render(grid, values, product, region, run, step, destination, config_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm
    spec = PRODUCTS[product]
    west, east, south, north, _ = REGIONS[region]
    fig, ax = plt.subplots(figsize=(12, 8.2), dpi=150)
    norm = BoundaryNorm(spec["levels"], plt.get_cmap(spec["cmap"]).N, clip=True)
    mesh = ax.pcolormesh(grid["lons"], grid["lats"], values, shading="auto",
                         cmap=spec["cmap"], norm=norm, rasterized=True)
    _draw_boundaries(ax, config_dir)
    ax.set(xlim=(west, east), ylim=(south, north)); ax.set_xticks([]); ax.set_yticks([])
    ax.set_aspect(1.0 / np.cos(np.deg2rad((south + north) / 2.0)))
    run_dt = datetime.strptime(run, "%Y%m%d%H").replace(tzinfo=timezone.utc)
    ax.set_title(f"ICON-GLOBAL 13 km — {spec['label']} ({spec['unit']})\nRun {run_dt:%d/%m/%Y %H} UTC · H+{step}",
                 fontsize=12, fontweight="bold")
    bar = fig.colorbar(mesh, ax=ax, orientation="vertical", pad=.015, fraction=.035)
    bar.set_label(spec["unit"], fontweight="bold")
    ax.text(.5, .018, "www.alertes-meteo.com", transform=ax.transAxes, ha="center", va="bottom",
            fontsize=8, color="#f04444", fontweight="bold",
            bbox={"facecolor": "#111", "alpha": .94, "edgecolor": "none", "pad": 4})
    destination.parent.mkdir(parents=True, exist_ok=True)
    fig.canvas.draw(); position = ax.get_position()
    plot_box = [round(position.x0, 6), round(1 - position.y1, 6),
                round(position.width, 6), round(position.height, 6)]
    fig.savefig(destination, facecolor="white"); plt.close(fig)
    return plot_box


def generate_maps(listings, run, output_dir, download, decode, grids, config_dir):
    output_dir = Path(output_dir); manifests = {name: [] for name in PRODUCTS}; cache = {}; payload_cache = {}
    for step in MAP_STEPS:
        for product, spec in PRODUCTS.items():
            for region, grid in grids.items():
                fields = []
                for variable in spec["variables"]:
                    key = (variable, step, region)
                    if key not in cache:
                        payload_key = (variable, step)
                        if payload_key not in payload_cache:
                            payload_cache[payload_key] = download(listings[variable][run, step])
                        cache[key] = decode(payload_cache[payload_key], run, step, variable, grid["indices"])[0]
                    fields.append(cache[key])
                values = np.hypot(fields[0], fields[1]) * 3.6 if product == "vent" else fields[0]
                if product == "temperature": values = values - 273.15
                if product == "rafales": values = values * 3.6
                values = values.reshape(len(grid["lats"]), len(grid["lons"]))
                image = f"maps/{region}/{product}-{step:03d}h.png"
                probe = f"maps/{region}/{product}-{step:03d}h-values.json"
                plot_box = _render(grid, values, product, region, run, step, output_dir / image, config_dir)
                probe_payload = {"bounds": list(REGIONS[region][:4]),
                                 "lons": np.round(grid["lons"], 4).tolist(),
                                 "lats": np.round(grid["lats"], 4).tolist(),
                                 "values": np.round(values, 1).tolist()}
                (output_dir / probe).write_text(json.dumps(probe_payload, separators=(",", ":")), encoding="utf-8")
                manifests[product].append({"region": region, "lead_hour": step, "image": image,
                                           "values": probe, "plot_box": plot_box})
    payload = {"model": "ICON-GLOBAL", "pipeline_version": "2.0.0", "resolution_km": 13,
               "run": run, "steps": list(MAP_STEPS),
               "products": {key: {"label": value["label"], "unit": value["unit"], "maps": manifests[key]}
                            for key, value in PRODUCTS.items()}}
    (output_dir / "maps" / "manifest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
