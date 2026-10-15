"""The High School Story ad's choice (ad_intro.py) and the thumbnail pipeline's handling of it."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from exp_runtime import episode_thumbnails
from exp_runtime.ad_intro import play_option

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
