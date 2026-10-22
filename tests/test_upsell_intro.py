"""The store plugs some SHS episodes open with (upsell_intro.py), on authored openings."""
import unittest

from exp_runtime.runtime import Session
from exp_runtime.upsell_intro import SEQUENCES, line_digest, skip_upsell_intro
from test_runtime import Resources, host_call, text_words
from test_vm import program

PLUG = ('Want to catch up? Grab the authored set!', 'It is in the store now!', 'And now...')


def opening(*lines, title=True):
    """Narrator lines, then a title card and a story line."""
    words, refs = text_words(*lines, 'Authored Episode', 'Story.')
    calls = [word for ref in refs[:len(lines)] for word in host_call(13, ref, 0)]
    if title:
        calls += host_call(8, refs[-2], refs[-2], -1, 0)
    return Resources(program(*calls, *host_call(13, refs[-1], 0), 0x33, words=words))


def digests(*lines):
    return tuple(line_digest(line) for line in lines)


class UpsellIntroTests(unittest.TestCase):
    def test_the_plug_is_acknowledged_up_to_the_title_card(self):
        session = skip_upsell_intro(Session(opening(*PLUG)), (digests(*PLUG),))
        self.assertEqual(session.pending.name, 'presentation')

    def test_it_stops_at_the_episodes_own_recap(self):
        # 2_1 Howard's Return: the plug's "And now..." is followed by "When we last left off...", which stays.
        recap = 'When we last left off, the authored story was just beginning.'
        session = skip_upsell_intro(Session(opening(*PLUG, recap)), (digests(*PLUG),))
        self.assertEqual((session.pending.name, session.pending.details['text']), ('dialogue', recap))

    def test_an_opening_that_matches_no_sequence_whole_is_untouched(self):
        for sequences in ((digests('Something else.'),), (digests(*PLUG, 'A fourth plug line.'),)):
            with self.subTest(sequences=len(sequences[0])):
                session = skip_upsell_intro(Session(opening(*PLUG)), sequences)
                self.assertEqual((session.pending.name, session.pending.details['text']), ('dialogue', PLUG[0]))

    def test_the_longest_whole_sequence_wins_and_a_longer_partial_one_is_undone(self):
        # 11_0 April Fools' five lines are 10_8's first four plus "And now...": each stops where its own plug ends.
        shorter, longer = digests(*PLUG[:2]), digests(*PLUG[:2], 'A different third line.')
        session = skip_upsell_intro(Session(opening(*PLUG)), (longer, shorter))
        self.assertEqual((session.pending.name, session.pending.details['text']), ('dialogue', PLUG[2]))

    def test_the_table_has_the_owners_33_episodes_and_no_story_text(self):
        self.assertEqual(len(SEQUENCES), 15)
        self.assertTrue(all(len(line) == 16 and int(line, 16) >= 0 for lines in SEQUENCES for line in lines))
        self.assertEqual(max(len(lines) for lines in SEQUENCES), 7)


if __name__ == '__main__':
    unittest.main()
