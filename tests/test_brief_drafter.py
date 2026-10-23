import unittest

from bildstod.brief_drafter import candidates, draft, parse_suggestion, prompt_for


class BriefDrafterTests(unittest.TestCase):
    def setUp(self):
        self.open = {"id": "FSK_10_12", "text_sv": "var", "resolution": "open_question",
                     "meaning_sv": "Tvetydigt ord.", "question_sv": "Vilken betydelse?",
                     "options_sv": ["Plats", "Dåtid"]}
        self.convention = {"id": "FSK_90_11", "text_sv": "paus", "resolution": "convention_proposal",
                           "meaning_sv": "Tillfälligt avbrott.", "proposal_sv": "Barn och pussel.",
                           "proposal_visual_en": "A child beside a puzzle."}
        self.valid = '{"safe_to_generate":false,"meaning_sv":"Frågeord om plats.","visual_prompt_en":"A child pointing to two different places.","must_show_sv":["Två platser"],"must_not_show_sv":["Text"],"contrast_terms_sv":["vart"],"review_question_sv":"Är denna betydelse vald?"}'

    def test_only_open_questions_are_selected_by_default(self):
        selected = candidates([self.convention, self.open], {}, 10)
        self.assertEqual([row["id"] for row in selected], ["FSK_10_12"])
        self.assertEqual(len(candidates([self.convention, self.open], {}, 10, True)), 2)
        self.assertEqual([row["id"] for row in candidates([self.open], {"FSK_10_12": {"status": "model_error"}}, 10)],
                         ["FSK_10_12"])
        self.assertEqual(candidates([self.open], {"FSK_10_12": {"status": "needs_editorial_review"}}, 10), [])

    def test_model_output_is_bounded_json(self):
        parsed = parse_suggestion("<think>reasoning</think>\n" + self.valid)
        self.assertFalse(parsed["safe_to_generate"])
        self.assertIn("Input:", prompt_for(self.open))
        self.assertEqual(parse_suggestion(self.valid.replace("Frågeord om plats.", "Frågeord\nom plats."))["meaning_sv"], "Frågeord\nom plats.")

    def test_draft_never_changes_catalog_and_requires_review(self):
        state = {"schema_version": 1, "records": {}}
        rows = draft([self.open], state, 1, ask=lambda row, model: parse_suggestion(self.valid))
        self.assertEqual([row["id"] for row in rows], ["FSK_10_12"])
        self.assertEqual(state["records"]["FSK_10_12"]["status"], "needs_editorial_review")
        self.assertNotIn("generation_enabled", state["records"]["FSK_10_12"])
