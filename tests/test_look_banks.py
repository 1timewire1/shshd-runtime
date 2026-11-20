"""Claire Hart plan Stage 0, pack 31500 registered: look banks (CoD draws a look as 5 consecutive IDs, chc holds each picture
once), the frame backdrop and the category."""
import json
from types import SimpleNamespace
import unittest

from exp_runtime.content import EpisodeResources, legacy_fields, pack_setting


class Archive:
    def __init__(self, contents):
        self.contents = contents
        self.entries = set(contents)

    def read(self, resource):
        return self.contents[resource]


def resources(pack=31500, spec=True, own=None):
    looks = [[28100, 28101, 28100, 28102, 28103], [28200, 28200, 28200, 28200, 28200], [28300, 28301]]
    contents = {28100: b'claire 0', 28101: b'claire 1', 28102: b'claire 3', 28103: b'claire 4', 28200: b'troy',
                28300: b'short look', 28001: b'green'}
    if spec:
        contents[26998] = json.dumps(dict(looks=looks)).encode()
    chc = Archive(contents)
    library = SimpleNamespace(game_id='cod', addon=lambda name: (dict(revision=1), chc) if name == 'chc' else None)
    episode = object.__new__(EpisodeResources)
    episode.library, episode.record = library, dict(pack_id=pack, name='Case 1')
    episode.archive = Archive(own or {25001: b'script'})
    episode._presentation, episode._required_addons, episode._addon_archives = {}, (('chc', 1),), [chc]
    return episode


class LookBankTests(unittest.TestCase):
    def test_a_looks_five_ids_read_its_pictures_from_chc(self):
        episode = resources()
        self.assertEqual([episode._bank_read(30000 + e) for e in range(5)],
                         [b'claire 0', b'claire 1', b'claire 0', b'claire 3', b'claire 4'])
        self.assertEqual(episode._bank_read(30005 + 3), b'troy')                 # look 1 shares one picture
        self.assertTrue(episode.exists(30004))
        self.assertFalse(episode.exists(30010))                                  # look 2 isn't five pictures
        self.assertFalse(episode.exists(30015))                                  # no look 3
        self.assertEqual(episode._bank_read(28001), b'green')                    # chc's own IDs still reach it

    def test_the_episodes_own_picture_wins_and_other_packs_have_none(self):
        self.assertEqual(resources(own={30000: b'own'})._bank_read(30000), b'own')
        self.assertFalse(resources(pack=31400).exists(30000))
        self.assertFalse(resources(spec=False).exists(30000))

    def test_pack_31500_is_registered(self):
        episode = resources()
        self.assertEqual(pack_setting(episode, 'LOOK_BANKS'), ('chc', 26998, 30000))
        self.assertEqual(pack_setting(episode, 'TRANSLATED_FRAME_BACKDROP'), 28001)
        self.assertEqual(legacy_fields(['Case 1 (CHC)'], 'cod', 10),
                         dict(titles=['Case 1'], legacy='CHC', category='Claire Hart'))


if __name__ == '__main__':
    unittest.main()
