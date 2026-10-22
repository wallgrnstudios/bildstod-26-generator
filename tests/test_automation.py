import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from bildstod.generation import ROOT,load_config,load_briefs,identity,seed_for,plan,run_batch,review_sheet
from bildstod.rework import apply_requests,fetch_queue
from bildstod.operations import summarize


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.config=load_config(ROOT/'config/generation.json')
        self.entry=next(e for e in load_briefs(ROOT/self.config['catalog_path']) if e.get('generation_enabled',True))
        self.id=self.entry['id'];self.sha='a'*64
        self.request={'concept_id':self.id,'source_sha256':self.sha,'prompt_en':'One clearly visible clean zipper on white.','request_id':self.id+'_'+self.sha+'_r1','revision':1,'created_at':'2026-10-22T10:00:00Z'}

    def test_matching_source_only_and_completed_override_stays(self):
        with tempfile.TemporaryDirectory() as d:
            output=Path(d);p=output/(self.id+'.json')
            self.assertEqual(apply_requests([self.entry],[self.request],output),[self.entry])
            p.write_text(json.dumps({'sha256':self.sha}))
            e=apply_requests([self.entry],[self.request],output)[0]
            self.assertNotEqual(identity(e,self.config),identity(self.entry,self.config))
            self.assertNotEqual(seed_for(e,self.config),seed_for(self.entry,self.config))
            p.write_text(json.dumps({'regeneration_request_id':self.request['request_id'],'sha256':'b'*64}))
            self.assertEqual(apply_requests([self.entry],[self.request],output)[0],e)
            p.write_text(json.dumps({'status':'failed','regeneration_request_id':self.request['request_id'],'regeneration_source_sha256':self.sha}))
            revised={**self.request,'revision':2,'request_id':self.id+'_'+self.sha+'_r2'}
            self.assertEqual(apply_requests([self.entry],[revised],output)[0]['regeneration_request_id'],revised['request_id'])
            p.write_text(json.dumps({'sha256':'c'*64}))
            self.assertEqual(apply_requests([self.entry],[self.request],output),[self.entry])

    def test_failed_replacement_preserves_previous_reviewable_image(self):
        with tempfile.TemporaryDirectory() as d:
            output=Path(d)
            original={'concept_id':self.id,'label_sv':'dragkedja','status':'pending_review','sha256':self.sha}
            (output/(self.id+'.json')).write_text(json.dumps(original))
            revised={**self.entry,'regeneration_request_id':self.request['request_id']}
            # Inject renderer, no model loads. Fail after last successful version is backed up.
            def fail(*args):raise RuntimeError('synthetic failure')
            batch=[{'id':self.id,'prompt':'test','seed':1}]
            with self.assertRaises(RuntimeError):run_batch([revised],self.config,output,batch,render=fail)
            review_sheet(output)
            self.assertEqual(json.loads((output/'candidates.json').read_text())['candidates'],[original])

    def test_public_queue_rejects_private_fields(self):
        f={'concept_id':{'stringValue':self.id},'source_sha256':{'stringValue':self.sha},'prompt_en':{'stringValue':self.request['prompt_en']},'public_approved':{'booleanValue':True},'schema_version':{'integerValue':'1'},'revision':{'integerValue':'1'},'createdAt':{'timestampValue':self.request['created_at']}}
        doc={'name':'queue/'+self.id+'_'+self.sha,'fields':f}
        with patch('bildstod.rework.read_url',return_value=json.dumps({'documents':[doc]}).encode()):self.assertEqual(fetch_queue(),[self.request])
        f['note']={'stringValue':'private'}
        with patch('bildstod.rework.read_url',return_value=json.dumps({'documents':[doc]}).encode()),self.assertRaises(ValueError):fetch_queue()

    def test_empty_queue_is_healthy_and_fixed_sample_ids_remain(self):
        receipt={'concept_id':self.id,'fingerprint':identity(self.entry,self.config),'status':'pending_review'}
        s=summarize([self.entry],[receipt],{},self.config)
        self.assertEqual((s['pending'],s['failed'],s['with_image']),([],[],1))
        specs=json.loads((ROOT/'config/quality-specimens.json').read_text())['specimens']
        baseline=json.loads((ROOT/'config/quality-baseline.json').read_text())['specimens']
        self.assertEqual(len({s['id'] for s in specs}),24)
        self.assertEqual({s['id'] for s in specs},{s['concept_id'] for s in baseline})
        self.assertTrue(all(len(c['source_commit'])==40 and c['source_commit'] in c['source_url'] for c in baseline))
