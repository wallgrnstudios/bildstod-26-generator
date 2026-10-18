import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from bildstod.generation import (ROOT, load_config, load_briefs, plan, identity, prompt_for,
                                 run_batch, verify_transparency, check_compute_permission)
from bildstod.pipeline import save_candidate
from bildstod.catalog import load


class GenerationTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(ROOT / 'config/generation.json')
        self.config['calibration_ids'] = ['FSK_01_04']
        self.entries = load_briefs(ROOT / 'catalog/pilot/concepts.json')

    def test_locked_style_and_calibration_queue(self):
        self.assertEqual(len(self.entries), 50)
        with tempfile.TemporaryDirectory() as directory:
            batch = plan(self.entries, self.config, Path(directory), 3)
            self.assertEqual([x['id'] for x in batch], ['FSK_01_04'])
            entry = next(x for x in self.entries if x['id'] == batch[0]['id'])
            self.assertIn(entry['visual_prompt_en'], prompt_for(entry, self.config))
            self.assertIn('pure white', batch[0]['prompt'].lower())
            self.assertNotIn('off-white rounded card', batch[0]['prompt'])
            changed = {**self.config, 'calibration_approved': True, 'batch_limit': 3}
            self.assertEqual(identity(entry, self.config), identity(entry, changed))
            with self.assertRaises(ValueError):
                plan(self.entries, self.config, Path(directory), 101)

    def test_transparent_output_integrity_and_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            batch = plan(self.entries, self.config, output, 1)
            def fake_render(*_):
                return Image.new('RGB', (1024, 1024), 'white')
            def fake_remove(*_):
                cutout = Image.new('RGBA', (1024, 1024), (0, 0, 0, 0))
                cutout.paste((120, 160, 100, 255), (200, 200, 800, 900))
                return cutout
            run_batch(self.entries, self.config, output, batch, fake_render, fake_remove)
            target = output / 'FSK_01_04.png'
            with Image.open(target) as image:
                self.assertEqual(image.mode, 'RGBA')
                self.assertGreater(verify_transparency(image)['transparent_fraction'], 0.05)
                self.assertEqual(json.loads(image.info['bildstod'])['status'], 'pending_review')
            self.assertEqual(plan(self.entries, self.config, output, 1), [])
            self.assertTrue((output / 'raw/FSK_01_04.png').exists())
            target.write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError, 'Damaged output'):
                plan(self.entries, self.config, output, 1)

    def test_failure_stops_without_auto_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            batch = plan(self.entries, self.config, output, 1)
            def fail(*_):
                raise RuntimeError('simulated model failure')
            with self.assertRaises(RuntimeError):
                run_batch(self.entries, self.config, output, batch, fail)
            self.assertEqual(plan(self.entries, self.config, output, 1), [])
            self.assertEqual(len(plan(self.entries, self.config, output, 1, retry_failed=True)), 1)
            with self.assertRaises(ValueError):
                verify_transparency(Image.new('RGBA', (128, 128), 'white'))

    def test_batch_reuses_models_and_checkpoints_each_image(self):
        config = {**self.config, 'calibration_approved': True}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            batch = plan(self.entries, config, output, 2)
            with patch('bildstod.generation.CpuRenderer') as renderer, patch('bildstod.generation.BackgroundRemover') as remover:
                renderer.return_value.return_value = Image.new('RGB', (1024, 1024), 'white')
                cutout = Image.new('RGBA', (1024, 1024), (0, 0, 0, 0))
                cutout.paste((100,150,100,255), (200,200,800,800))
                remover.return_value.return_value = cutout
                checkpoints = []
                run_batch(self.entries, config, output, batch, checkpoint=lambda p: checkpoints.append(p))
                renderer.assert_called_once()
                remover.assert_called_once()
                self.assertEqual(renderer.return_value.call_count, 2)
                self.assertEqual(len(checkpoints), 2)
                renderer.return_value.close.assert_called_once()
                self.assertEqual(json.loads((output/'metrics.json').read_text())['completed_this_run'], 2)
        all_ids = [item['id'] for index in range(8) for item in plan(self.entries, config, Path('/tmp/unused-bildstod-test-shards'), 100, shard_index=index, shard_count=8)]
        self.assertEqual(len(all_ids), 50)
        self.assertEqual(len(set(all_ids)), 50)

    def test_no_accidental_local_workload_and_preserved_import_alpha(self):
        with patch.dict('os.environ', {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'Local model execution is off'):
                check_compute_permission(False)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'test.png'
            source = Image.new('RGBA', (160, 200), (0, 0, 0, 0))
            source.paste((20, 80, 40, 255), (30, 30, 120, 170))
            save_candidate(source, load(ROOT / 'data/ordlista.json')[0], target, 'test')
            with Image.open(target) as image:
                self.assertEqual(image.getchannel('A').getextrema(), (0, 255))
