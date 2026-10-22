import unittest
from bildstod.prompt_budget import validate_prompt_budget

class BudgetTests(unittest.TestCase):
    def test_uses_complete_rendered_prompt_and_reports_all_bad_entries(self):
        class Tokenizer:
            def encode(self,prompt):
                # Both style and appended instructions consume the real text budget.
                assert 'STYLE' in prompt and 'No decorative scene' in prompt
                return list(range(221 if 'LONG' in prompt else 220))
        entries=[{'id':'FSK_10_01','symbol_type':'object','visual_prompt_en':'LONG'},
                 {'id':'FSK_10_02','symbol_type':'object','visual_prompt_en':'LONG'}]
        with self.assertRaisesRegex(ValueError,'FSK_10_01: 221/220.*FSK_10_02: 221/220'):
            validate_prompt_budget(entries,{'style_prompt':'STYLE'},Tokenizer())
        entries[0]['visual_prompt_en']='SHORT'
        result=validate_prompt_budget(entries[:1],{'style_prompt':'STYLE'},Tokenizer())
        self.assertEqual(result,{'checked':1,'max_tokens':220,'limit':220})
