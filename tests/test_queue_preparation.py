import copy
import unittest
from tools.prepare_production_queue import prepare, prepare_resolutions

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

    def test_typed_resolutions_keep_people_and_never_activate_conventions(self):
        vocabulary=[{'id':'FSK_11_01','text_sv':'kasta','brief_status':'brief_required','entry_type':'concept','category':'rörelse'},
                    {'id':'FSK_11_02','text_sv':'över','brief_status':'convention_required','entry_type':'concept','category':'position'},
                    {'id':'FSK_11_03','text_sv':'jag kastar','brief_status':'composition_required','entry_type':'phrase','category':'rörelse'}]
        resolutions=[{'id':'FSK_11_01','text_sv':'kasta','resolution':'standalone','meaning_sv':'Att kasta.','symbol_type':'action',
                      'visual_prompt_en':'One child throwing a ball overhand.','must_show_sv':['Boll i luften'],'must_not_show_sv':['Fånga'],'contrast_terms_sv':['rulla']},
                     {'id':'FSK_11_02','text_sv':'över','resolution':'convention_proposal','meaning_sv':'Läge ovanför.','proposal_sv':'Boll ovanför låda',
                      'proposal_visual_en':'Ball above box.','review_question_sv':'Begripligt?','contrast_terms_sv':['på']},
                     {'id':'FSK_11_03','text_sv':'jag kastar','resolution':'composition','meaning_sv':'Jag kastar.','parts':[{'text':'jag '},{'text':'kastar','symbol_id':'FSK_11_01'}]}]
        symbols=[]
        self.assertEqual(prepare_resolutions(symbols,vocabulary,resolutions),['FSK_11_01'])
        self.assertEqual(symbols[0]['symbol_type'],'action')
        self.assertNotIn('No people',symbols[0]['visual_prompt_en'])
        self.assertEqual([r['brief_status'] for r in vocabulary],['generation_ready','convention_proposed','composition_defined'])
        self.assertEqual([r['generation_enabled'] for r in vocabulary],[True,False,False])
        symbols[0]['visual_prompt_en']='Reviewer corrected'
        self.assertEqual(prepare_resolutions(symbols,vocabulary,resolutions),[])
        self.assertEqual(symbols[0]['visual_prompt_en'],'Reviewer corrected')
        resolutions[2].update(resolution='standalone',symbol_type='action',visual_prompt_en='x',must_show_sv=['x'],must_not_show_sv=['x'],contrast_terms_sv=['x'])
        with self.assertRaises(ValueError):
            prepare_resolutions(symbols,vocabulary,resolutions)
