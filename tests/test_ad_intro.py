"""The High School Story ad's choice (ad_intro.py) and the thumbnail pipeline's handling of it."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from exp_runtime import episode_thumbnails
from exp_runtime.ad_intro import play_option, skip_ad_intro
from exp_runtime.runtime import Session
from test_runtime import Resources, host_call, text_words
from test_vm import program

OPTIONS = ['Go to the High School Story app!', 'See a sneak peek of High School Story!',
           'Play the Surviving High School episode!']


def choice(options, enabled=None):
    return SimpleNamespace(name='choice', details=dict(options=options, enabled=enabled or [True] * len(options)))


class AdChoiceTests(unittest.TestCase):
    def test_the_play_option_is_found_wherever_it_sits(self):
        self.assertEqual(play_option(choice(OPTIONS)), 2)
        # After the sneak peek the second option is gone.
        self.assertEqual(play_option(choice([OPTIONS[0], OPTIONS[2]])), 1)

    def test_other_screens_and_choices_have_none(self):
        self.assertIsNone(play_option(choice(['Working out.', 'Watching TV.'])))
        self.assertIsNone(play_option(SimpleNamespace(name='dialogue', details={})))
        self.assertIsNone(play_option(None))
        self.assertIsNone(play_option(choice(OPTIONS, [True, True, False])))


class SkipAdIntroTests(unittest.TestCase):
    @staticmethod
    def story(*episode):
        """The ad (Autumn's line, the three-option choice, the narrator's "And now..."), then `episode`'s screens."""
        words, refs = text_words('Hey, everyone! Autumn here!', 'Choose', '|'.join(OPTIONS), 'Check it out?',
                                 'And now...', 'Previously, on `Surviving High School...`', 'Game of Cones', 'Story.')
        intro, title, options, prompt, and_now, recap, card, line = refs
        screens = {'recap': host_call(13, recap, 0), 'card': host_call(8, card, card, -1, 0),
                   'line': host_call(13, line, 0)}
        return Resources(program(*host_call(13, intro, 0), *host_call(1, title, options, prompt, 0, -1, -1, -1, 0),
                                 *host_call(13, and_now, 0), *(word for name in episode for word in screens[name]),
                                 0x33, words=words))

    def test_the_ad_is_played_through_to_the_title_card(self):
        # The choice ignores taps for its first 250 ms (Session.choice_ready, from exp-runtime v0.6.0): answering at
        # once left the skip stuck on it, so the ad played as if the setting were off.
        session = skip_ad_intro(Session(self.story('card', 'line')))
        self.assertEqual(session.pending.name, 'presentation')

    def test_a_recap_after_the_ads_and_now_is_kept(self):
        # Game of Cones: "And now..." ends the ad; the episode's "Previously, on..." recap comes before its title card.
        session = skip_ad_intro(Session(self.story('recap', 'card', 'line')))
        self.assertEqual((session.pending.name, session.pending.details['text']),
                         ('dialogue', 'Previously, on `Surviving High School...`'))


class ThumbnailMarkerTests(unittest.TestCase):
    def test_an_older_no_title_card_marker_is_tried_again(self):
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / 'episode.none'
            self.assertFalse(episode_thumbnails.marked(marker))
            marker.write_bytes(b'')                     # the first pipeline's marker
            self.assertFalse(episode_thumbnails.marked(marker))
            marker.write_bytes(episode_thumbnails.MARKER)
            self.assertTrue(episode_thumbnails.marked(marker))


if __name__ == '__main__':
    unittest.main()
