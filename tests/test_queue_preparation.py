import copy
import unittest
from tools.prepare_production_queue import prepare

class QueuePreparationTests(unittest.TestCase):
    def test_repeated_preparation_preserves_corrected_briefs_and_stable_ids(self):
        original={'id':'FSK_10_01','text_sv':'tidigare','visual_prompt_en':'Reviewer corrected prompt','style_prompt_override':'Reviewed style'}
        symbols=[copy.deepcopy(original)]
        vocabulary=[{'id':'FSK_10_01','text_sv':'tidigare','brief_status':'generation_ready','entry_type':'concept'},
                    {'id':'FSK_10_02','text_sv':'ny','brief_status':'brief_required','entry_type':'concept','priority_tier':2}]
        briefs=[['tidigare','Obsolete source prompt','Gammalt krav','annat'],['ny','One clearly defined object.','Tydlig form','annat']]
        self.assertEqual(prepare(symbols,vocabulary,briefs),['FSK_10_02'])
        self.assertEqual(symbols[0],original)
        self.assertEqual(symbols[1]['generation_priority'],2)
        self.assertEqual(vocabulary[1]['symbol_id'],'FSK_10_02')
        saved=copy.deepcopy(symbols)
        self.assertEqual(prepare(symbols,vocabulary,briefs),[])
        self.assertEqual(symbols,saved)

    def test_phrase_is_not_activated_as_an_object(self):
        vocabulary=[{'id':'FSK_10_03','text_sv':'jag går','brief_status':'composition_required','entry_type':'phrase'}]
        with self.assertRaises(ValueError):
            prepare([],vocabulary,[['jag går','One child walking.','Ett barn','sitta']])
