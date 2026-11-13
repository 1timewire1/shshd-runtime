"""Extra rows per speech bubble in a frame taller than HD's 3:4 (General's Aspect Ratio, owner 2026-11-11)."""
import unittest

from exp_runtime.runtime import Session
from test_label_layout import authored_dialogue
from test_runtime import Resources, answer_screen, host_call, text_words
from test_vm import program


class ExtraRowsTests(unittest.TestCase):
    def session(self):
        text = 'A long line of speech that runs on and on across the bubble. ' * 12
        words, (ref,) = text_words(text)
        resources = Resources(program(*host_call(13, ref, 1), 0x33, words=words))
        resources.library.kind = 'ipa'
        layout = authored_dialogue(outline=True)
        resources.dialogue_layout = lambda: layout
        session = Session(resources)
        session.engine.character_names[1] = 'Avery'
        session.engine.character_art_variants[1] = [100] * 5
        session.advance()
        answer_screen(session)
        return session, resources

    def test_a_bubble_holds_more_rows_and_grows_upward(self):
        session, _ = self.session()
        hd, taller = session.dialogue_page(extra_rows=0), session.dialogue_page(extra_rows=2)
        self.assertEqual(len(taller.body.lines), len(hd.body.lines) + 2)
        self.assertGreater(taller.end, hd.end)
        self.assertEqual(hd.lift, 0)
        self.assertGreater(taller.lift, 0)
        # The whole bubble moves up by its lift: its bottom stays where HD's is.
        self.assertAlmostEqual(taller.box.y + taller.box.height, hd.box.y + hd.box.height)
        self.assertAlmostEqual(taller.portrait.y, hd.portrait.y - taller.lift)
        self.assertAlmostEqual(taller.name_origin[1], hd.name_origin[1] - taller.lift)

    def test_a_short_line_is_hds_whatever_the_rows(self):
        words, (ref,) = text_words('Hi there.')
        resources = Resources(program(*host_call(13, ref, 1), 0x33, words=words))
        resources.library.kind = 'ipa'
        layout = authored_dialogue(outline=True)
        resources.dialogue_layout = lambda: layout
        session = Session(resources)
        session.engine.character_art_variants[1] = [100] * 5
        session.advance()
        self.assertEqual(session.dialogue_page(extra_rows=3), session.dialogue_page(extra_rows=0))

    def test_the_line_on_screen_re_pages_and_a_save_keeps_hds_page(self):
        session, resources = self.session()
        details = session.pending.details
        hd_end = details['page_end']
        session.dialogue_extra_rows = 2
        self.assertGreater(details['page_end'], hd_end)
        saved = session.snapshot()
        self.assertEqual(saved['pending']['details']['page_end'], hd_end)
        # Loaded at 3:4 (no extra rows), as on any build: valid, and HD's page.
        restored = Session.from_snapshot(resources, saved)
        self.assertEqual(restored.pending.details['page_end'], hd_end)
        restored.dialogue_extra_rows = 2
        self.assertEqual(restored.pending.details['page_end'], details['page_end'])
        # The next page starts where the lengthened one ended.
        lengthened = details['page_end']
        session.tick(5000)
        session.answer()
        self.assertEqual(session.pending.name, 'dialogue')
        self.assertEqual(session.pending.details['page_start'], lengthened)


if __name__ == '__main__':
    unittest.main()
