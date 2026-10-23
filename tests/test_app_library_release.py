import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from tools.build_app_library_release import approved_current, build


class AppLibraryReleaseTests(unittest.TestCase):
    def test_only_current_explicit_approval_is_selected(self):
        candidates = [{"concept_id": "FSK_10_01", "sha256": "a" * 64}, {"concept_id": "FSK_10_02", "sha256": "b" * 64}]
        reviews = [{"concept_id": "FSK_10_01", "sha256": "a" * 64, "decision": "approved"},
                   {"concept_id": "FSK_10_02", "sha256": "c" * 64, "decision": "approved"}]
        self.assertEqual(approved_current(candidates, reviews), [candidates[0]])

    def test_catalog_is_content_addressed_and_matching_stays_disabled(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            image = root / "source.png"
            Image.new("RGBA", (16, 16), "white").save(image)
            digest = hashlib.sha256(image.read_bytes()).hexdigest()
            candidate = {"concept_id": "FSK_10_01", "label_sv": "boll", "sha256": digest,
                         "source_url": image.as_uri(), "symbol_type": "object"}
            catalog = build([candidate], [{"concept_id": "FSK_10_01", "sha256": digest, "decision": "approved"}],
                            [{"id": "FSK_10_01", "category": "lek"}], root / "release", "2026-10-23.1")
            entry = catalog["entries"][0]
            self.assertFalse(entry["matching"]["enabled"])
            self.assertEqual(entry["image"]["sha256"], digest)
            self.assertTrue((root / "release/images" / (digest + ".png")).exists())
