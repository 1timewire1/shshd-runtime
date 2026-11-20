"""Claire Hart plan Stage 0, E: a narrator line shows the narrator's portrait (presentation narration_portrait): a small
speaker-style box attached to the portrait (the lead's side), in narration's text, with no name plate (owner,
2026-11-19)."""
import unittest

from exp_runtime.dialogue_animation import DialoguePortrait
from exp_runtime.engine import EngineState


class NarrationPortraitTests(unittest.TestCase):
    def engine(self, on):
        engine = EngineState()
        engine.ui_defaults[75] = 7                  # the narrator (service 75)
        engine.character_art_variants[7] = [2401, 2402, -1, 2404, 2405]
        engine.narration_portrait = on
        return engine

    def test_the_narrator_speaks_beside_a_portrait_as_narration_when_wanted(self):
        self.assertEqual(self.engine(False).dialogue_presentation(7, 0), (4, -1, -1))
        self.assertEqual(self.engine(True).dialogue_presentation(7, 0), (1, 7, 0))
        self.assertEqual(self.engine(True).dialogue_presentation(7, 2), (4, -1, -1))       # no art for this face
        details = self.engine(True).present_dialogue(7, 1, 'The night was quiet.', 0)
        self.assertEqual((details['presentation_mode'], details['visible_character_id'], details['speaker'],
                          details.get('narration'), details['relationship']), (1, 7, '', True, None))
        portrait = DialoguePortrait.from_details(details, {7: [2401, 2402, -1, 2404, 2405]})
        self.assertEqual((portrait.asset_id, portrait.mode), (2402, 1))

    def test_cod_turns_it_on_for_claire_hart_classic_only(self):
        from exp_runtime.cod import profile
        self.assertEqual(profile.TRANSLATED_NARRATION_PORTRAITS, {31500: True})


if __name__ == '__main__':
    unittest.main()
