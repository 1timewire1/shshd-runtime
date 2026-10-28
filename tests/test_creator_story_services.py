"""Story services added to the creator for translated episodes, executed in the production VM and engine."""
import unittest

from exp_runtime.creator import Character, Choice, Node, Project, ProjectError, compile_project
from test_creator import image_bytes, session_for
from test_creator_coverage import services
from test_creator_features import sequence
from test_runtime import answer_screen


def with_cast(project, *names):
    """Reusable characters with real embedded portraits, so the engine presents them with their art."""
    for name in names:
        image = project.add_image(name, image_bytes())
        project.characters.append(Character(name.lower(), name, image.id))
    return project


def scenes(project):
    """The same story split into one scene per node, so variables live in the multi-scene property store."""
    for i, node in enumerate(project.nodes):
        node.scene = 25001 + i
    return project


class TextFormattingTests(unittest.TestCase):
    def story(self):
        return sequence(
            Node('points', 'set', variable='points', value=7),
            Node('score', 'score', params={'owner': 0, 'key': 400, 'operation': 'set', 'value': 42, 'result': 'score'}),
            Node('say', text='You have {points} points (100%), {points * 2} doubled, {prop(0, 400)} total. { :) }'),
            Node('ask', 'choice', text='Spend {points}?', options=[Choice('Spend {points - 2}', 'end'),
                                                                   Choice('Keep', 'end')]))

    def test_numbers_and_game_state_are_formatted_into_text(self):
        for split in (False, True):
            with self.subTest(scenes=split):
                p = self.story()
                s = session_for(scenes(p) if split else p)
                self.assertEqual(s.advance().details['text'],
                                 'You have 7 points (100%), 14 doubled, 42 total. { :) }')
                choice = answer_screen(s)
                self.assertEqual(choice.details['title'], '')
                self.assertEqual(choice.details['text'], 'Spend 7?')
                self.assertEqual(choice.details['options'], ['Spend 5', 'Keep'])

    def test_stored_text_names_and_unknown_braces_stay_literal(self):
        p = sequence(Node('input', 'input', params={'result': 'name'}), Node('hi', text='Hi {name}, {nobody}!'))
        s = session_for(p)
        s.advance()
        self.assertEqual(s.answer('Alex').details['text'], 'Hi Alex, {nobody}!')
        self.assertNotIn(0, services(compile_project(p)))  # Nothing to format: plain text references.

    def test_a_name_cannot_be_both_text_and_number(self):
        p = sequence(Node('input', 'input', params={'result': 'name'}),
                     Node('n', 'set', variable='name', value=1))
        with self.assertRaisesRegex(ProjectError, 'both a stored text and a number'):
            compile_project(p)


class GameStateExpressionTests(unittest.TestCase):
    def test_property_bit_and_art_reads_and_flag_writes(self):
        for split in (False, True):
            with self.subTest(scenes=split):
                p = with_cast(sequence(
                    Node('rel', 'relationship', character='alex', params={'operation': 'set', 'value': 3}),
                    Node('flag', 'flag', params={'owner': 0, 'key': 3010, 'bit': 4}),
                    Node('alex_flag', 'flag', character='alex', params={'key': 3011, 'bit': 0}),
                    Node('test', 'branch', params={'expression':
                         "prop('alex', 407) == 3 and bit(0, 3010, 4) and prop(0, 3010) == 16 "
                         "and bit('alex', 3011, 0) and not bit(0, 3010, 3) and art('alex') == 26000"},
                         next='yes', otherwise='no'),
                    Node('yes', text='Yes', next='end'), Node('no', text='No')), 'Alex')
                s = session_for(scenes(p) if split else p)
                self.assertEqual(s.advance().details['text'], 'Yes')
                self.assertEqual(s.engine.numbers[s.engine.number_key(0, 3010)], 16)

    def test_clearing_a_flag_and_unknown_or_reserved_owners(self):
        p = sequence(Node('on', 'flag', params={'key': 5, 'bit': 2}),
                     Node('off', 'flag', params={'key': 5, 'bit': 2, 'value': False}),
                     Node('say', text='{prop(0, 5)}'))
        self.assertEqual(session_for(p).advance().details['text'], '0')
        for expression, message in (("prop('ghost', 1)", 'unknown character'), ('prop(-30000, 1)', 'reserved')):
            with self.assertRaisesRegex(ProjectError, message):
                compile_project(sequence(Node('t', 'set', variable='x', params={'expression': expression})))


class SpeakerTests(unittest.TestCase):
    def test_player_and_narrator_characters_set_native_presentation(self):
        p = with_cast(sequence(
            Node('before', character='alex', text='Alex speaks'),
            Node('who', 'speakers', params={'player': 'alex', 'narrator': 'sam'}),
            Node('player', character='alex', text='Me'), Node('other', character='sam', text='Narration by Sam'),
            Node('narration', text='Plain narration'),
            Node('reset', 'speakers'), Node('after', text='Built-in narrator again')), 'Alex', 'Sam')
        for split in (False, True):
            with self.subTest(scenes=split):
                s = session_for(scenes(p) if split else p)
                self.assertEqual(s.advance().details['presentation_mode'], 2)
                player = answer_screen(s)
                self.assertEqual((player.details['presentation_mode'], player.details['speaker']), (1, 'Alex'))
                narrator = answer_screen(s)
                self.assertEqual((narrator.details['presentation_mode'], narrator.details['speaker']), (4, ''))
                plain = answer_screen(s)
                self.assertEqual((plain.details['character_id'], plain.details['presentation_mode']), (2, 4))
                self.assertEqual(answer_screen(s).details['character_id'], 0)
                self.assertEqual(s.engine.ui_defaults, {74: 0, 75: 0})


class StoredTextTests(unittest.TestCase):
    def test_shared_keys_set_text_and_defaults(self):
        p = sequence(Node('rank', 'set', variable='rank', value=9),
                     Node('zoe', 'text_default', text='Zoe', params={'key': '$ZOE'}),
                     Node('again', 'text_default', text='Zoey', params={'key': '$ZOE'}),
                     Node('villain', 'set_text', text='Mr. {rank}', params={'key': '$Antagonist'}),
                     Node('input', 'input', params={'result': '$USR'}),
                     Node('check', 'text_branch', params={'variable': '$USR', 'equals': 'Alex'}, next='hi', otherwise='end'),
                     Node('hi', text='$USR meets $ZOE and $Antagonist'))
        s = session_for(p)
        s.advance()
        self.assertEqual(s.answer('Alex').details['text'], 'Hi Alex, {nobody}!')
        self.assertNotIn(0, services(compile_project(p)))  # Nothing to format: plain text references.

    def test_a_name_cannot_be_both_text_and_number(self):
        p = sequence(Node('input', 'input', params={'result': 'name'}),
                     Node('n', 'set', variable='name', value=1))
        with self.assertRaisesRegex(ProjectError, 'both a stored text and a number'):
            compile_project(p)


class GameStateExpressionTests(unittest.TestCase):
    def test_property_bit_and_art_reads_and_flag_writes(self):
        for split in (False, True):
            with self.subTest(scenes=split):
                p = with_cast(sequence(
                    Node('rel', 'relationship', character='alex', params={'operation': 'set', 'value': 3}),
                    Node('flag', 'flag', params={'owner': 0, 'key': 3010, 'bit': 4}),
                    Node('alex_flag', 'flag', character='alex', params={'key': 3011, 'bit': 0}),
                    Node('test', 'branch', params={'expression':
                         "prop('alex', 407) == 3 and bit(0, 3010, 4) and prop(0, 3010) == 16 "
                         "and bit('alex', 3011, 0) and not bit(0, 3010, 3) and art('alex') == 26000"},
                         next='yes', otherwise='no'),
                    Node('yes', text='Yes', next='end'), Node('no', text='No')), 'Alex')
                s = session_for(scenes(p) if split else p)
                self.assertEqual(s.advance().details['text'], 'Yes')
                self.assertEqual(s.engine.numbers[s.engine.number_key(0, 3010)], 16)

    def test_clearing_a_flag_and_unknown_or_reserved_owners(self):
        p = sequence(Node('on', 'flag', params={'key': 5, 'bit': 2}),
                     Node('off', 'flag', params={'key': 5, 'bit': 2, 'value': False}),
                     Node('say', text='{prop(0, 5)}'))
        self.assertEqual(session_for(p).advance().details['text'], '0')
        for expression, message in (("prop('ghost', 1)", 'unknown character'), ('prop(-30000, 1)', 'reserved')):
            with self.assertRaisesRegex(ProjectError, message):
                compile_project(sequence(Node('t', 'set', variable='x', params={'expression': expression})))


class SpeakerTests(unittest.TestCase):
    def test_player_and_narrator_characters_set_native_presentation(self):
        p = with_cast(sequence(
            Node('before', character='alex', text='Alex speaks'),
            Node('who', 'speakers', params={'player': 'alex', 'narrator': 'sam'}),
            Node('player', character='alex', text='Me'), Node('other', character='sam', text='Narration by Sam'),
            Node('narration', text='Plain narration'),
            Node('reset', 'speakers'), Node('after', text='Built-in narrator again')), 'Alex', 'Sam')
        for split in (False, True):
            with self.subTest(scenes=split):
                s = session_for(scenes(p) if split else p)
                self.assertEqual(s.advance().details['presentation_mode'], 2)
                player = answer_screen(s)
                self.assertEqual((player.details['presentation_mode'], player.details['speaker']), (1, 'Alex'))
                narrator = answer_screen(s)
                self.assertEqual((narrator.details['presentation_mode'], narrator.details['speaker']), (4, ''))
                plain = answer_screen(s)
                self.assertEqual((plain.details['character_id'], plain.details['presentation_mode']), (2, 4))
                self.assertEqual(answer_screen(s).details['character_id'], 0)
                self.assertEqual(s.engine.ui_defaults, {74: 0, 75: 0})


class StoredTextTests(unittest.TestCase):
    def test_shared_keys_set_text_and_defaults(self):
        p = sequence(Node('zoe', 'text_default', text='Zoe', params={'key': '$ZOE'}),
                     Node('again', 'text_default', text='Zoey', params={'key': '$ZOE'}),
                     Node('villain', 'set_text', text='Mr. {rank}', params={'key': '$Antagonist'}),
                     Node('rank', 'set', variable='rank', value=9, next='input'),
                     Node('input', 'input', params={'result': '$USR'}),
                     Node('check', 'text_branch', params={'variable': '$USR', 'equals': 'Alex'}, next='hi', otherwise='end'),
                     Node('hi', text='$USR meets $ZOE and $Antagonist'))
        p.nodes.insert(0, p.nodes.pop(3))  # The rank is set before the villain's name is formatted.
        p.nodes[0].next, p.start = 'zoe', 'rank'
        p.nodes[3].next = 'input'
        s = session_for(p)
        s.advance()
        self.assertEqual(s.answer('Alex').details['text'], 'Alex meets Zoe and Mr. 9')
        self.assertEqual({key: s.engine.strings[key] for key in ('$USR', '$ZOE', '$Antagonist')},
                         {'$USR': 'Alex', '$ZOE': 'Zoe', '$Antagonist': 'Mr. 9'})

    def test_invalid_shared_keys_are_rejected(self):
        for key in ('$', '$A B', '{x}', ''):
            with self.subTest(key=key), self.assertRaisesRegex(ProjectError, 'stored text'):
                compile_project(sequence(Node('n', 'set_text', text='x', params={'key': key})))


class CharacterChangeTests(unittest.TestCase):
    def test_default_expressions_art_and_names_change_mid_episode(self):
        p = with_cast(sequence(
            Node('default', 'expression_default', character='alex', expression=2),
            Node('uses', character='alex', expression=-1, text='Default'),
            Node('explicit', character='alex', expression=4, text='Explicit'),
            Node('rename', 'character_name', character='alex', text='alex the great', params={'capitalize': True}),
            Node('art', 'character_art', character='alex', asset=26005),
            Node('after', character='alex', expression=-1, text='Renamed')), 'Alex', 'Costume')
        s = session_for(p)
        self.assertEqual(s.advance().details['expression'], 2)
        self.assertEqual(answer_screen(s).details['expression'], 4)
        after = answer_screen(s)
        self.assertEqual((after.details['speaker'], after.details['expression']), ('Alex The Great', 2))
        self.assertEqual(s.engine.character_art_bases[1], 26005)

    def test_portrait_picker_copies_the_chosen_look(self):
        p = with_cast(sequence(
            Node('pick', 'picker', text='Choose your look', character='you',
                 params={'characters': ['look_a', 'look_b'], 'result': 'look'}),
            Node('say', text='Look {look}')), 'You', 'Look_A', 'Look_B')
        s = session_for(p)
        action = s.advance()
        self.assertEqual((action.name, action.details['text']), ('character_picker', 'Choose your look'))
        self.assertEqual(s.engine.character_picker.characters, [2, 3])
        s.answer(1)
        self.assertEqual(answer_screen(s).details['text'], 'Look 1')
        self.assertEqual(s.engine.character_art_bases[1], s.engine.character_art_bases[3])

    def test_embedded_music_and_sound_effects(self):
        from exp_runtime.creator.native import import_exp
        from exp_runtime.exp import ExpArchive
        mp3, wav = b'ID3\x04\0\0\0\0\0\0' + b'\xff\xfb\x90\x00' * 8, b'RIFF\x24\0\0\0WAVEfmt ' + bytes(28)
        p = sequence(Node('music', 'music'), Node('sound', 'sound'), Node('say', text='Listen'))
        song, effect = p.add_audio('Theme.mp3', mp3), p.add_audio('Door.wav', wav)
        p.nodes[0].params, p.nodes[1].params = {'resource': song.id, 'loop': True}, {'resource': effect.id}
        data = compile_project(p)
        self.assertEqual((ExpArchive(data).read(song.id), ExpArchive(data).read(effect.id)), (mp3, wav))
        s = session_for(p)
        s.advance()
        self.assertEqual((s.engine.music_id, s.engine.sound_id), (song.id, effect.id))
        self.assertEqual([a.data for a in import_exp(data).assets], [mp3, wav])
        # shshd-runtime: embedded music may be a WAV too (the X360 prototype's own tracks); one not embedded may not.
        wav_music = sequence(Node('a', 'music', params={'resource': effect.id, 'loop': True}))
        wav_music.assets = list(p.assets)
        compile_project(wav_music)
        for node, params, message in ((0, {'resource': 26999}, 'embedded MP3 or WAV'),
                                      (1, {'resource': 26999}, 'Embed the sound effect')):
            broken = sequence(Node('a', p.nodes[0].kind if node == 0 else 'sound', params=params))
            broken.assets = list(p.assets)
            with self.subTest(message=message), self.assertRaisesRegex(ProjectError, message):
                compile_project(broken)
        background = sequence(Node('bg', 'background', asset=song.id))
        background.assets = list(p.assets)
        with self.assertRaisesRegex(ProjectError, 'audio, not an image'):
            compile_project(background)
        with self.assertRaisesRegex(ProjectError, 'MP3 or WAV'):
            p.add_audio('Picture.png', image_bytes())

    def test_vibrate(self):
        s = session_for(sequence(Node('buzz', 'vibrate'), Node('say', text='Done')))
        s.advance()
        self.assertEqual(s.engine.vibration_serial, 1)


class RemainingServiceTests(unittest.TestCase):
    def test_append_text_concatenates_a_stored_text(self):
        p = sequence(Node('first', 'set_text', text='Mr.', params={'key': '$Title'}),
                     Node('more', 'append_text', text=' Doom {rank}', params={'key': '$Title'}),
                     Node('again', 'append_text', text='!', params={'key': '$Title'}),
                     Node('fresh', 'append_text', text='new', params={'key': 'empty'}),
                     Node('say', text='$Title / {empty}'))
        p.nodes.insert(0, Node('rank', 'set', variable='rank', value=3, next='first'))
        p.start = 'rank'
        for split in (False, True):
            with self.subTest(scenes=split):
                s = session_for(scenes(p) if split else p)
                self.assertEqual(s.advance().details['text'], 'Mr. Doom 3! / new')

    def test_build_query_loading_screen_and_links(self):
        p = sequence(Node('wait', 'loading'), Node('link', 'open_url', params={'url': 'https://example.com/story'}),
                     Node('say', text='{build(9)} {build(10)} {build(3)}'))
        s = session_for(p)
        self.assertEqual(s.advance().name, 'loading')
        action = s.tick(3001)
        self.assertEqual(action.details['text'], '1 0 6')
        self.assertEqual(s.engine.store_link, 'https://example.com/story')
        for expression in ('build(11)', 'build(x)'):
            with self.subTest(expression=expression), self.assertRaisesRegex(ProjectError, 'selectors'):
                compile_project(sequence(Node('t', 'set', variable='x', params={'expression': expression})))

    def test_football_home_and_away_scores(self):
        p = sequence(Node('game', 'football', params={'home_result': 'home', 'away_result': 'away'}),
                     Node('say', text='{home}-{away} ({football_margin})'))
        s = session_for(p)
        self.assertEqual(s.advance().name, 'football')
        for _ in range(1000):
            if s.pending.name != 'football':
                break
            s.tick(1000)
            if s.pending.name == 'football':
                s.answer(None)
        home, away = s.engine.football_scores
        self.assertEqual(s.pending.details['text'], f'{home}-{away} ({home - away})')

    def test_survey_sends_the_hd_frame_and_continues_offline(self):
        from exp_runtime.creator.compiler import SURVEY_FAILURE
        from exp_runtime.shs.survey import CONNECTION_ERROR
        self.assertEqual(SURVEY_FAILURE, CONNECTION_ERROR)
        p = sequence(Node('rate', 'set', variable='rating', value=4),
                     Node('send', 'survey', params={'poll_id': 12000, 'answers': ['rating', 'rating * 2'],
                                                    'results': ['first', 'second']}),
                     Node('say', text='After the survey {first}'))
        s = session_for(p)
        action = s.advance()
        self.assertEqual(action.name, 'survey_confirmation')
        request = s.vm.pending
        self.assertEqual(request.args[:5], (12000, 2, request.args[2], 2, 2))
        self.assertEqual(request.args[6], 2)
        self.assertEqual([s.vm.read_word(request.args[2] + i) for i in range(2)], [4, 8])
        s.tick(1001)                                    # the local receipt's reading time
        self.assertEqual(answer_screen(s).details['text'], 'After the survey 0')     # no results came back offline
        for node in (Node('a', 'survey'), Node('a', 'loading')):
            with self.subTest(kind=node.kind), self.assertRaisesRegex(ProjectError, 'CoD game has no'):
                compile_project(sequence(node, game='cod'))


if __name__ == '__main__':
    unittest.main()
