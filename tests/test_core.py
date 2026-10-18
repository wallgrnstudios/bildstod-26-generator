import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from bildstod.catalog import load, search
from bildstod.pipeline import save_candidate, build_index, atomic_json

class CoreTests(unittest.TestCase):
    def test_multilingual_search(self):
        entries = load('data/ordlista.json')
        for query in (' ÄTER ', 'وجبة', 'їсти', 'eating'):
            self.assertEqual(search(entries, query)[0]['id'], 'ORD_0001')
        self.assertEqual(search(entries, 'saknas'), [])

    def test_publication_gate_and_metadata(self):
        entry = load('data/ordlista.json')[0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root / 'ORD_0001.png'
            save_candidate(Image.new('RGB', (160, 200)), entry, path, 'test')
            with Image.open(path) as image:
                self.assertIn('وجبة', json.loads(image.info['bildstod'])['keywords'])
            self.assertEqual(build_index([entry], root), [])
            metadata = json.loads(path.with_suffix('.json').read_text())
            metadata.update(review_status='approved', license='test-only')
            atomic_json(path.with_suffix('.json'), metadata)
            self.assertEqual(len(build_index([entry], root)), 1)
            changed = {**entry, 'word_sv': 'ändrad'}
            self.assertEqual(build_index([changed], root), [])

if __name__ == '__main__':
    unittest.main()
