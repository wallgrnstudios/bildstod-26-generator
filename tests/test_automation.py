import copy
import json
import tempfile
import unittest
from urllib.error import HTTPError
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
            self.assertFalse(e['reference_conditioning'])
            p.write_text(json.dumps({'regeneration_request_id':self.request['request_id'],'sha256':'b'*64}))
            self.assertEqual(apply_requests([self.entry],[self.request],output)[0],e)
            p.write_text(json.dumps({'status':'failed','regeneration_request_id':self.request['request_id'],'regeneration_source_sha256':self.sha}))
            revised={**self.request,'revision':2,'request_id':self.id+'_'+self.sha+'_r2'}
            self.assertEqual(apply_requests([self.entry],[revised],output)[0]['regeneration_request_id'],revised['request_id'])
            p.write_text(json.dumps({'sha256':'c'*64}))
            self.assertEqual(apply_requests([self.entry],[self.request],output),[self.entry])

    def test_rework_accepts_verified_source_from_previous_render_profile(self):
        with tempfile.TemporaryDirectory() as d:
            output=Path(d)
            legacy=output/'symbol-white-0.13-arm512'
            legacy.mkdir()
            (legacy/(self.id+'.previous.json')).write_text(json.dumps({
                'sha256':'b'*64,
                'regeneration_source_sha256':self.sha,
                'status':'pending_review',
            }))
            revised=apply_requests([self.entry],[self.request],output)[0]
            self.assertEqual(revised['regeneration_request_id'],self.request['request_id'])
            self.assertFalse(revised['reference_conditioning'])

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

    def test_token_budget_error_keeps_last_image_and_records_request_failure(self):
        import sys
        from types import SimpleNamespace
        from unittest.mock import Mock
        from bildstod import prompt_budget
        with tempfile.TemporaryDirectory() as d:
            output=Path(d)
            entry={**self.entry,'regeneration_request_id':self.request['request_id'],'regeneration_source_sha256':self.sha}
            catalog=output/'catalog.json';catalog.write_text(json.dumps([entry]))
            original={'concept_id':self.id,'label_sv':'dragkedja','status':'pending_review','sha256':self.sha}
            (output/(self.id+'.json')).write_text(json.dumps(original))
            planfile=output/'plan.json';planfile.write_text(json.dumps({'batch':[{'id':self.id}]}))
            tokenizer=Mock();tokenizer.encode.return_value=list(range(221))
            fake=SimpleNamespace(Qwen2TokenizerFast=SimpleNamespace(from_pretrained=lambda *a,**k:tokenizer))
            argv=['prompt_budget','--catalog',str(catalog),'--plan',str(planfile),'--checkpoint-branch','generated-flux-worker-0']
            with patch.dict(sys.modules,{'transformers':fake}),patch.object(sys,'argv',argv),patch('bildstod.generation.checkpoint_git') as checkpoint,self.assertRaisesRegex(ValueError,'221/220'):
                prompt_budget.main()
            checkpoint.assert_called_once()
            failure=json.loads((output/(self.id+'.json')).read_text())
            self.assertEqual(failure['error_type'],'PromptBudgetExceeded')
            self.assertEqual(failure['regeneration_request_id'],self.request['request_id'])
            self.assertEqual(json.loads((output/'candidates.json').read_text())['candidates'],[original])

    def test_public_queue_rejects_private_fields(self):
        f={'concept_id':{'stringValue':self.id},'source_sha256':{'stringValue':self.sha},'prompt_en':{'stringValue':self.request['prompt_en']},'public_approved':{'booleanValue':True},'schema_version':{'integerValue':'1'},'revision':{'integerValue':'1'},'createdAt':{'timestampValue':self.request['created_at']}}
        doc={'name':'queue/'+self.id+'_'+self.sha,'fields':f}
        with patch('bildstod.rework.read_url',return_value=json.dumps({'documents':[doc]}).encode()):self.assertEqual(fetch_queue(),[self.request])
        f['note']={'stringValue':'private'}
        with patch('bildstod.rework.read_url',return_value=json.dumps({'documents':[doc]}).encode()),self.assertRaises(ValueError):fetch_queue()
        del f['note'];f['cancelled']={'booleanValue':True}
        with patch('bildstod.rework.read_url',return_value=json.dumps({'documents':[doc]}).encode()):self.assertEqual(fetch_queue(),[])
        f['updatedAt']={'timestampValue':self.request['created_at']}
        with patch('bildstod.rework.read_url',return_value=json.dumps({'documents':[doc]}).encode()):self.assertEqual(fetch_queue(),[])

    def test_rate_limited_public_queue_defers_reworks_without_stopping_generation(self):
        warning=[]
        error=HTTPError('https://example.test/queue',429,'Quota exceeded',None,None)
        with patch('bildstod.rework.read_url',side_effect=error),patch('bildstod.rework.time.sleep') as sleep:
            self.assertEqual(fetch_queue(warning),[])
        sleep.assert_called_once_with(2)
        self.assertEqual(len(warning),1)

    def test_suppressed_images_do_not_inflate_active_coverage_or_pending_queue(self):
        receipt={'concept_id':self.id,'fingerprint':identity(self.entry,self.config),'status':'pending_review'}
        with patch('bildstod.operations.suppressed_concepts',return_value={self.id}):
            report=summarize([self.entry],[receipt],{},self.config)
        self.assertEqual((report['enabled'],report['with_image'],report['pending'],report['failed']),(0,0,[],[]))
        self.assertEqual(report['suppressed'],1)

    def test_empty_queue_is_healthy_and_fixed_sample_ids_remain(self):
        receipt={'concept_id':self.id,'fingerprint':identity(self.entry,self.config),'status':'pending_review'}
        s=summarize([self.entry],[receipt],{},self.config)
        self.assertEqual((s['pending'],s['failed'],s['with_image']),([],[],1))
        specs=json.loads((ROOT/'config/quality-specimens.json').read_text())['specimens']
        baseline=json.loads((ROOT/'config/quality-baseline.json').read_text())['specimens']
        self.assertEqual(len({s['id'] for s in specs}),24)
        self.assertEqual({s['id'] for s in specs},{s['concept_id'] for s in baseline})
        self.assertTrue(all(len(c['source_commit'])==40 and c['source_commit'] in c['source_url'] for c in baseline))
