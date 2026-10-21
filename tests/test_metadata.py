import json
import unittest
from bildstod.metadata import analyze_questions,choice,human_expected,select_batch,make_analyzer

class MetadataTests(unittest.TestCase):
    def test_short_answers_and_object_contradiction(self):
        answers=iter(['1','black','short','medium','child'])
        p=analyze_questions(lambda *_:next(answers),True)[0]
        self.assertEqual(p['hairColor'],'svart')
        self.assertEqual(p['characterId'],'')
        self.assertEqual(p['genderPresentation'],'')
        self.assertEqual(analyze_questions(lambda *_:'zero',False),[])
        with self.assertRaises(ValueError):
            analyze_questions(lambda *_:'one',False)
        self.assertFalse(human_expected('One sheep. Isolated without people.'))
        self.assertTrue(human_expected('One preschool child listening.'))
        self.assertEqual(choice('black or brown',{'black':1,'brown':2}),'unknown')

    def test_pilot_lifetime_cap_resume_and_failed_receipts(self):
        items=[{'concept_id':f'FSK_81_{i:02}','sha256':str(i).zfill(64)} for i in range(40)]
        selected=select_batch(items,{'records':{}},{'pilot_limit':30})
        self.assertEqual(len(selected),30)
        records={c['concept_id']+':'+c['sha256']:{'status':'failed'} for c in selected}
        self.assertEqual(select_batch(items,{'records':records},{'pilot_limit':30}),[])
        records.pop(next(iter(records)))
        self.assertEqual(len(select_batch(items,{'records':records},{'pilot_limit':30})),1)

    def test_no_local_model_loading(self):
        with self.assertRaises(RuntimeError):
            make_analyzer({})
