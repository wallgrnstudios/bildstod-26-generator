import tempfile
import unittest
from pathlib import Path
from PIL import Image, ImageDraw
from bildstod.triage import image_stats, rule_flags, duplicates, thumbnail, prioritize
from bildstod.contact_sheets import build


def drawing(box, color=(40, 90, 160)):
    image = Image.new('RGB', (512, 512), 'white')
    ImageDraw.Draw(image).rectangle(box, fill=color)
    return image


class TriageTests(unittest.TestCase):
    def test_rules_respect_symbol_type_and_material(self):
        cut = image_stats(drawing((0, 150, 300, 350)))
        self.assertIn('cropped', rule_flags(cut, {'symbol_type': 'object'}))
        self.assertNotIn('cropped', rule_flags(cut, {'symbol_type': 'body_part'}))
        brown = image_stats(drawing((150, 150, 350, 350), (150, 110, 70)))
        self.assertIn('warm_cast', rule_flags(brown, {'visual_prompt_en': 'One clean white diaper. Isolated on pure white.'}))
        self.assertNotIn('warm_cast', rule_flags(brown, {'visual_prompt_en': 'One wooden table. Isolated on pure white.'}))
        self.assertEqual(rule_flags(image_stats(drawing((150, 150, 350, 350))), {}), [])

    def test_duplicates_need_matching_hash_and_pixels(self):
        a, b, c = drawing((100, 100, 400, 400)), drawing((102, 100, 402, 400)), drawing((100, 100, 400, 400), (250, 220, 40))
        stats = {k: image_stats(v)['dhash'] for k, v in {'A': a, 'B': b, 'C': c}.items()}
        thumbs = {k: thumbnail(v) for k, v in {'A': a, 'B': b, 'C': c}.items()}
        pairs = {(x, y) for x, y, _ in duplicates(stats, thumbs, 8, 20)}
        self.assertIn(('A', 'B'), pairs)
        self.assertNotIn(('A', 'C'), pairs)

    def test_priority_orders_by_weighted_flags_and_sheets_render(self):
        ordered = prioritize({'X': {'concept_id': 'X', 'flags': ['warm_cast']}, 'Y': {'concept_id': 'Y', 'flags': ['reference_echo', 'cropped']}})
        self.assertEqual([r['concept_id'] for r in ordered], ['Y', 'X'])
        with tempfile.TemporaryDirectory() as d:
            path = Path(d, 'a.png');drawing((100, 100, 400, 400)).save(path)
            index = build({'FSK_10_01': path}, {'FSK_10_01': 'boll'}, {'FSK_10_01': 'lek'}, Path(d, 'out'))
            self.assertEqual(len(index[0]['files']), 7)
            self.assertTrue(all(Path(d, 'out', f).exists() for f in index[0]['files'].values()))
