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



class CreatorNarrationPortraitTests(unittest.TestCase):
    """The Creator's setting (owner, 2026-11-19): a CoD project may show the narrator's portrait beside narration, as Claire
    Hart's cases do; CoD accepts that one declared member and no other."""

    def test_a_cod_project_declares_it_when_set(self):
        from exp_runtime.creator import Project
        from exp_runtime.creator.compiler import presentation_record
        from exp_runtime.creator.model import FREE_SETTING_GAMES, validate_structure
        project = Project(game='cod')
        self.assertNotIn('narration_portrait', presentation_record(project))
        project.options = {'narration_portrait': True}
        validate_structure(project)
        self.assertEqual(presentation_record(project), {'narration_portrait': True})
        self.assertEqual(FREE_SETTING_GAMES['narration_portrait'], 'cod')

    def test_cod_reads_that_member_alone(self):
        from types import SimpleNamespace
        from exp_runtime.content import declared, presentation_feature
        episode = SimpleNamespace(record=dict(pack_id=30000), library=SimpleNamespace(game_id='cod'),
                                  presentation={'narration_portrait': True, 'duet': (1, 2), 'creator': True})
        self.assertIs(presentation_feature(episode, 'narration_portrait'), True)
        self.assertIsNone(presentation_feature(episode, 'duet'))         # not CoD's to declare
        self.assertIsNone(declared(episode, 'creator'))
        shs = SimpleNamespace(record=dict(pack_id=30000), library=SimpleNamespace(game_id='shs'), presentation={'duet': (1, 2)})
        self.assertEqual(presentation_feature(shs, 'duet'), (1, 2))       # SHS still takes every member


if __name__ == '__main__':
    unittest.main()
