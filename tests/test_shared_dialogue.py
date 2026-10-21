"""The v0.1.3 SHS dialogue skin is shared by every game/package adapter."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from exp_runtime.content import EpisodeResources
from exp_runtime.dialogue import DialogueLayout, dialogue_styles
from exp_runtime.fonts import TextStyle, layout_text
from exp_runtime.runtime import SaveError, Session
from exp_runtime.speaker_names import NameFontState, SpeakerNames, outline_speaker_label
from exp_runtime.ui_assets import Rect
import test_label_layout
from test_label_layout import authored_dialogue
from test_runtime import Resources, host_call, text_words
from test_vm import program


def details(mode=1, speaker='Alex', theme=1):
    return dict(presentation_mode=mode, theme=theme, emphasis_theme=2,
                speaker=speaker, text='An authored sentence. ' * 30)


def check_original_page(test, session):
    """Optional checks use only the player's local originals."""
    layout = session.resources.dialogue_layout()
    test.assertIs(type(layout), DialogueLayout)
    page = session.dialogue_page()
    mode = session.pending.details['presentation_mode']
    if mode == 4:
        test.assertEqual(page.body_origin, (30, 120))
    else:
        node = layout.bank.rectangle(17, 8)
        extra = node.y - page.box.y
        test.assertIn(extra, (8, 40))
        test.assertEqual(page.box.width, node.width + 14)
        outline = getattr(layout.font(page.body_font), 'cap_height', None) is not None
        test.assertEqual(page.body_origin, (node.x, node.y) if outline else
                         (node.x - 7, node.y - extra // 2))
        if outline:
            test.assertLessEqual(page.body_origin[1] + page.body.ink_bounds[3],
                                 page.box.y + page.box.height + 1)
        name_font = layout.font(page.name_font)
        if getattr(name_font, 'native_face', False):
            label = outline_speaker_label(session.pending.details['speaker'], mode, page.name_font,
                                          layout.bank, name_font)
            test.assertEqual((page.name, page.name_origin, page.name_scale),
                             (label.layout, label.origin, 1))
        else:
            test_label_layout.SpeakerPlacementTests.assert_name_fits(test, page)
        test.assertTrue(session.engine.speaker_names.fonts)


class SharedDialogueTests(unittest.TestCase):
    def test_game_colors_do_not_select_different_dialogue_geometry(self):
        for theme in (1, 2, 3, -1):
            shs = dialogue_styles(theme, game='shs')
            cod = dialogue_styles(theme, game='cod')
            self.assertEqual(shs[:3], cod[:3])
            self.assertEqual((cod[3].height, cod[3].gap), (14, 7))
            self.assertEqual(cod[3].color, (180, 78, 78) if theme == 2 else (0, 0, 0))
        self.assertEqual(dialogue_styles(1, game='shs')[3].color, (41, 104, 221))
        for game, color, emphasis in (('shs', (223, 163, 52), (125, 67, 0)),
                                      ('cod', (0, 0, 0), (180, 109, 26))):
            style = dialogue_styles(-1, game=game, narrator=True)[3]
            self.assertEqual((style.height, style.gap), (10, 7))
            self.assertEqual((style.color, style.markers), (color, (('`', emphasis),)))

    def test_all_package_adapters_use_v013_geometry_and_speaker_history(self):
        reference = authored_dialogue()
        for game, kind in (('shs', 'apk'), ('shs', 'ipa'), ('cod', 'ipa')):
            with self.subTest(game=game, kind=kind):
                resources = EpisodeResources.__new__(EpisodeResources)
                resources.library = SimpleNamespace(game_id=game, kind=kind)
                with patch('exp_runtime.dialogue.read_ui', return_value=b'authored layout'), \
                     patch('exp_runtime.dialogue.LayoutBank.parse', return_value=reference.bank):
                    layout = resources.dialogue_layout()
                self.assertIs(type(layout), DialogueLayout)
                layout.font = reference.font
                layout.border_widths = reference.border_widths
                names = SpeakerNames()
                for mode, end, box, origin in (
                        (1, 91, Rect(33, 296, 254, 114), (33, 300)),
                        (2, 91, Rect(33, 296, 254, 114), (33, 300)),
                        (3, 113, Rect(33, 296, 254, 114), (33, 300)),
                        (4, 289, Rect(25, 115, 216, 214), (30, 120))):
                    d = details(mode)
                    layout.prepare_name(d, names)
                    page = layout.page(d, names=names)
                    expected_step = 17 if mode == 4 else 21
                    if game == 'cod':
                        # CoD's own SHSUIDialog (docs/COD.md, "Dialogue geometry"): typed lines sit 4 up and left of
                        # the text layer (plus the photo-measured baseline drop), and narration is measured and
                        # drawn in its own font, wrapped at 220, from (30, 120).
                        from exp_runtime.dialogue import COD_BASELINE_DROP, COD_TYPING_PAD
                        if mode == 4:
                            style = TextStyle(16, 9)
                            measured = layout_text(reference.font('TrebuchetMS_Italic16'), d['text'], 220, style)
                            width = max(120, (int(measured.width) + 2) // 2 * 2)
                            height = (int(measured.height) + 5) // 2 * 2
                            box, end, expected_step = Rect(25, 115, width + 10, height + 10), page.end, 25
                        origin = (origin[0] - COD_TYPING_PAD, origin[1] - COD_TYPING_PAD + COD_BASELINE_DROP)
                    self.assertEqual((page.box, page.body_origin, page.end), (box, origin, end))
                    self.assertEqual(page.name_scale, .9)
                    self.assertEqual([line.y for line in page.body.lines],
                                     [n * expected_step for n in range(len(page.body.lines))])
                    if mode != 4:
                        test_label_layout.SpeakerPlacementTests.assert_name_fits(self, page)
                    else:
                        self.assertEqual({g.color for g in page.body.glyphs},
                                         {(0, 0, 0) if game == 'cod' else (223, 163, 52)})
                expected_names, names = SpeakerNames(), SpeakerNames()
                reference.resources.library.game_id = game
                for mode in (2, 1, 3):
                    for theme in (1, 2, 3, -1):
                        for speaker in ('A very long speaker name', 'Alex', 'The Whole Room', "Howard's Mom"):
                            d = details(mode, speaker, theme)
                            self.assertEqual(layout.prepare_name(d, names),
                                             reference.prepare_name(d, expected_names))
                            self.assertEqual(names, expected_names)
                            self.assertEqual(layout.page(d, names=names),
                                             reference.page(d, names=expected_names))

    def session(self, game='shs', kind='ipa'):
        words, (ref,) = text_words('A long authored dialogue with several pages. ' * 40)
        resources = Resources(program(*host_call(13, ref, 1), 0x33, words=words))
        resources.library.kind = kind
        resources.library.game_id = game
        resources.dialogue_layout = authored_dialogue
        session = Session(resources)
        session.engine.character_names[1] = 'Spud The Stud'
        session.engine.character_art_variants[1] = [100] * 5
        session.engine.speaker_names.fonts['PajamaHip26'] = NameFontState(lines=2, gap=8)
        session.advance()
        session.tick(120000)
        session.answer()
        return session

    @unittest.skip("exp-runtime's own IPA save versions 13-15: this fork numbers saves independently (docs/RUNTIME.md)")
    def test_v14_ipa_reflows_saved_read_offset_and_rebuilds_only_missing_name_state(self):
        for game in ('shs', 'cod'):
            with self.subTest(game=game):
                session = self.session(game)
                old = session.snapshot()
                old['version'] = 14
                # v14's separate IPA renderer stored no speaker layout history.
                old['engine']['speaker_names'] = dict(fonts={}, basis={})
                old['engine']['panel']['speaker'] = old['pending']['details']['speaker']
                old['pending']['details']['page_end'] = old['pending']['details']['page_start'] + 1
                untouched = deepcopy(old)
                restored = Session.from_snapshot(session.resources, old)
                self.assertEqual(old, untouched)
                self.assertEqual(restored.vm.snapshot(), session.vm.snapshot())
                self.assertEqual(restored.engine.random48, session.engine.random48)
                self.assertEqual(restored.engine.numbers, session.engine.numbers)
                self.assertEqual(restored.engine.dialogue_animation, session.engine.dialogue_animation)
                self.assertGreater(restored.pending.details['page_start'], 0)
                self.assertEqual(restored.pending.details['page_start'], old['pending']['details']['page_start'])
                self.assertNotEqual(restored.pending.details['page_end'], old['pending']['details']['page_end'])
                self.assertTrue(restored.engine.speaker_names.fonts)
                current = restored.snapshot()
                self.assertEqual(current['version'], 27)
                self.assertEqual(Session.from_snapshot(session.resources, current).snapshot(), current)
                current['pending']['details']['page_end'] -= 1
                with self.assertRaisesRegex(SaveError, 'page does not match'):
                    Session.from_snapshot(session.resources, current)

    @unittest.skip("exp-runtime's own IPA save versions 13-15: this fork numbers saves independently (docs/RUNTIME.md)")
    def test_v13_ipa_reflow_uses_saved_basis_without_applying_current_name_twice(self):
        session = self.session()
        old = session.snapshot()
        old['version'] = 13
        old['pending']['details']['page_end'] -= 1
        restored = Session.from_snapshot(session.resources, old)
        self.assertEqual(restored.engine.speaker_names, session.engine.speaker_names)
        self.assertEqual(restored.engine.panel.speaker, session.engine.panel.speaker)
        self.assertEqual(restored.dialogue_page(), session.dialogue_page())
        self.assertEqual(restored.vm.snapshot(), session.vm.snapshot())

    @unittest.skip("exp-runtime's own IPA save versions 13-15: this fork numbers saves independently (docs/RUNTIME.md)")
    def test_v15_ipa_reflows_with_native_font_metrics_but_preserves_and_validates_history(self):
        from exp_runtime.background import BackgroundPan
        for game in ('shs', 'cod'):
            session = self.session(game)
            # v15 displayed a centered background and had no pan history.
            session.engine.background_pan = BackgroundPan()
            old = session.snapshot()
            old['version'] = 15
            del old['engine']['background_pan']
            before = deepcopy(old)
            # The old checkpoint used the bitmap-style layout; the same
            # resources now expose outline metrics without changing VM data.
            session.resources.dialogue_layout = lambda: authored_dialogue(outline=True)
            restored = Session.from_snapshot(session.resources, old)
            self.assertEqual(old, before)
            self.assertEqual(restored.vm.snapshot(), session.vm.snapshot())
            self.assertEqual(restored.engine, session.engine)
            self.assertEqual(restored.pending.details['page_start'], old['pending']['details']['page_start'])
            self.assertNotEqual(restored.pending.details['page_end'], old['pending']['details']['page_end'])
            current = restored.snapshot()
            self.assertEqual(current['version'], 27)
            self.assertEqual(Session.from_snapshot(session.resources, current).snapshot(), current)
            bad = deepcopy(old)
            bad['engine']['speaker_names']['fonts']['PajamaHip26']['lines'] += 1
            with self.assertRaisesRegex(SaveError, 'Speaker layout does not match'):
                Session.from_snapshot(session.resources, bad)
            current['pending']['details']['page_end'] -= 1
            with self.assertRaisesRegex(SaveError, 'page does not match'):
                Session.from_snapshot(session.resources, current)

    def test_apk_pages_and_current_ipa_font_history_remain_strictly_validated(self):
        apk = self.session(kind='apk')
        old = apk.snapshot()
        old['version'] = 14
        self.assertEqual(Session.from_snapshot(apk.resources, old).dialogue_page(), apk.dialogue_page())
        old['pending']['details']['page_end'] -= 1
        with self.assertRaisesRegex(SaveError, 'page does not match'):
            Session.from_snapshot(apk.resources, old)
        ipa = self.session()
        bad = ipa.snapshot()
        bad['engine']['speaker_names']['fonts']['PajamaHip26']['lines'] += 1
        with self.assertRaisesRegex(SaveError, 'Speaker layout does not match'):
            Session.from_snapshot(ipa.resources, bad)
