import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
maps = importlib.import_module('icon_global_maps')
ROOT = Path(__file__).resolve().parents[1]

class VectorMapsTests(unittest.TestCase):
    def test_vector_output_and_geographic_box(self):
        with tempfile.TemporaryDirectory() as tmp:
            for region in maps.REGIONS:
                west, east, south, north = maps.REGIONS[region][:4]
                lon = np.linspace(west, east, 40)
                lat = np.linspace(north, south, 35)
                xx, yy = np.meshgrid(lon, lat)
                rain = 160 * np.exp(-((xx - (west+east)/2)**2 + (yy-(south+north)/2)**2)/8)
                output = Path(tmp) / (region + '.png')
                box = maps._render({'lons': lon, 'lats': lat}, rain, 'precipitation', region, '2026092500', 120, output, ROOT/'config')
                self.assertTrue(output.exists())
                svg = ET.parse(output.with_suffix('.svg'))
                self.assertFalse(any(n.tag.endswith('}image') for n in svg.iter()), 'SVG must not embed a raster')
                self.assertGreater(sum(n.tag.endswith('}path') for n in svg.iter()), 50)
                self.assertTrue(all(0 < v < 1 for v in box))
                self.assertLessEqual(box[0] + box[2], 1)
                self.assertLessEqual(box[1] + box[3], 1)

    def test_wind_legend_steps(self):
        for key in ('vent', 'rafales'):
            np.testing.assert_array_equal(np.diff(maps.PRODUCTS[key]['levels']), 5)

if __name__ == '__main__':
    unittest.main()
