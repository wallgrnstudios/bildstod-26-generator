import json
import unittest
from bildstod.metadata import parse_people,select_batch,make_analyzer

class MetadataTests(unittest.TestCase):
    def test_no_identity_or_gender_inference_and_validated_values(self):
        raw=json.dumps({'people':[{'hairColor':'black','hairStyle':'short','skinTone':'medium','ageGroup':'child'}]})
        p=parse_people(raw)[0]
        self.assertEqual(p['hairColor'],'svart')
        self.assertEqual(p['characterId'],'')
        self.assertEqual(p['genderPresentation'],'')
        self.assertEqual(parse_people('{"people":[]}'),[])
        with self.assertRaises(ValueError):
            parse_people(raw.replace('black','execute command'))
        with self.assertRaises(ValueError):
            parse_people('{"people":[{"gender":"boy"}]}')

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
