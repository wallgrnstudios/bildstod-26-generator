import copy
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from bildstod.quality_lab import CHECKS, plan, render, save_decisions, merge
from bildstod.operations import production_activity


class QualityLabTests(unittest.TestCase):
    def state(self):
        return {'experiment_id':'test', 'max_attempts':2, 'cases':[
            {'id':'FSK_90_01','entry':{'id':'FSK_90_01','text_sv':'dragkedja',
             'visual_prompt_en':'One zipper.', 'must_show_sv':['Löpare']},'attempts':{}}]}

    def test_paired_seeds_and_bounded_human_correction(self):
        state=self.state()
        a=plan(state,'text')[0];b=plan(state,'reference')[0]
        self.assertEqual(a['seed'], b['seed'])
        self.assertFalse(a['entry']['reference_conditioning'])
        self.assertTrue(b['entry']['reference_conditioning'])
        attempts=state['cases'][0]['attempts']['text']=[{'status':'pending_review'}]
        self.assertEqual(plan(state,'text'),[])
        attempts[0].update(decision='revise',next_prompt_en='One clearly visible zipper slider.')
        self.assertEqual(plan(state,'text')[0]['entry']['visual_prompt_en'],attempts[0]['next_prompt_en'])
        attempts.append(copy.deepcopy(attempts[0]))
        self.assertEqual(plan(state,'text'),[])

    def test_failed_attempt_is_not_silently_retried(self):
        state=self.state()
        for status in ('started','failed'):
            state['cases'][0]['attempts']['text']=[{'status':status}]
            self.assertEqual(plan(state,'text'),[])
        with patch.dict('os.environ',{'GITHUB_ACTIONS':'false'}):
            with self.assertRaisesRegex(ValueError,'GitHub-hosted'):
                render(Path('/nonexistent'),'text')

    def test_reviews_require_matching_bytes_and_all_checks(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);image=root/'candidate.png';Image.new('RGB',(48,48),'white').save(image)
            sha=hashlib.sha256(image.read_bytes()).hexdigest()
            state=self.state();state['cases'][0]['attempts']['text']=[{'attempt':1,'status':'pending_review','sha256':sha,'image':'candidate.png'}]
            path=root/'experiment.json';path.write_text(json.dumps(state));original=path.read_bytes()
            decision={'id':'FSK_90_01','profile':'text','attempt':1,'sha256':sha,'decision':'keep_for_pilot','checks':dict.fromkeys(CHECKS,True),'note':''}
            invalid=copy.deepcopy(decision);invalid['checks']['meaning']=False
            with self.assertRaises(ValueError):save_decisions(root,[decision,invalid])
            self.assertEqual(path.read_bytes(),original)
            save_decisions(root,[decision])
            self.assertEqual(json.loads((root/'metrics.json').read_text())['text']['kept'],1)
            image.write_bytes(b'changed')
            with self.assertRaises(ValueError):save_decisions(root,[decision])

    def test_hosted_runner_writes_reviewable_candidate_without_touching_baseline(self):
        from bildstod.generation import ROOT, load_config, load_briefs
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);state=self.state()
            state['config']=load_config(ROOT/'config/generation.json')
            state['cases'][0]['entry']=next(e for e in load_briefs(ROOT/'catalog/pilot/symbols.json') if e['id']=='FSK_90_01')
            (root/'baseline').mkdir();baseline=root/'baseline/FSK_90_01.png'
            Image.new('RGB',(512,512),'red').save(baseline);before=baseline.read_bytes()
            (root/'experiment.json').write_text(json.dumps(state))
            class FakeRenderer:
                def __init__(self,*args):pass
                def __call__(self,*args):return Image.new('RGB',(512,512),'white')
                def close(self):pass
            with patch.dict('os.environ',{'GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'github-hosted'}), patch('bildstod.flux_renderer.FluxRenderer',FakeRenderer):
                render(root,'text')
                render(root,'text')
            state=json.loads((root/'experiment.json').read_text())
            records=state['cases'][0]['attempts']['text']
            self.assertEqual(len(records),1)
            self.assertEqual(records[0]['status'],'pending_review')
            self.assertEqual(baseline.read_bytes(),before)
            self.assertIn('data-identity', (root/'review.html').read_text())

    def test_merge_refuses_unpaired_experiment(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);a=root/'text';b=root/'reference';a.mkdir();b.mkdir()
            state=self.state();state['config']={};state['cases'][0]['baseline']={'sha256':'a'*64}
            (a/'experiment.json').write_text(json.dumps(state))
            other=copy.deepcopy(state);other['experiment_id']='different'
            (b/'experiment.json').write_text(json.dumps(other))
            with self.assertRaises(ValueError):merge(a,b)
            other['experiment_id']=state['experiment_id'];other['cases'][0]['baseline']['sha256']='b'*64
            (b/'experiment.json').write_text(json.dumps(other))
            with self.assertRaises(ValueError):merge(a,b)
            (b/'experiment.json').write_text(json.dumps(state));merge(a,b)
            self.assertTrue((a/'review.html').exists())

    def test_activity_uses_image_dates_not_workflow_success(self):
        now=datetime(2026,11,8,18,tzinfo=timezone.utc)
        activity=production_activity([{'created_at':'2026-11-06T18:00:00Z'}],{'pending':[],'failed':[]},now)
        self.assertTrue(activity['no_candidates_for_24h'])
        self.assertTrue(activity['base_queue_empty'])
        self.assertIsNone(activity['approved_last_24h'])
        self.assertIsNone(production_activity([],{'pending':['x'],'failed':[]},now)['no_candidates_for_24h'])

if __name__=='__main__':unittest.main()
