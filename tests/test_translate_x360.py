"""tools/translate x360.py and lua_subset.py on authored data (no prototype content): the pak and string encodings,
the Lua subset, and a small story played through the production Session."""
import importlib.util
import io
import lzma
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools' / 'translate'))
import lua_subset  # noqa: E402

HAS_PIL = importlib.util.find_spec('PIL') is not None


def encode_wc(text):
    digits = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789*+'
    return 'WC' + ''.join(digits[ord(c) & 63] + digits[ord(c) >> 6 & 63] + digits[ord(c) >> 12 & 63] for c in text)


def pak(files):
    table, blobs = b'', []
    names = list(files)
    body = [lzma.compress(files[n], format=lzma.FORMAT_ALONE) for n in names]
    table_size = sum(12 + len(n) for n in names)
    offset = 26 + table_size
    for name, blob in zip(names, body):
        table += struct.pack('<III', offset, len(blob), len(name)) + name.encode()
        offset += len(blob)
    return b'tongas_pack_v20000' + struct.pack('<II', len(names), table_size) + table + b''.join(body)


class LuaSubsetTests(unittest.TestCase):
    def test_statements_comments_and_strings(self):
        block = lua_subset.parse('--[[ long\ncomment ]]\nx.y = 1 + 2 * 3 -- tail\n'
                                 'if a == true then f("s", [[raw]]) elseif not b then g() else h() end\n'
                                 'obj:method(1)\nlocal t = {1, k = "v"}\n')
        self.assertEqual(block[0], ('assign', [('field', ('name', 'x'), 'y')],
                                    [('binop', '+', ('num', 1.0), ('binop', '*', ('num', 2.0), ('num', 3.0)))]))
        self.assertEqual(block[1][0], 'if')
        self.assertEqual(len(block[1][1]), 2)
        self.assertEqual(block[1][1][0][1][0][1][2], [('str', 's'), ('str', 'raw')])
        self.assertEqual(block[2], ('call', ('method', ('name', 'obj'), 'method', [('num', 1.0)])))
        self.assertEqual(block[3][0], 'local')

    def test_concatenation_is_right_associative_and_dotted_reads_string_indexes(self):
        expr = lua_subset.parse('x = "a" .. "b" .. "c"')[0][2][0]
        self.assertEqual(expr, ('binop', '..', ('str', 'a'), ('binop', '..', ('str', 'b'), ('str', 'c'))))
        target = lua_subset.parse('scene["props/car"].Opacity = 1')[0][1][0]
        self.assertEqual(lua_subset.dotted(target), 'scene.props/car.Opacity')

    def test_a_syntax_error_is_reported(self):
        with self.assertRaises(lua_subset.LuaSyntaxError):
            lua_subset.parse('renderer.ResetRenderPasses\n')


@unittest.skipUnless(HAS_PIL, 'x360.py draws backgrounds with Pillow')
class X360StoryTests(unittest.TestCase):
    EVENTS = '''<Tongas project="t">
    <object key="_a" type="EVENTCONFIGMASTER" name="t/one" version="1"><properties key="_a">
    <p k="_a" n="LocationName">lot</p><p k="_a" n="Script" l="lua"><![CDATA[
gameStats = {}
gameStats.score = 0
gameStats.flag = false
OpenDialog("a",0)
scene.a.CreateFx("hud/emoticon/love")
DialogText("t/hello")
CloseDialog()
gameSHS.ClearChoices()
gameSHS.AddChoices(ToUniString("[:t/yes]"),"","gameSHS.SetCharacterEmotion('a','happy')","gameStats.choice = 0")
gameSHS.AddChoices(ToUniString("[:t/no]"),"","gameSHS.SetCharacterEmotion('a','angry')","gameStats.choice = 1")
if gameStats.flag then
    gameSHS.AddChoices(ToUniString("[:t/secret]"),"","","gameStats.choice = 2")
end
gameSHS.OpenChoice("x","y",0)
if gameStats.choice == 0 then
    gameStats.score = gameStats.score + 2
    OpenDialog("a",1)
    DialogText("t/glad")
    CloseDialog()
elseif gameStats.choice == 1 then
    OpenDialog("a",6)
    DialogText("t/sad")
    CloseDialog()
end
game.RunEvent("t/two")
]]></p></properties></object>
    <object key="_b" type="EVENTCONFIGMASTER" name="t/two" version="1"><properties key="_b">
    <p k="_b" n="LocationName">lot</p><p k="_b" n="Script" l="lua"><![CDATA[
OpenDialog("",8)
if gameStats.score >= 2 then
    DialogText("t/won")
end
CloseDialog()
GuiScreen.AddControl("gameover","GGRP:hud/gameover/main",CreateV2(0,0),"100")
GuiScreen.gameover.main.gameovertext.Text = ToUniString("[:t/end]")
]]></p></properties></object></Tongas>'''
    STRINGS = {'t/hello': '&:130 180 80;Hi <:str,a>!', 't/yes': 'Say `yes`', 't/no': 'Say no', 't/secret': 'Secret',
               't/glad': 'Glad you said yes.', 't/sad': 'Oh well…', 't/won': 'You scored.', 't/end': 'The end',
               'a': '<:color,1 2 3><:font,1>Andy<:font,0>'}

    def prototype(self):
        import x360
        strings = ''.join(f'<object key="_s{i}" type="UNISTRINGSMASTER" name="{k}" version="1"><properties key="_s{i}">'
                          f'<p k="_s{i}" n="Text">{encode_wc(v)}</p></properties></object>'
                          for i, (k, v) in enumerate(self.STRINGS.items()))
        files = {'data/templates/unistrings.wxr': f'<Tongas project="t">{strings}</Tongas>'.encode(),
                 'data/templates/eventconfig.wxr': self.EVENTS.encode(),
                 'data/templates/guilabel.wxr': b'<Tongas project="t"></Tongas>'}
        return x360.Prototype(pak(files))

    def test_pak_and_text_decoding(self):
        import x360
        proto = self.prototype()
        self.assertEqual(proto.text('t/hello'), '&:130 180 80;Hi `Andy`!')     # an inserted name: emphasis colour
        self.assertEqual(x360.story_text(proto.text('t/hello')), 'Hi `Andy`!')
        self.assertEqual(x360.story_text('Say `yes`', label=True), 'Say yes')
        self.assertEqual(x360.story_text(proto.text('t/sad')), 'Oh well...')
        self.assertEqual(x360.story_text('Yeah, maybe . . . '), 'Yeah, maybe...')
        self.assertEqual(x360.story_text('. . . so I didn\'t go in.'), '...so I didn\'t go in.')
        self.assertEqual(x360.story_text('With Ryan, I . . . well . . . no'), 'With Ryan, I ... well ... no')

    def test_a_story_plays_its_choices_conditions_and_end_card(self):
        import x360
        from exp_runtime.creator import compile_project
        from PIL import Image
        from playthrough import play

        class Art:
            def background(self, location, mode):
                return Image.new('RGB', (12, 4), (10, 20, 30))

            def backdrop(self):
                return None

        story = x360.Story('Test', 1, ['t/one'], [x360.Cast('a', 'Andy', 1, bank=2050)], {'lot': 23}, player='a')
        project = x360.translate(self.prototype(), story, Art())
        options = [n for n in project.nodes if n.kind == 'choice'][0].options
        self.assertEqual([(o.text, o.condition) for o in options],
                         [('Say yes', ''), ('Say no', ''), ('Secret', 'flag')])
        data = compile_project(project)
        lines = lambda record: [e['text'] for e in record if e['kind'] in ('line', 'message')]  # noqa: E731
        first = play(data, [0])
        self.assertEqual(lines(first), ['Hi `Andy`!', 'Glad you said yes.', 'You scored.', 'The end'])
        self.assertEqual([e['expression'] for e in first if e['kind'] == 'line'][:2], [0, 2])   # yes: happy
        self.assertEqual(first[-1]['kind'], 'exit')
        self.assertEqual(lines(play(data, [2])), lines(first))     # "Secret" is locked: the first answer plays
        self.assertEqual(lines(play(data, [1])), ['Hi `Andy`!', '{ Oh well... {', 'The end'])     # sung: SHS's notes
        # The emoticon is set just before its line and cleared after; the cast's SHS badges are hidden.
        kinds = [(n.kind, n.params.get('key'), n.params.get('value')) for n in project.nodes
                 if n.kind in ('score', 'dialogue')][:3]
        self.assertEqual(kinds, [('score', x360.EFFECT_KEY, 4), ('dialogue', None, None), ('score', x360.EFFECT_KEY, 0)])
        badges = [n for n in project.nodes if n.kind == 'relationship']
        self.assertEqual([(n.character, n.params['hide'], n.params['value']) for n in badges], [('a', True, 0)])

    def test_ima_adpcm_sounds_decode_to_pcm(self):
        import x360
        # One mono IMA ADPCM block (header: first sample 100, step index 0) with four nibbles of +1 steps.
        block = struct.pack('<hBx', 100, 0) + bytes([0x11, 0x11])
        fmt = struct.pack('<HHIIHH', 0x11, 1, 22050, 11100, len(block), 4) + struct.pack('<HH', 2, 5)
        wav = (b'RIFF' + struct.pack('<I', 4 + 8 + len(fmt) + 8 + len(block)) + b'WAVEfmt ' + struct.pack('<I', len(fmt))
               + fmt + b'data' + struct.pack('<I', len(block)) + block)
        pcm = x360.pcm_wav(wav)
        self.assertEqual(pcm[20:22], struct.pack('<H', 1))                      # PCM
        samples = struct.unpack('<5h', pcm[44:54])
        self.assertEqual(samples[0], 100)
        self.assertTrue(all(b > a for a, b in zip(samples, samples[1:])))       # each +1 nibble climbs

    def test_an_intro_and_its_loop_are_embedded_and_only_the_intro_is_started(self):
        # The prototype's own music (--music-file): dont_trust_me runs into dont_trust_me_loop by itself in the runtime
        # (shs profile TRANSLATED_MUSIC_LOOPS), so the story's later switch to the loop cue is not a second request.
        import x360
        from exp_runtime.shs.profile import TRANSLATED_MUSIC_LOOPS
        self.assertEqual(TRANSLATED_MUSIC_LOOPS[x360.PACK_ID], {x360.MUSIC_INTRO: x360.MUSIC_LOOP})
        music = {}
        assets, chained = x360.music_assets({'dont_trust_me': b'intro', 'dont_trust_me_loop': b'loop',
                                             'chilled': b'chill'}, music)
        self.assertEqual({a.id: a.data for a in assets}, {x360.MUSIC_INTRO: b'intro', x360.MUSIC_LOOP: b'loop',
                                                          x360.MUSIC_OTHER: b'chill'})
        self.assertEqual((music, chained), ({'dont_trust_me': x360.MUSIC_INTRO, 'chilled': x360.MUSIC_OTHER},
                                            {'dont_trust_me_loop'}))
        self.EVENTS = self.EVENTS.replace('OpenDialog("a",0)', 'scene.level.Resources[0] = "SNFX:music/dont_trust_me"\n'
                                          'OpenDialog("a",0)', 1).replace(
            'game.RunEvent("t/two")', 'scene.level.Resources[0] = "SNFX:music/dont_trust_me_loop"\n'
            'game.RunEvent("t/two")', 1)

        class Art:
            def background(self, location, mode):
                from PIL import Image
                return Image.new('RGB', (12, 4), (10, 20, 30))

            def backdrop(self):
                return None

        story = x360.Story('Test', 1, ['t/one'], [x360.Cast('a', 'Andy', 1, bank=2050)], {'lot': 23}, player='a',
                           own_music=True)
        project = x360.translate(self.prototype(), story, Art(),
                                 music_files={'dont_trust_me': b'intro', 'dont_trust_me_loop': b'loop'})
        self.assertEqual([n.params for n in project.nodes if n.kind == 'music'],
                         [{'resource': x360.MUSIC_INTRO, 'loop': True}])
        self.assertEqual({a.id for a in project.assets} >= {x360.MUSIC_INTRO, x360.MUSIC_LOOP}, True)
        # A story without music of its own (Puzzle Test, Dating Beth) leaves the files out, built alongside.
        story.own_music = False
        project = x360.translate(self.prototype(), story, Art(),
                                 music_files={'dont_trust_me': b'intro', 'dont_trust_me_loop': b'loop'})
        self.assertFalse({a.id for a in project.assets} & {x360.MUSIC_INTRO, x360.MUSIC_LOOP})

    def test_the_puzzle_plays_after_its_event_where_the_switch_is_on_and_is_skipped_where_not(self):
        import x360
        from exp_runtime.creator import compile_project
        from playthrough import play
        self.EVENTS = '''<Tongas project="t">
    <object key="_a" type="EVENTCONFIGMASTER" name="t/one" version="1"><properties key="_a">
    <p k="_a" n="LocationName">lot</p><p k="_a" n="Script" l="lua"><![CDATA[
gameSHS.OpenDialog("a","bubbles/talk/left","bubbles/enter_from_left")
gameSHS.SetDialogText("t/glad",20)
gameSHS.CloseDialog("bubbles/exit_from_left")
]]></p></properties></object>
    <object key="_b" type="EVENTCONFIGMASTER" name="t/two" version="1"><properties key="_b">
    <p k="_b" n="LocationName">lot</p><p k="_b" n="Script" l="lua"><![CDATA[
gameSHS.OpenDialog("a","bubbles/talk/left","bubbles/enter_from_left")
gameSHS.SetDialogText("t/won",20)
gameSHS.CloseDialog("bubbles/exit_from_left")
QuitGame()
]]></p></properties></object></Tongas>'''

        class Art:
            def background(self, location, mode):
                from PIL import Image
                return Image.new('RGB', (12, 4), (10, 20, 30))

            def backdrop(self):
                return None

        story = x360.Story('Test', 1, ['t/one', 't/two'], [x360.Cast('a', 'Andy', 1, bank=2050)], {'lot': 23}, player='a',
                           puzzle_after='t/one')
        data = compile_project(x360.translate(self.prototype(), story, Art()))
        real = [event for event in play(data) if event['kind'] in ('line', 'x360_puzzle')]
        self.assertEqual([event.get('text', event['kind']) for event in real],
                         ['Glad you said yes.', 'x360_puzzle', 'You scored.'])
        timed = [event for event in play(data, arena=False) if event['kind'] in ('line', 'x360_puzzle')]
        self.assertEqual([event.get('text', event['kind']) for event in timed], ['Glad you said yes.', 'You scored.'])

    def test_the_leash_plays_real_where_the_switch_is_on_and_as_timed_choices_where_not(self):
        import x360
        from exp_runtime.creator import compile_project
        from playthrough import play
        self.EVENTS = '''<Tongas project="t">
    <object key="_a" type="EVENTCONFIGMASTER" name="t/one" version="1"><properties key="_a">
    <p k="_a" n="LocationName">lot</p><p k="_a" n="Script" l="lua"><![CDATA[
gameStats = {}
gameStats.choice = 0
gameSHS.RunSmashButtonMinigame("g", 50, 7, 12, math.random(2,5), 13, "w", "l", "i", "d")
if gameStats.choice == 1 then
    gameSHS.OpenDialog("a","bubbles/talk/left","bubbles/enter_from_left")
    gameSHS.SetDialogText("t/won",20)
    gameSHS.CloseDialog("bubbles/exit_from_left")
else
    gameSHS.OpenDialog("a","bubbles/talk/left","bubbles/enter_from_left")
    gameSHS.SetDialogText("t/sad",20)
    gameSHS.CloseDialog("bubbles/exit_from_left")
end
QuitGame()
]]></p></properties></object></Tongas>'''

        class Art:
            def background(self, location, mode):
                from PIL import Image
                return Image.new('RGB', (12, 4), (10, 20, 30))

            def backdrop(self):
                return None

        story = x360.Story('Test', 1, ['t/one'], [x360.Cast('a', 'Andy', 1, bank=2050)], {'lot': 23}, player='a')
        data = compile_project(x360.translate(self.prototype(), story, Art()))
        real = play(data)                                       # (the bot shakes as it's asked)
        self.assertIn('x360_leash', [event['kind'] for event in real])
        self.assertNotIn('word_game', [event['kind'] for event in real])
        self.assertIn('You scored.', [event.get('text') for event in real])
        timed = play(data, arena=False)
        self.assertIn('word_game', [event['kind'] for event in timed])
        self.assertNotIn('x360_leash', [event['kind'] for event in timed])
        self.assertIn('Oh well...', [event.get('text') for event in timed])

    def test_the_slot_machine_plays_real_where_the_switch_is_on_and_as_timed_choices_where_not(self):
        # Service 70's query picks. The real one's points are the script's own; the word game's map onto them.
        import x360
        from exp_runtime.creator import compile_project
        from playthrough import play
        self.EVENTS = '''<Tongas project="t">
    <object key="_a" type="EVENTCONFIGMASTER" name="t/one" version="1"><properties key="_a">
    <p k="_a" n="LocationName">lot</p><p k="_a" n="Script" l="lua"><![CDATA[
gameStats = {}
gameStats.choice = 0
gameSHS.RunSlotMachineMinigame("g", "e", "t", 0.5, 15, 1.4)
if gameStats.choice >= 3 then
    gameSHS.OpenDialog("a","bubbles/talk/left","bubbles/enter_from_left")
    gameSHS.SetDialogText("t/won",20)
    gameSHS.CloseDialog("bubbles/exit_from_left")
end
if gameStats.choice <= 1 then
    gameSHS.OpenDialog("a","bubbles/talk/left","bubbles/enter_from_left")
    gameSHS.SetDialogText("t/sad",20)
    gameSHS.CloseDialog("bubbles/exit_from_left")
end
QuitGame()
]]></p></properties></object></Tongas>'''

        class Art:
            def background(self, location, mode):
                from PIL import Image
                return Image.new('RGB', (12, 4), (10, 20, 30))

            def backdrop(self):
                return None

        story = x360.Story('Test', 1, ['t/one'], [x360.Cast('a', 'Andy', 1, bank=2050)], {'lot': 23}, player='a')
        data = compile_project(x360.translate(self.prototype(), story, Art()))
        real = play(data)                                       # (the bot takes every bulb)
        self.assertIn('x360_slot', [event['kind'] for event in real])
        self.assertNotIn('word_game', [event['kind'] for event in real])
        self.assertIn('You scored.', [event.get('text') for event in real])
        timed = play(data, arena=False)
        self.assertIn('word_game', [event['kind'] for event in timed])
        self.assertNotIn('x360_slot', [event['kind'] for event in timed])
        self.assertIn('Oh well...', [event.get('text') for event in timed])    # the word game runs out at 0
        # Its bulbs part where the word game's score does: 5, 3-4, and 2 or fewer.
        from exp_runtime.choice_hints import x360_slot_outcomes
        from playthrough import session as start
        s = start(data)
        action = s.advance()
        for _ in range(50):
            if action.name == 'x360_slot':
                break
            action = s.tick(1000)
        self.assertEqual([outcome[0] for outcome in x360_slot_outcomes(s)], [0, 3, 5])

    def audio_art(self):
        class Art:
            def background(self, location, mode):
                from PIL import Image
                return Image.new('RGB', (12, 4), (10, 20, 30))

            def backdrop(self):
                return None
        return Art()

    def test_a_levels_track_starts_on_arrival_if_the_pak_has_its_files(self):
        from unittest.mock import patch
        import x360
        story = x360.Story('Test', 1, ['t/one'], [x360.Cast('a', 'Andy', 1, bank=2050)], {'lot': 23}, player='a',
                           level_music={'lot': 'freedom'})
        project = x360.translate(self.prototype(), story, self.audio_art())     # no files: no cue, nothing embedded
        self.assertFalse([n for n in project.nodes if n.kind == 'music'])
        proto = self.prototype()
        proto.files['data/sound/music/freedom.ogg'] = b'ogg'
        with patch.object(x360, 'mix_track', return_value=b'mp3') as mix:
            project = x360.translate(proto, story, self.audio_art())
        mix.assert_called_once_with(proto.files, 'freedom')
        self.assertEqual([n.params for n in project.nodes if n.kind == 'music'],
                         [{'resource': x360.MIXES['freedom'][0], 'loop': True}] * 2)    # t/two is the same place: SHS
        self.assertEqual({a.id: a.data for a in project.assets}[x360.MIXES['freedom'][0]], b'mp3')  # plays it on

    def test_a_script_cue_takes_over_from_the_pair_and_the_loop_comes_back_after_it(self):
        from unittest.mock import patch
        import x360
        self.EVENTS = self.EVENTS.replace('OpenDialog("a",0)', 'scene.level.Resources[0] = "SNFX:music/dont_trust_me"\n'
                                          'OpenDialog("a",0)', 1).replace(
            'OpenDialog("a",1)', 'scene.level.Resources[1] = "SNFX:music/jumparound"\nOpenDialog("a",1)', 1).replace(
            'DialogText("t/glad")\n    CloseDialog()',
            'DialogText("t/glad")\n    CloseDialog()\n    scene.level.Resources[1] = "SNFX:music/dont_trust_me_loop"', 1)
        story = x360.Story('Test', 1, ['t/one'], [x360.Cast('a', 'Andy', 1, bank=2050)], {'lot': 23}, player='a',
                           own_music=True, script_music={'jumparound': 'jumparound'})
        proto = self.prototype()
        for path, _ in x360.MIXES['jumparound'][1]:
            proto.files[path] = b'x'
        with patch.object(x360, 'mix_track', return_value=b'mp3'):
            project = x360.translate(proto, story, self.audio_art(),
                                     music_files={'dont_trust_me': b'intro', 'dont_trust_me_loop': b'loop'})
        self.assertEqual([n.params['resource'] for n in project.nodes if n.kind == 'music'],
                         [x360.MUSIC_INTRO, x360.MIXES['jumparound'][0], x360.MUSIC_LOOP])

    def test_a_level_or_camera_effect_that_is_a_sound_plays_and_others_dont(self):
        from unittest.mock import patch
        import x360
        self.EVENTS = self.EVENTS.replace('OpenDialog("a",0)', 'scene.level.CreateFx("sound/whip")\n'
                                          'camera.CreateFx("generic/disaster")\nscene.level.CreateFx("sound/bubble")\n'
                                          'OpenDialog("a",0)', 1)
        story = x360.Story('Test', 1, ['t/one'], [x360.Cast('a', 'Andy', 1, bank=2050)], {'lot': 23}, player='a')
        proto = self.prototype()
        proto.files['data/sound/fx/dbp_fail.wav'] = b'fail'
        proto.files['data/sound/fx/whip.wav'] = b'whip'             # the opening's, which waits for its cutscene
        with patch.object(x360, 'pcm_wav', side_effect=lambda data: data + b' pcm'):
            project = x360.translate(proto, story, self.audio_art())
        resource = x360.SCRIPT_SOUNDS['generic/disaster'][1]
        self.assertEqual([n.params['resource'] for n in project.nodes if n.kind == 'sound'], [resource])
        self.assertEqual({a.id: a.data for a in project.assets}[resource], b'fail pcm')

    def test_a_dialogue_closing_plays_the_zip_once_and_a_notice_still_goes_ahead_of_its_last_line(self):
        from unittest.mock import patch
        import x360
        story = x360.Story('Test', 1, ['t/one'], [x360.Cast('a', 'Andy', 1, bank=2050)], {'lot': 23}, player='a')
        self.EVENTS = self.EVENTS.replace('DialogText("t/hello")\nCloseDialog()',
                                          'DialogText("t/hello")\nCloseDialog()\nOpenDialog("a",0)\nCloseDialog()\n'
                                          'gameStats.check1 = true', 1)
        proto = self.prototype()
        project = x360.translate(proto, story, self.audio_art())                # no file: no sound
        self.assertFalse([n for n in project.nodes if n.kind == 'sound'
                          and n.params['resource'] == x360.CLOSE_SOUND[1]])
        proto.files[x360.CLOSE_SOUND[0]] = b'zip'
        with patch.object(x360, 'pcm_wav', side_effect=lambda data: data):
            project = x360.translate(proto, story, self.audio_art())
        nodes = {n.id: n for n in project.nodes}
        zips = [n for n in project.nodes if n.kind == 'sound' and n.params['resource'] == x360.CLOSE_SOUND[1]]
        self.assertEqual(len(zips), 4)                  # hello, glad, sad and won; not the empty dialogue
        self.assertEqual({a.id: a.data for a in project.assets}[x360.CLOSE_SOUND[1]], b'zip')
        kinds, at = [], project.start
        while at in nodes and len(kinds) < 40 and nodes[at].kind != 'choice':
            kinds.append(nodes[at].kind)
            at = nodes[at].next
        self.assertLess(kinds.index('notice'), kinds.index('dialogue'))
        self.assertLess(kinds.index('dialogue'), max(i for i, k in enumerate(kinds) if k == 'sound'))

    def test_every_track_and_sound_is_one_the_addon_carries(self):
        import x360
        for resource, _ in x360.MIXES.values():
            self.assertTrue(x360.addon_holds(resource))
            self.assertLess(resource, x360.MUSIC_OTHER)
        for _, resource in x360.SCRIPT_SOUNDS.values():
            self.assertTrue(x360.addon_holds(resource))

    @unittest.skipUnless(__import__('shutil').which('ffmpeg'), 'ffmpeg is not installed')
    def test_a_track_sets_its_level_from_the_music_and_the_ambience_repeats_under_it(self):
        # Decoded real audio: the music alone comes up to MIX_RMS, and the same gain carries the ambience over it.
        import wave
        import numpy as np
        import x360

        def tone(seconds, level, hz):
            t = np.arange(int(seconds * 44100)) / 44100
            out = io.BytesIO()
            with wave.open(out, 'wb') as clip:
                clip.setnchannels(1); clip.setsampwidth(2); clip.setframerate(44100)
                clip.writeframes((np.sin(2 * np.pi * hz * t) * level * 32767).astype('<i2').tobytes())
            return out.getvalue()
        x360._mix_cache.clear()
        self.addCleanup(x360._mix_cache.clear)
        files = {'data/sound/music/freedom.ogg': tone(2, 0.5, 440), 'data/sound/ambient/suburban.ogg': tone(0.5, 0.5, 880),
                 'data/sound/ambient/dog_pound.ogg': tone(0.5, 0.25, 880)}
        alone = x360.decoded(x360.mix_track(files, 'freedom'), 44100, 2)
        mixed = x360.decoded(x360.mix_track(files, 'freedom_suburban'), 44100, 2)
        self.assertAlmostEqual(np.sqrt((alone ** 2).mean()), x360.MIX_RMS, delta=0.015)
        self.assertLess(np.abs(mixed).max(), x360.MIX_PEAK + 0.03)
        self.assertAlmostEqual(len(mixed) / 44100, 2.0, delta=0.1)               # the music's length
        tail = mixed[int(1.2 * 44100):int(1.8 * 44100)]
        self.assertGreater(np.abs(tail).max(), np.abs(alone).max() * 1.5)        # the ambience still there past its 0.5 s

    def test_the_limiter_leaves_the_music_and_rounds_off_only_the_peaks(self):
        import numpy as np
        import x360
        out = x360.limited(np.array([[0.5, -0.69], [1.5, -3.0]]))
        self.assertEqual(out[0].tolist(), [0.5, -0.69])
        self.assertTrue(x360.MIX_KNEE < out[1, 0] < x360.MIX_PEAK)
        self.assertTrue(-x360.MIX_PEAK <= out[1, 1] < -x360.MIX_KNEE)

    def test_the_pair_takes_its_ambience_running_on_from_the_intro_into_the_loop(self):
        import wave
        import numpy as np
        import x360
        from unittest.mock import patch

        def clip(samples):
            out = io.BytesIO()
            with wave.open(out, 'wb') as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(1000)
                w.writeframes((samples * 32767).astype('<i2').tobytes())
            return out.getvalue()

        def read(data):
            with wave.open(io.BytesIO(data)) as w:
                return np.frombuffer(w.readframes(w.getnframes()), '<i2') / 32768
        layer = np.linspace(0, 0.1, 150).reshape(-1, 1)
        with patch.object(x360, 'decoded', return_value=layer):
            a, b = x360.with_ambience(clip(np.zeros(100)), clip(np.zeros(100)), b'crowd', 0.5)
        self.assertEqual((read(a).max(), read(b).max()), (0.0, 0.0))              # relative to silence: no ambience
        with patch.object(x360, 'decoded', return_value=layer):
            a, b = x360.with_ambience(clip(np.zeros(100)), clip(np.full(100, 0.25)), b'crowd', 0.5)
        a, b = read(a), read(b)                                                   # half the loop's loudness
        scale = 0.5 * 0.25 / np.sqrt((layer ** 2).mean())
        self.assertAlmostEqual(a[99], layer[99, 0] * scale, delta=0.001)
        self.assertAlmostEqual(b[0], 0.25 + layer[100, 0] * scale, delta=0.001)   # on from where the intro left it
        self.assertAlmostEqual(b[60], 0.25 + layer[10, 0] * scale, delta=0.001)   # and round again past its end

    def test_an_objective_notice_and_its_sound_come_ahead_of_the_line_it_follows(self):
        # SHS shows a notice with the next line; the X360 checks an objective off after a talk's last line, and the
        # hub's choice comes next. The notice and the success sound go ahead of that last line instead.
        import x360
        from exp_runtime.creator import compile_project
        self.EVENTS = self.EVENTS.replace('DialogText("t/glad")\n    CloseDialog()',
                                          'DialogText("t/glad")\n    CloseDialog()\n    gameStats.check1 = true\n'
                                          '    camera.CreateFx("sound/success")', 1)
        proto = self.prototype()
        rate = 8000
        proto.files[x360.OBJECTIVE_SOUND[0]] = (b'RIFF' + struct.pack('<I', 36 + 2) + b'WAVEfmt ' + struct.pack(
            '<IHHIIHH', 16, 1, 1, rate, rate * 2, 2, 16) + b'data' + struct.pack('<I', 2) + b'\0\0')

        class Art:
            def background(self, location, mode):
                from PIL import Image
                return Image.new('RGB', (12, 4), (10, 20, 30))

            def backdrop(self):
                return None

        story = x360.Story('Test', 1, ['t/one'], [x360.Cast('a', 'Andy', 1, bank=2050)], {'lot': 23}, player='a')
        project = x360.translate(proto, story, Art())
        by_id = {n.id: n for n in project.nodes}
        notice = [n for n in project.nodes if n.kind == 'notice']
        self.assertEqual([n.text for n in notice], ['Objective Complete'])
        sound = by_id[notice[0].next]
        self.assertEqual((sound.kind, sound.params['resource']), ('sound', x360.OBJECTIVE_SOUND[1]))
        glad = by_id[sound.next]
        self.assertEqual((glad.kind, glad.text), ('dialogue', 'Glad you said yes.'))
        leads = [n.id for n in project.nodes if n.next == glad.id or n.otherwise == glad.id
                 or any(o.target == glad.id for o in n.options or ())]
        self.assertEqual(leads, [sound.id])                     # nothing skips past the notice to the line
        self.assertIn(x360.OBJECTIVE_SOUND[1], {a.id for a in project.assets})
        compile_project(project)

    def test_a_transition_into_an_event_is_queued_ahead_of_the_last_line_before_it(self):
        # SHS plays a queued transition as the next panel is dismissed: so it goes ahead of the last line before the
        # event, under the event's condition, and that line's other way on skips it.
        import x360
        from unittest import mock
        from exp_runtime.creator import compile_project
        from playthrough import play
        self.EVENTS = self.EVENTS.replace('game.RunEvent("t/two")', 'OpenDialog("a",0)\nDialogText("t/won")\n'
                                          'CloseDialog()\ngame.RunEvent("t/two")', 1)

        class Art:
            def background(self, location, mode):
                from PIL import Image
                return Image.new('RGB', (12, 4), (10, 20, 30))

            def backdrop(self):
                return None

        story = x360.Story('Test', 1, ['t/one'], [x360.Cast('a', 'Andy', 1, bank=2050)], {'lot': 23}, player='a')
        with mock.patch.dict(x360.TRANSITION_EVENTS, {'t/two': '(score >= 2)'}, clear=True):
            project = x360.translate(self.prototype(), story, Art())
        by_id = {n.id: n for n in project.nodes}
        fades = [n for n in project.nodes if n.kind == 'transition']
        self.assertEqual([n.params['selector'] for n in fades], [x360.SCENE_TRANSITION])
        line = by_id[fades[0].next]
        self.assertEqual((line.kind, line.character), ('dialogue', 'a'))       # Andy's "You scored." in t/one
        test = [n for n in project.nodes if n.next == fades[0].id]
        self.assertEqual([(n.kind, n.params['expression'], n.otherwise) for n in test],
                         [('branch', '(score >= 2)', line.id)])
        record = play(compile_project(project), [0])
        self.assertEqual(record[-1]['kind'], 'exit')

    def test_rendered_portraits_replace_a_cast_members_art_for_sd_and_hd(self):
        # x360_portrait.py's busts (HD-sized, <id>/<id>_<emotion>.png as the catalogue lays them out) take a cast
        # member's five slots, even one drawn from an SHS bank: as they are at the HD offset, halved for SD.
        import tempfile
        import x360
        from PIL import Image

        class Art:
            def background(self, location, mode):
                return Image.new('RGB', (12, 4), (10, 20, 30))

            def backdrop(self):
                return None

        # Andy wears Kim's render here (as Puzzle Test's "Josh" wears Josh's): its IDs are the render's own in every
        # story (RENDERS, so the X360 addon holds each once), whatever the cast's order.
        story = x360.Story('Test', 1, ['t/one'], [x360.Cast('a', 'Andy', 1, bank=2050)], {'lot': 23}, player='a',
                           renders={'a': 'kim'})
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'kim').mkdir()
            for i, emotion in enumerate(x360.RENDERED_EMOTIONS):
                Image.new('RGBA', (226, 256), (i * 40, 0, 0, 255)).save(Path(folder) / 'kim' / f'kim_{emotion}.png')
            rendered = x360.rendered_portraits(folder, story)
        self.assertEqual(list(rendered), ['a'])
        project = x360.translate(self.prototype(), story, Art(), rendered=rendered)
        andy = next(c for c in project.characters if c.id == 'a')
        base = x360.PORTRAIT_BASE + 5 * x360.RENDERS.index('kim')
        self.assertEqual(andy.expressions, [base + i for i in range(5)])                   # not the SHS bank
        assets = {a.id: a for a in project.assets}
        sd = Image.open(io.BytesIO(assets[base + 2].data))
        hd = Image.open(io.BytesIO(assets[base + x360.HIRES_PORTRAIT_OFFSET + 2].data))
        self.assertEqual((sd.size, hd.size), ((113, 128), (226, 256)))
        self.assertEqual(hd.getpixel((5, 5))[:3], (80, 0, 0))                              # happy, slot 2
        # A render with no ID is refused rather than given one that another story may use for someone else.
        story.renders = {'a': 'stranger'}
        with self.assertRaises(x360.TranslateError):
            x360.translate(self.prototype(), story, Art(), rendered=rendered)

    def test_the_prototypes_own_background_replaces_the_new_rules_one(self):
        # scene_backgrounds: <location>.jpg (and <location>_<who>.jpg for a talk); a covered location gets no New
        # Rules picture, and its event opens on the prototype's own.
        import tempfile
        import x360
        from PIL import Image

        class Art:
            def background(self, location, mode):
                raise AssertionError('no New Rules background wanted')

            def backdrop(self):
                return None

        story = x360.Story('Test', 1, ['t/one'], [x360.Cast('a', 'Andy', 1, bank=2050)], {'lot': 23}, player='a')
        with tempfile.TemporaryDirectory() as folder:
            Image.new('RGB', (960, 1440), (1, 2, 3)).save(Path(folder) / 'lot.jpg')
            Image.new('RGB', (960, 1440), (4, 5, 6)).save(Path(folder) / 'lot_a.jpg')
            Image.new('RGB', (960, 1440), (7, 8, 9)).save(Path(folder) / 'elsewhere.jpg')
            backgrounds = x360.scene_backgrounds(folder, story)
        self.assertEqual(sorted(backgrounds), ['lot', 'lot_a'])
        from unittest import mock
        with mock.patch.object(x360, 'SCENES', ('lot_a', 'lot')):                           # each its fixed ID
            project = x360.translate(self.prototype(), story, Art(), backgrounds=backgrounds)
        first = next(n for n in project.nodes if n.kind == 'background')
        self.assertEqual(first.asset, x360.SCENE_BACKGROUND_BASE + 1)                      # 'lot'
        with self.assertRaises(x360.TranslateError):                                        # 'lot' has no ID
            x360.translate(self.prototype(), story, Art(), backgrounds=backgrounds)
        sizes = {a.id: Image.open(io.BytesIO(a.data)).size for a in project.assets if a.id in (first.asset,)}
        self.assertEqual(sizes, {first.asset: (960, 1440)})
        self.assertFalse(any(x360.BACKGROUND_BASE <= a.id < x360.SCENE_BACKGROUND_BASE for a in project.assets))

    def test_dating_beths_older_scripts_choices_and_minigames(self):
        # MS3's calls (gameSHS.OpenDialog/SetDialogText/CloseDialog, three-argument AddChoices with "A. " labels and
        # -1), a think bubble in parentheses, an off-screen line given to the cast member whose colour it has, the
        # leash minigame as a word game deciding choice, and QuitGame.
        import x360
        from exp_runtime.creator import compile_project
        from playthrough import play
        self.EVENTS = '''<Tongas project="t">
    <object key="_a" type="EVENTCONFIGMASTER" name="t/one" version="1"><properties key="_a">
    <p k="_a" n="LocationName">lot</p><p k="_a" n="Script" l="lua"><![CDATA[
gameStats = {}
if gameStats ~= nil then
    gameStats.choice = 0
else
    gameStats = {}
    gameStats.choice = 0
end
gameSHS.OpenDialog("a","bubbles/think/left","bubbles/enter_from_left", false)
gameSHS.SetDialogText("t/glad",20)
gameSHS.CloseDialog("bubbles/exit_from_left")
gameSHS.OpenDialog("","bubbles/telephone/left","bubbles/enter_from_left")
gameSHS.SetDialogText("t/pink",20)
gameSHS.CloseDialog("bubbles/exit_fade")
gameSHS.ClearChoices()
gameSHS.AddChoices(ToUniString("[:t/yes]"),"GGRP:bubbles/choice/choice","me.RunCmd(0) gameStats.choice = -1")
gameSHS.AddChoices(ToUniString("[:t/no]"),"GGRP:bubbles/choice/choice","me.RunCmd(0) gameStats.choice = 1")
gameSHS.OpenChoice("bubbles/choice/main","choice/enter_from_bottom",0)
gameSHS.CloseChoice("choice/exit_fade")
gameSHS.ClearButtonSmashOptions()
gameSHS.AddButtonSmashOption("hud/x","LeftRight")
gameSHS.RunSmashButtonMinigame("hud/minigame/power_bar/main", 50, 7, 12, math.random(2,5), 13, "w", "l", "i", "d")
if gameStats.choice == 1 then
    gameSHS.OpenDialog("a","bubbles/talk/left","bubbles/enter_from_left")
    gameSHS.SetDialogText("t/won",20)
    gameSHS.CloseDialog("bubbles/exit_from_left")
end
QuitGame()
]]></p></properties></object></Tongas>'''
        self.STRINGS = dict(self.STRINGS, **{'t/yes': 'A. Say yes', 't/no': 'B. Say no',
                                             't/pink': '&:250 140 200;Hi from the phone'})

        class Art:
            def background(self, location, mode):
                from PIL import Image
                return Image.new('RGB', (12, 4), (10, 20, 30))

            def backdrop(self):
                return None

        story = x360.Story('Test', 1, ['t/one'], [x360.Cast('a', 'Andy', 1, bank=2050)], {'lot': 23}, player='a',
                           voices={'250 140 200': 'a'})
        project = x360.translate(self.prototype(), story, Art())
        choice = next(n for n in project.nodes if n.kind == 'choice')
        self.assertEqual([o.text for o in choice.options], ['Say yes', 'Say no'])
        games = [n for n in project.nodes if n.kind == 'word_game']
        self.assertEqual([g.params['result'] for g in games], ['leash'])
        lines = [(n.character, n.text) for n in project.nodes if n.kind == 'dialogue']
        self.assertEqual(lines[:2], [('a', '(Glad you said yes.)'), ('a', 'Hi from the phone')])
        # the slot machine's word game score maps onto the script's points: 5+ -> 3, 3-4 -> 2, less -> 0
        builder = x360.Builder(self.prototype(), story)
        builder.minigame('gameSHS.RunSlotMachineMinigame')
        self.assertEqual([n.params['expression'] for n in builder.nodes if n.kind == 'branch'],
                         ['(real_minigames == 1)', '(idea >= 5)', '(idea >= 3)'])
        self.assertEqual([n.params['expression'] for n in builder.nodes if n.kind == 'set'], ['3', '2', '0'])
        record = play(compile_project(project), [1], arena=False)  # the word game runs out at 0: the leash is lost
        self.assertEqual([e['text'] for e in record if e['kind'] == 'line'],
                         ['(Glad you said yes.)', 'Hi from the phone'])
        self.assertEqual(record[-1]['kind'], 'exit')

    def test_the_objective_tally_names_the_count_then_the_verdict(self):
        import x360
        builder = x360.Builder(self.prototype(), x360.Story('Test', 1, [], [], {}))
        builder.objective_tally()
        by_id = {n.id: n for n in builder.nodes}
        self.assertEqual(builder.nodes[0].params['expression'], '(check1 + check2 + check3)')

        def lines_for(n):
            node = builder.nodes[1]
            while node.kind == 'branch':
                node = by_id[node.next if node.params['expression'] == f'(objectives_done == {n})' else node.otherwise]
            return [node.text, by_id[node.next].text]
        self.assertEqual(lines_for(3), ['You completed 3 out of 3 objectives.', x360.TALLY_ALL])
        for n in (2, 1, 0):
            self.assertEqual(lines_for(n), [f'You completed {n} out of 3 objectives.', x360.TALLY_SOME])
        self.assertEqual(len(builder.pending), 4)                           # all four meet again at the end card


class MondayPlannerTests(unittest.TestCase):
    """What the Monday Planner adds to the translator, on authored scripts."""
    EVENTS = """<Tongas project="t">
    <object key="_a" type="EVENTCONFIGMASTER" name="t/start" version="1"><properties key="_a">
    <p k="_a" n="LocationName">lot</p><p k="_a" n="Script" l="lua"><![CDATA[
gameStats.tod = 0
gameStats.disslevel = 0
DissComment()
game.RunEvent("t/practice")
]]></p></properties></object>
    <object key="_b" type="EVENTCONFIGMASTER" name="t/practice" version="1"><properties key="_b">
    <p k="_b" n="LocationName">lot</p><p k="_b" n="Script" l="lua"><![CDATA[
gameStats.tod = gameStats.tod +1
if gameStats.tod > 2 then
    gameStats.tod = 0
end
dissTutorial(gameStats.dissPractice)
]]></p></properties></object>
    <object key="_c" type="EVENTCONFIGMASTER" name="episode3/monday_afternoon" version="1"><properties key="_c">
    <p k="_c" n="LocationName">room</p><p k="_c" n="Script" l="lua"><![CDATA[
OpenDialog("",8)
DialogText("t/afternoon")
CloseDialog()
game.RunEvent("t/practice")
]]></p></properties></object>
    <object key="_d" type="EVENTCONFIGMASTER" name="episode3/monday_evening" version="1"><properties key="_d">
    <p k="_d" n="LocationName">lot</p><p k="_d" n="Script" l="lua"><![CDATA[
OpenDialog("",8)
DialogText("t/evening")
CloseDialog()
game.RunEvent("t/practice")
]]></p></properties></object>
    <object key="_e" type="EVENTCONFIGMASTER" name="t/battle" version="1"><properties key="_e">
    <p k="_e" n="LocationName">lot</p><p k="_e" n="Script" l="lua"><![CDATA[
OpenDialog("",8)
DialogText("t/old")
CloseDialog()
--call the game here
OpenDialog("",8)
DialogText("t/won")
CloseDialog()
--next
QuitGame()
]]></p></properties></object></Tongas>"""
    STRINGS = {'t/afternoon': 'Afternoon', 't/evening': 'Evening', 't/old': 'Before', 't/won': 'Won', 't/lost': 'Lost',
               'episode3/end_demo/dialog_001': 'The end',
               **{f'episode3/comment/diss_00{n}': f'Comment {n}' for n in range(1, 6)},
               **{f'episode3/diss_battle_practice/dialog_000{c}': f'Level 2{c}' for c in ('', 'b', 'c', 'd')},
               'episode3/diss_battle_practice/dialog_001': 'Level 3',
               'episode3/diss_battle_practice/dialog_002': 'Level 4'}

    def prototype(self):
        import x360
        strings = ''.join(f'<object key="_s{i}" type="UNISTRINGSMASTER" name="{k}" version="1"><properties key="_s{i}">'
                          f'<p k="_s{i}" n="Text">{encode_wc(v)}</p></properties></object>'
                          for i, (k, v) in enumerate(self.STRINGS.items()))
        files = {'data/templates/unistrings.wxr': f'<Tongas project="t">{strings}</Tongas>'.encode(),
                 'data/templates/eventconfig.wxr': self.EVENTS.encode(),
                 'data/templates/guilabel.wxr': b'<Tongas project="t"></Tongas>'}
        return x360.Prototype(pak(files))

    def project(self, events, **story):
        import x360

        class Art:
            def background(self, location, mode):
                from PIL import Image
                return Image.new('RGB', (12, 4), (10, 20, 30))

            def backdrop(self):
                return None
        settings = dict(player='josh', diss_rounds=True, keep_state=frozenset({'tod'}),
                        extra_text=x360.MONDAY_PLANNER.extra_text)
        settings.update(story)
        backgrounds = settings.pop('backgrounds', None)
        return x360.translate(self.prototype(), x360.Story('Test', 1, events, [x360.Cast('josh', 'Josh', 1, bank=2050)],
                                                           {'lot': 23, 'room': 23}, **settings), Art(),
                              backgrounds=backgrounds)

    @staticmethod
    def drive(data, answers=(), scores=()):
        """(lines, choices' prompts, word games played): answering in order, each word game ending at its score."""
        from playthrough import session
        s = session(data, arena=False)
        s.engine.random.state = 1
        answers, scores = list(answers), list(scores)
        lines, prompts, games = [], [], 0
        action = s.advance()
        for _ in range(2000):
            while s.transitioning:
                action = s.tick(s.engine.scene_transition.duration_ms)
            kind, details = action.name, action.details
            if kind == 'episode_exit':
                break
            if kind == 'dialogue':
                lines.append(details['text'])
                if not s.engine.dialogue_animation.complete:
                    s.answer(); s.tick(2000)
                action = s.answer()
            elif kind == 'choice':
                prompts.append(details['text'])
                if not s.choice_ready:
                    s.tick(250)
                action = s.answer(answers.pop(0))
            elif kind == 'word_game':
                games += 1
                action = s.skip_word_game(scores.pop(0))
            elif kind == 'message_panel':
                lines.append(s.engine.message_panel.text)
                action = s.tick(4000)
                if s.pending is not None and s.pending.name == kind:
                    action = s.answer()
            else:
                raise AssertionError(kind)
            if action is None:
                action = s.pending
        return lines, prompts, games

    def test_a_round_passes_at_its_levels_goal_says_so_and_goes_on_by_the_time_of_day(self):
        from exp_runtime.creator import compile_project
        data = compile_project(self.project(['t/start']))
        comments = [f'Comment {n}' for n in range(1, 6)]
        lines, _, games = self.drive(data, scores=(8, 10, 13))
        self.assertEqual(games, 3)
        self.assertIn(lines[0], comments)
        self.assertEqual(lines[1:], ['Level 2', 'Level 2b', 'Level 2c', 'Level 2d', 'Afternoon', 'Level 3', 'Evening',
                                     'Level 4', 'The end'])

    def test_a_failed_round_says_ouch_and_doesnt_repeat_the_level(self):
        from exp_runtime.creator import compile_project
        data = compile_project(self.project(['t/start']))
        ouch = "Ouch. You couldn't quite move up to the next level of diss battling..."
        lines, _, _ = self.drive(data, scores=(7, 8, 9))
        # The first fails (7 < 8), the second passes (8), the third fails: the goal is now 10.
        self.assertEqual(lines[1:], [ouch, 'Afternoon', 'Level 2', 'Level 2b', 'Level 2c', 'Level 2d', 'Evening', ouch,
                                     'The end'])

    def test_the_real_game_plays_where_the_switch_is_on_with_its_tutorial_the_first_time(self):
        from exp_runtime.creator import compile_project
        from playthrough import play
        project = self.project(['t/start'])
        games = [n.params['tutorial'] for n in project.nodes if n.kind == 'x360_diss']
        self.assertEqual(games, [1, 0])
        record = play(compile_project(project))
        self.assertEqual([e['kind'] for e in record].count('x360_diss'), 3)
        self.assertNotIn('word_game', [e['kind'] for e in record])
        self.assertEqual(record[-1]['kind'], 'exit')

    def test_a_sound_can_play_at_its_volume(self):
        import io
        import struct
        import wave
        import x360
        out = io.BytesIO()
        with wave.open(out, 'wb') as writer:
            writer.setnchannels(1); writer.setsampwidth(2); writer.setframerate(22050)
            writer.writeframes(struct.pack('<2h', 12700, -12700))
        with wave.open(io.BytesIO(x360.at_volume(out.getvalue(), 64))) as reader:
            self.assertEqual(struct.unpack('<2h', reader.readframes(2)), (6400, -6400))
            self.assertEqual((reader.getframerate(), reader.getnchannels()), (22050, 1))

    def test_every_comment_can_be_said(self):
        project = self.project(['t/start'])
        said = [n.text for n in project.nodes if n.kind == 'dialogue' and n.text.startswith('Comment')]
        self.assertEqual(said, [f'Comment {n}' for n in range(1, 6)])
        self.assertEqual([n.params['bound'] for n in project.nodes if n.kind == 'random'], [5])

    def battle(self):
        import x360
        from exp_runtime.creator import compile_project
        loss = 'else\nOpenDialog("",8)\nDialogText("t/lost")\nCloseDialog()\nend\n--next'
        project = self.project(['t/battle'], script_edits={'t/battle': (
            ('--call the game here', 'SpeedDiss()\nif gameStats.flow >= 7 then'), ('--next', loss))})
        return compile_project(project), x360.SPIKE_ROUNDS

    def test_the_speed_diss_wins_at_seven_and_ends_at_ten_hits_or_three_misses(self):
        data, rounds = self.battle()
        right = [answer for _, _, answer in rounds]
        wrong = [(answer + 1) % len(options) for _, options, answer in rounds]
        lines, prompts, _ = self.drive(data, right[:12])
        self.assertEqual(lines, ['Before', 'Won'])
        self.assertEqual(len(prompts), 10)                      # ten hits finish it
        self.assertEqual(prompts[0], 'Flow: 0/10\nMiss: 0/3\nRhymes with { Rude {')
        self.assertEqual(prompts[9], 'Flow: 9/10\nMiss: 0/3\nRhymes with { Spend {')
        lines, prompts, _ = self.drive(data, wrong[:3])
        self.assertEqual((lines, len(prompts)), (['Before', 'Lost'], 3))
        lines, prompts, _ = self.drive(data, right[:7] + wrong[7:10])
        self.assertEqual((lines, len(prompts)), (['Before', 'Won'], 10))
        lines, prompts, _ = self.drive(data, right[:6] + wrong[6:9])
        self.assertEqual((lines, len(prompts)), (['Before', 'Lost'], 9))

    def test_every_speed_diss_round_has_a_rhyme_and_times_out_as_a_miss(self):
        import x360
        project = self.project(['t/battle'], script_edits={'t/battle': (('--call the game here', 'SpeedDiss()'),)})
        by_id = {n.id: n for n in project.nodes}
        rounds = [n for n in project.nodes if n.kind == 'choice']
        self.assertEqual(len(rounds), len(x360.SPIKE_ROUNDS))
        for node, (_, options, answer) in zip(rounds, x360.SPIKE_ROUNDS):
            self.assertEqual([o.text for o in node.options], [o.capitalize() for o in options])
            self.assertEqual(node.timeout_ms, x360.SPEED_DISS_MS)
            self.assertEqual(by_id[node.options[answer].target].variable, 'flow')
            self.assertEqual(by_id[node.options[node.timeout_option].target].variable, 'miss')

    def test_an_edit_that_doesnt_fit_its_script_stops_the_build(self):
        import x360
        with self.assertRaises(x360.TranslateError):
            self.project(['t/battle'], script_edits={'t/battle': (('--no such line', 'x'),)})

    def test_a_scene_has_its_own_background_and_music_or_silence(self):
        import x360
        from unittest import mock
        from PIL import Image
        picture = Image.new('RGB', (12, 4), (1, 2, 3))
        with mock.patch.object(x360, 'SCENES', ('a', 'b')), mock.patch.dict(x360.MIXES, {}, clear=False):
            project = self.project(['t/start'], event_scenes={'t/start': 'a', 't/practice': 'b',
                                                              'episode3/monday_afternoon': 'a',
                                                              'episode3/monday_evening': 'b'},
                                   event_music={'episode3/monday_afternoon': ''},
                                   backgrounds={'a': picture, 'b': picture})
        assets = [n.asset for n in project.nodes if n.kind == 'background']
        self.assertEqual(assets, [x360.SCENE_BACKGROUND_BASE, x360.SCENE_BACKGROUND_BASE + 1, x360.SCENE_BACKGROUND_BASE,
                                  x360.SCENE_BACKGROUND_BASE + 1])
        kinds = [n.kind for n in project.nodes]
        self.assertEqual(kinds[kinds.index('stop_audio') - 1], 'background')    # silent as the scene arrives
        self.assertEqual(kinds.count('stop_audio'), 1)

    def test_time_of_day_is_only_kept_by_the_story_that_decides_by_it(self):
        kept = [n.variable for n in self.project(['t/start']).nodes if n.kind == 'set']
        self.assertIn('tod', kept)
        # (Without it the practice's own routing can't be built, so a story without tod is one with no rounds.)
        self.assertNotIn('tod', [n.variable for n in self.project(['t/battle'], keep_state=frozenset()).nodes
                                 if n.kind == 'set'])

    def test_a_placeholder_takes_its_one_portrait_in_all_five_slots(self):
        import tempfile
        import x360
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'spike').mkdir()
            Image.new('RGBA', (4, 4)).save(Path(folder) / 'spike' / 'spike_neutral.png')
            planner = x360.Story('T', 1, [], [x360.Cast('spike', 'Spike', 1)], {}, event_scenes={'t': 'a'})
            self.assertEqual(len(x360.rendered_portraits(folder, planner)['spike']), 5)
            other = x360.Story('T', 1, [], [x360.Cast('spike', 'Spike', 1)], {})
            self.assertEqual(x360.rendered_portraits(folder, other), {})

    def test_andy_is_spike_at_an_id_of_his_own(self):
        import x360
        self.assertEqual(x360.MONDAY_PLANNER.renders, {'spike': 'andy'})
        self.assertEqual(x360.RENDERS[-1], 'andy')          # new ones at the end: the others' IDs are kept
        taken = {x360.render_base(render) for render in x360.RENDERS}
        self.assertEqual(len(taken), len(x360.RENDERS))
        self.assertTrue(x360.addon_holds(x360.render_base('andy')))
        self.assertTrue(x360.addon_holds(x360.render_base('andy') + x360.HIRES_PORTRAIT_OFFSET))

    def test_the_ms3_set_is_the_looks_the_switch_changes_at_the_offset_the_profile_names(self):
        import tempfile
        import x360
        from exp_runtime.shs.profile import MS3_CHARACTER_ART
        from PIL import Image
        self.assertEqual(MS3_CHARACTER_ART[x360.PACK_ID], x360.MS3_PORTRAIT_OFFSET)
        self.assertEqual(set(x360.MS3_LOOKS), {'josh', 'zack', 'kim', 'ryan', 'hector'})
        self.assertEqual(x360.MS3_LOOKS['josh'], x360.MS3_LOOKS['zack'])    # MS3's Josh wears Zack's model
        with tempfile.TemporaryDirectory() as folder:
            for look in set(x360.MS3_LOOKS.values()):
                (Path(folder) / look).mkdir()
                for emotion in x360.RENDERED_EMOTIONS:
                    Image.new('RGBA', (4, 4)).save(Path(folder) / look / f'{look}_{emotion}.png')
            portraits = x360.ms3_portraits(folder)
        self.assertEqual(len(portraits), 5 * len(x360.MS3_LOOKS))
        for render in x360.MS3_LOOKS:
            for i in range(5):
                self.assertIn(x360.render_base(render) + x360.MS3_PORTRAIT_OFFSET + i, portraits)
        self.assertFalse(set(portraits) & {x360.render_base(render) + x360.HIRES_PORTRAIT_OFFSET + i
                                           for render in x360.RENDERS for i in range(5)})

    def test_the_planners_edits_fit_nothing_the_other_stories_use(self):
        import x360
        for story in (x360.DAY_OF_DISS, x360.PUZZLE_TEST, x360.DATING_BETH):
            self.assertFalse(story.diss_rounds or story.script_edits or story.event_scenes)
        self.assertEqual(max(story.addon_revision for story in x360.STORIES.values()), x360.ADDON_REVISION)
        self.assertEqual(set(x360.MONDAY_PLANNER.event_scenes.values()) - set(x360.SCENES), set())


class EmoticonEffectTests(unittest.TestCase):
    def test_each_effect_enters_then_keeps_a_quiet_loop(self):
        from exp_runtime import emoticon_effects as fx
        for effect in fx.EFFECTS:
            self.assertEqual(fx.sprites(effect, 0), [], effect)                 # nothing before it starts
            late = [fx.sprites(effect, t) for t in (5000, 9000, 20000)]
            self.assertTrue(all(late), effect)                                  # still up while the line is
            for frame in late:
                for sprite in frame:
                    self.assertEqual(sprite.effect, effect)
                    self.assertTrue(0 < sprite.scale < 2 and 0 <= sprite.alpha <= 1)
                    self.assertLess(abs(sprite.x) + abs(sprite.y), 60)         # near the anchor
        self.assertEqual(fx.sprites(99, 500), [])
        self.assertEqual(fx.sprites(fx.HEART, 1000), fx.sprites(fx.HEART, 1000))   # pure: the same time, the same frame

    def test_entrances_overshoot_and_settle(self):
        from exp_runtime import emoticon_effects as fx
        peak = max(fx.sprites(fx.ANGER, t)[0].scale for t in range(10, 240, 10))
        self.assertGreater(peak, 1.1)
        rise = [fx.sprites(fx.EXCLAMATION, t)[0].y for t in (40, 200, 520)]
        self.assertGreater(rise[0], rise[2])                                    # springs up into place
        self.assertLessEqual(len(fx.sprites(fx.HEART, 1000)), 4)                 # the burst, then one at a time

    def test_the_x360_names_map_onto_the_six_cells(self):
        from exp_runtime import emoticon_effects as fx
        self.assertEqual(fx.X360_EFFECTS['love'], fx.HEART)
        self.assertEqual(fx.X360_EFFECTS['angry_female'], fx.LIGHTNING)
        self.assertEqual(fx.X360_EFFECTS['stress'], fx.ANGER)
        self.assertNotIn('dust', fx.X360_EFFECTS)

    def test_the_runtime_reads_the_effect_key_the_translator_sets(self):
        from types import SimpleNamespace
        from exp_runtime.engine import EngineState
        from exp_runtime.runtime import Session
        from exp_runtime.shs import profile
        key, first = profile.TRANSLATED_PORTRAIT_EFFECTS[31400]
        engine = SimpleNamespace(numbers={}, number_key=EngineState.number_key)
        line = SimpleNamespace(name='dialogue', details=dict(presentation_mode=2))
        session = SimpleNamespace(pending=line, engine=engine, resources=SimpleNamespace(
            record=dict(pack_id=31400), library=SimpleNamespace(game_id='shs')))
        self.assertIsNone(Session.portrait_effect(session))
        engine.numbers[EngineState.number_key(0, key)] = 4
        self.assertEqual(Session.portrait_effect(session), (4, first + 3))
        line.details['presentation_mode'] = 3                                   # no portrait: none
        self.assertIsNone(Session.portrait_effect(session))
        line.details['presentation_mode'] = 1
        session.resources.record = dict(pack_id=5)                              # another pack: never
        self.assertIsNone(Session.portrait_effect(session))


class X360AddonTests(unittest.TestCase):
    """The X360 addon (shsx360): what the three stories share, held once, and the stories built without it."""

    @staticmethod
    def story(extra=None):
        from exp_runtime.exp import Metadata, encode_exp
        resources = {1: Metadata(31400, 1, ('A story (SHSX360)',) * 5).to_bytes(), 25001: b'script',
                     26000: b'a New Rules strip', 26100: b'diss battle', 26200: b'josh'}
        resources.update(extra or {})
        return encode_exp(resources)

    def test_renders_and_backgrounds_have_one_id_in_every_story(self):
        import x360
        # Day of Diss keeps the IDs it was first imported with; Puzzle Test's and Dating Beth's moved to these.
        self.assertEqual(x360.RENDERS[:5], ('josh', 'kim', 'ryan', 'nicole', 'hector'))
        self.assertEqual(x360.SCENES[:6], ('diss_battle', 'parking_lot', 'parking_lot_hector', 'parking_lot_kim',
                                           'parking_lot_nicole', 'parking_lot_ryan'))
        held = (26100, 26109, 26200, 26239, 27200, 27239, 26900, 26901, 26985, 26990, 26999, 26300, 26390)
        self.assertTrue(all(x360.addon_holds(i) for i in held))
        # New Rules' location strips and looks stay in the story that uses them.
        self.assertFalse(any(x360.addon_holds(i) for i in (1, 25001, 26000, 26121, 26250, 27250)))
        # The later renders stay out of the New Rules looks' way, and within what the larger set moves.
        self.assertEqual(x360.render_base('moondog'), 26235)
        self.assertEqual(x360.render_base('mrpibb'), 26750)
        self.assertTrue(all(x360.addon_holds(x360.render_base('dexter') + i) for i in (4, 1004)))

    def test_the_addon_holds_the_shared_resources_and_a_story_declares_it(self):
        import x360
        from exp_runtime.addons import addon_record
        from exp_runtime.exp import ExpArchive
        first = self.story({26990: b'emoticon'})
        second = self.story()
        addon = ExpArchive(x360.build_addon([first, second], {26300: b'{}'}))
        self.assertEqual(addon_record(addon)[0], 'provides')
        self.assertEqual(sorted(i for i in addon.entries if i >= 26000), [26100, 26200, 26300, 26990])
        stripped, left_out = x360.strip_addon(first, addon)
        self.assertEqual(left_out, [26100, 26200, 26990])
        archive = ExpArchive(stripped)
        self.assertEqual(sorted(archive.entries), [1, 4, 25001, 26000])
        self.assertEqual(addon_record(archive), ('requires', ((x360.ADDON_ID, x360.STORY_ADDON_REVISION),)))
        # Stories built from other art can't share the addon.
        with self.assertRaises(x360.TranslateError):
            x360.build_addon([first, self.story({26100: b'another battle'})])
        with self.assertRaises(x360.TranslateError):
            x360.strip_addon(self.story({26200: b'another josh'}), addon)

    def test_the_stories_are_tagged_for_the_pickers_x360_badge(self):
        import x360
        from exp_runtime.content import legacy_fields
        from exp_runtime.shs.profile import LEGACY_GAMES
        fields = legacy_fields(['Day of Diss' + x360.TITLE_SUFFIX], 'shs', 1)
        self.assertEqual(fields, dict(titles=['Day of Diss'], legacy='SHSX360', category='Xbox 360'))
        self.assertEqual(LEGACY_GAMES['SHSX360']['badge'], 'X360')
        # Listed Day of Diss, Monday Planner, Dating Beth, Puzzle Test (their ids are 1, 4, 3, 2).
        order = LEGACY_GAMES['SHSX360']['order']
        self.assertEqual(sorted((1, 4, 3, 2), key=lambda episode: order.get(episode, episode)), [1, 4, 3, 2])


@unittest.skipUnless(HAS_PIL, 'x360_arena_art.py draws with Pillow')
class DanceAtlasTests(unittest.TestCase):
    def test_ms3s_dance_is_the_next_atlas_in_its_own_folder(self):
        import tempfile
        from PIL import Image
        import x360_arena_art
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            (folder / 'dance_ms3').mkdir()
            for name in ('stand', '0'):
                Image.new('RGBA', (4, 4), (1, 2, 3, 255)).save(folder / 'dance_ms3' / f'{name}.png')
            _, entry = x360_arena_art.dance_atlas(folder, dict(period_ms=70, stand=[0, 0, 1, 1], frames=[[0, 0, 1, 1]], places={'7': {'scale': 2}}),
                                                  'dance_ms3', x360_arena_art.DANCE_BASE + 1)
        self.assertEqual(entry['atlas'], x360_arena_art.DANCE_BASE + 1)
        self.assertEqual((entry['period_ms'], entry['places']), (70, {'7': {'scale': 2}}))
        self.assertIn(entry['atlas'], x360_arena_art.SKIN_IDS)

    def test_every_frame_lands_in_the_atlas_with_its_box(self):
        import tempfile
        from PIL import Image
        import x360_arena_art
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            (folder / 'dance').mkdir()
            colours = {'stand': (9, 9, 9, 255), **{str(i): (i * 10 + 20, 0, 0, 255) for i in range(12)}}
            for name, colour in colours.items():
                Image.new('RGBA', (300, 40), colour).save(folder / 'dance' / f'{name}.png')
            data, entry = x360_arena_art.dance_atlas(folder, dict(period_ms=800, stand=[1, 2, 3, 4], frames=[[i, 0, 1, 1] for i in range(12)]))
        atlas = Image.open(io.BytesIO(data)).convert('RGBA')
        self.assertEqual(entry['atlas'], x360_arena_art.DANCE_BASE)
        self.assertIn(x360_arena_art.DANCE_BASE, x360_arena_art.SKIN_IDS)
        self.assertEqual(atlas.width, x360_arena_art.DANCE_ATLAS_WIDTH)
        self.assertEqual(entry['stand']['box'], [1, 2, 3, 4])
        self.assertEqual(entry['period_ms'], 800)
        self.assertEqual(len(entry['frames']), 12)
        self.assertEqual(atlas.getpixel(tuple(entry['stand']['rect'][:2])), colours['stand'])
        for i, cell in enumerate(entry['frames']):
            self.assertEqual(cell['box'][0], i)
            x, y, w, h = cell['rect']
            self.assertLessEqual(x + w, atlas.width)
            self.assertLessEqual(y + h, atlas.height)
            self.assertEqual(atlas.getpixel((x + w - 1, y + h - 1)), colours[str(i)])


@unittest.skipUnless(HAS_PIL, 'x360_arena_art.py draws with Pillow')
class OpeningTests(unittest.TestCase):
    def art(self, folder):
        from PIL import Image
        import io

        def bytes_of(image, kind):
            buffer = io.BytesIO()
            image.save(buffer, kind)
            return buffer.getvalue()
        for name in ('sweep_first', 'sweep_lot', 'sweep_low'):
            Image.new('RGB', (2560, 1440), (10, 20, 30)).save(Path(folder) / f'{name}.jpg')
        Image.new('RGB', (1440, 2560), (40, 50, 60)).save(Path(folder) / 'josh_tall.jpg')
        base = 'data/art/hud/characters_presentation/josh/'
        files = {base + 'background.jpg': bytes_of(Image.new('RGB', (1024, 1024)), 'JPEG')}
        for name in ('yellow_stains', 'name'):
            files[base + name + '.jpg'] = bytes_of(Image.new('RGB', (512, 256)), 'JPEG')
            files[base + name + '_a.jpg'] = bytes_of(Image.new('L', (512, 256)), 'JPEG')
        chars = ''.join(f'char id={ord(c)} x=0 y=0 width=8 height=8 xoffset=0 yoffset=0 xadvance=8 page=0 chnl=15\n'
                        for c in set("King of Diss '08"))
        files['data/art/fonts/blambot_badaboom_white.fnt'] = f'common lineHeight=12 base=8\npage id=0 file="a.png"\n{chars}'.encode()
        files['data/art/fonts/blambot_badaboom_white_00.png'] = bytes_of(Image.new('RGBA', (16, 16), (255, 255, 255, 255)), 'PNG')
        files['data/sound/fx/whip.wav'] = b'whip'
        return files

    def test_the_opening_is_a_valid_cutscene_stored_at_the_frames_scale(self):
        import io
        import tempfile
        import x360
        import x360_arena_art as art
        from PIL import Image
        from exp_runtime.cutscene import read_spec
        with tempfile.TemporaryDirectory() as folder:
            out = art.opening(self.art(folder), lambda data: data, folder)
        spec = read_spec(out[art.OPENING_BASE])
        self.assertEqual(x360.DAY_OF_DISS.opening, art.OPENING_BASE)
        self.assertEqual(sorted(out), list(range(art.OPENING_BASE, art.OPENING_BASE + 10)))
        self.assertTrue(all(resource in art.SKIN_IDS and x360.addon_holds(resource) for resource in out))
        self.assertTrue(set(range(art.NOTES_BASE, art.NOTES_BASE + 6)).isdisjoint(out))
        # The whip and the card land together, where the prototype's whip falls in the music, and it holds there.
        self.assertEqual(spec['sounds'], [dict(at=14510, sound=art.OPENING_BASE + 9)])
        self.assertEqual(spec['skip'], 14510)
        self.assertEqual(spec['hold'], 14810)
        self.assertEqual(spec['music'], x360.MUSIC_INTRO)
        self.assertEqual(spec['shots'][-1]['start'], 14510)
        self.assertEqual(spec['shots'][-2]['end'], 14510)
        for shot in spec['shots']:
            size = Image.open(io.BytesIO(out[shot['image']])).size
            for box in (shot['from'], shot['to']):
                self.assertEqual(box[2:], [768, 1024])              # a blit
                self.assertTrue(0 <= box[0] <= size[0] - 768 and 0 <= box[1] <= size[1] - 1024, (shot, size))

    def test_day_of_diss_needs_the_addon_that_holds_its_opening(self):
        import x360
        self.assertEqual(x360.DAY_OF_DISS.addon_revision, 14)
        self.assertLessEqual(x360.MONDAY_PLANNER.addon_revision, x360.ADDON_REVISION)


class X360SkinTests(unittest.TestCase):
    def test_a_bmfont_descriptor_is_read(self):
        import x360_arena_art
        spec, pages = x360_arena_art.read_font(
            'info face="Blambot Casual" size=50 bold=1\ncommon lineHeight=50 base=41 scaleW=512 scaleH=512 pages=2\n'
            'page id=0 file="casual_00.png"\npage id=1 file="casual_01.png"\nchars count=2\n'
            'char id=65   x=1     y=2     width=30    height=40    xoffset=-6    yoffset=3     xadvance=24   page=1  chnl=15\n'
            'char id=32   x=495   y=162   width=13    height=12    xoffset=-6    yoffset=44    xadvance=12   page=0  chnl=15\n'
            'kerning first=65 second=86 amount=-2\n')
        self.assertEqual(pages, ['casual_00.png', 'casual_01.png'])
        self.assertEqual((spec['line_height'], spec['base']), (50, 41))
        self.assertEqual(spec['chars']['65'], [1, 2, 30, 40, -6, 3, 24, 1])
        self.assertEqual(spec['kerning'], {'65,86': -2})
        with self.assertRaises(x360_arena_art.SkinError):
            x360_arena_art.read_font('info face="x"\n')

    def test_a_new_rules_item_is_enlarged_and_outlined(self):
        import x360_arena_art
        from PIL import Image
        item = Image.new('RGBA', (10, 6), (0, 0, 0, 0))
        item.paste((200, 40, 40, 255), (2, 1, 8, 5))
        out = x360_arena_art.outlined(item)
        # twice the size, with a solid ink line OUTLINE pixels wide just outside it, and a shadow beyond
        self.assertGreater(out.width, 12 + 2 * x360_arena_art.OUTLINE)
        row = [out.getpixel((x, out.height // 2 - 2)) for x in range(out.width)]
        first_red = next(x for x, p in enumerate(row) if p[0] > 150)        # the smooth enlargement blends its edge
        self.assertEqual(row[first_red - 2], x360_arena_art.INK + (255,))
        last_red = max(x for x, p in enumerate(row) if p[0] > 150)
        self.assertEqual(row[last_red + 2], x360_arena_art.INK + (255,))
        self.assertTrue(0 < row[last_red + 2 + x360_arena_art.OUTLINE][3] < 255)    # then the soft shadow

    def test_an_effect_sprite_is_white_with_its_brightness_as_alpha(self):
        import x360_arena_art
        from PIL import Image
        cell = Image.new('RGB', (4, 4), (0, 0, 0))
        cell.putpixel((1, 1), (200, 200, 200))
        out = x360_arena_art.sprite(cell)
        self.assertEqual(out.getpixel((1, 1)), (255, 255, 255, 200))
        self.assertEqual(out.getpixel((0, 0))[3], 0)

    def test_the_skin_stays_in_its_ids_and_replaces_new_rules_sounds_and_music(self):
        import x360_arena_art as art
        self.assertTrue(all(i in art.SKIN_IDS for i in (art.SPEC, art.PICTURE_BASE, art.FONT_PAGE_BASE,
                                                        art.SOUND_BASE + len(art.SOUNDS) - 1, art.MUSIC)))
        self.assertLessEqual(art.PICTURE_BASE + len(art.PICTURES) + len(art.DERIVED) + art.NR_ITEMS, art.FONT_PAGE_BASE)
        self.assertEqual(set(art.SOUND_TRACKS), {13, 1, 11})        # right, wrong, Fever's bonus noise (the swaps)
        self.assertEqual(art.MUSIC_TRACK, 14)                       # the games' music
        self.assertIn(art.BOOTH_BASE + len(art.BOOTH_PIECES) + len(art.PLACES), art.SKIN_IDS)

    def test_the_booths_shots_keep_their_place_in_the_camera_frame(self):
        import io
        import json
        import tempfile
        import x360_arena_art as art
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            (folder / 'digits').mkdir()
            (folder / 'places').mkdir()
            boxes = {}
            for k, name in enumerate(art.BOOTH_PIECES):
                Image.new('RGBA', (30, 10), (k, 0, 0, 255)).save(folder / f'{name}.png')
                boxes[name] = [100, 200, 130, 210]
            for i in range(art.DIGIT_SLOTS):
                for n in range(art.DIGITS):
                    Image.new('RGBA', (4 + n, 6 + i), (200, n, i, 255)).save(folder / 'digits' / f'slot_{i}_{n}.png')
                    boxes[f'slot_{i}_{n}'] = [10 * i, 5 * n, 10 * i + 4 + n, 5 * n + 6 + i]
            for name in art.PLACES:
                Image.new('RGB', (16, 9), (1, 2, 3)).save(folder / 'places' / f'{name}.png')
            (folder / 'booth.json').write_text(json.dumps(dict(frame=[1848, 1040], camera='cameras/diss_002',
                                                               boxes=boxes)), encoding='utf-8')
            resources, entry = art.booth(folder)
        self.assertEqual(sorted(resources), list(range(art.BOOTH_BASE, art.BOOTH_BASE + 4 + len(art.PLACES))))
        self.assertEqual(entry['pieces']['record'], dict(id=art.BOOTH_BASE + 2, box=[100, 200, 130, 210]))
        cell = entry['digits']['slots'][2][3]                         # slot 2 showing 3
        self.assertEqual(cell['box'], [20, 15, 27, 23])
        atlas = Image.open(io.BytesIO(resources[entry['digits']['atlas']]))
        x, y, w, h = cell['rect']
        self.assertEqual((w, h), (7, 8))
        self.assertEqual(atlas.getpixel((x, y)), (200, 3, 2, 255))
        self.assertEqual(entry['places']['school_front_diss_002'], art.BOOTH_BASE + 4)   # the practice's own view first

    def test_the_skins_music_is_an_mp3_with_nothing_counted_as_playing_time_but_its_frames(self):
        from unittest.mock import Mock, patch
        import x360_arena_art as art
        with patch.object(art.shutil, 'which', return_value='ffmpeg'), \
                patch.object(art.subprocess, 'run', return_value=Mock(stdout=b'mp3')) as run:
            self.assertEqual(art.ogg_mp3(b'ogg'), b'mp3')
        command = run.call_args.args[0]
        self.assertEqual(run.call_args.kwargs['input'], b'ogg')
        for option, value in (('-f', 'mp3'), ('-acodec', 'libmp3lame'), ('-b:a', art.MUSIC_BITRATE), ('-write_xing', '0'),
                              ('-id3v2_version', '0')):
            self.assertEqual(command[command.index(option) + 1], value)
        with patch.object(art.shutil, 'which', return_value=None), self.assertRaises(art.SkinError):
            art.ogg_mp3(b'ogg')

    def test_the_split_decks_arm_frames_go_in_one_atlas_with_their_places(self):
        import io
        import tempfile
        import x360_arena_art as art
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            (folder / 'arm').mkdir()
            for name in ('body', 'record_base', 'record_seams', 'spindle'):
                Image.new('RGBA', (8, 8), (1, 2, 3, 255)).save(folder / f'{name}.png')
            Image.new('RGBA', (5, 4), (10, 0, 0, 255)).save(folder / 'arm' / '0.png')
            Image.new('RGBA', (7, 3), (20, 0, 0, 255)).save(folder / 'arm' / '1.png')
            parts = dict(body=[1, 2, 3, 4], record_base=[5, 6, 7, 8], spindle=[9, 9, 9, 9],
                         seams=dict(centre=[50, 60], radius=30, squash=2.5),
                         arm=dict(push=[[0, 0], [100, 20]], frames=[dict(angle=0, box=[0, 0, 5, 4], tip=[1, 1]),
                                                                    dict(angle=20, box=[2, 2, 9, 5], tip=[3, 3])]))
            resources, entry = art.deck_parts(folder, parts)
        self.assertEqual(sorted(resources), list(range(art.PARTS_BASE, art.PARTS_BASE + 5)))
        self.assertTrue(all(i in art.SKIN_IDS for i in resources))
        self.assertEqual(entry['record'], dict(id=art.PARTS_BASE + 1, box=[5, 6, 7, 8]))
        self.assertEqual(entry['seams'], dict(id=art.PARTS_BASE + 2, centre=[50, 60], radius=30, squash=2.5))
        self.assertEqual(entry['arm']['push'], [[0, 0], [100, 20]])
        frame = entry['arm']['frames'][1]
        self.assertEqual((frame['angle'], frame['box'], frame['tip'], frame['rect']), (20, [2, 2, 9, 5], [3, 3], [0, 4, 7, 3]))
        atlas = Image.open(io.BytesIO(resources[entry['arm']['atlas']]))
        self.assertEqual(atlas.size, (7, 7))
        self.assertEqual(atlas.getpixel((0, 4)), (20, 0, 0, 255))

    def test_the_tutorials_music_is_brought_down_to_the_practice_musics_level(self):
        import x360_arena_art as art
        self.assertEqual(art.TUTORIAL_MUSIC_FILE, 'data/sound/music/diss_001.ogg')
        self.assertIn(art.TUTORIAL_MUSIC, art.SKIN_IDS)
        self.assertNotEqual(art.TUTORIAL_MUSIC, art.MUSIC)
        from unittest.mock import patch
        with patch.object(art.subprocess, 'run') as run, patch.object(art.shutil, 'which', return_value='ffmpeg'):
            art.ogg_mp3(b'ogg', art.TUTORIAL_MUSIC_GAIN_DB)
            self.assertIn('volume=-5dB', run.call_args.args[0])
            art.ogg_mp3(b'ogg')
            self.assertFalse([a for a in run.call_args.args[0] if str(a).startswith('volume')])

    def test_the_puzzles_art_and_sounds_keep_to_their_ids(self):
        import x360_arena_art as art
        from exp_runtime import x360_puzzle
        self.assertEqual(x360_puzzle.SOUND_DRAG, art.PUZZLE_BASE + 5)
        self.assertEqual(x360_puzzle.SOUND_CLEAR, art.PUZZLE_BASE + 6)
        self.assertGreater(art.PUZZLE_BASE, art.LEASH_BASE + 4)
        self.assertIn(art.PUZZLE_JEWELS + 5 * 60 - 1, art.SKIN_IDS)

    def test_the_leashs_art_comes_from_the_hud(self):
        import io
        import x360_arena_art as art
        from PIL import Image

        def picture(size, mode='RGB', colour='white'):
            out = io.BytesIO()
            Image.new(mode, size, colour).save(out, 'PNG')
            return out.getvalue()
        sheet = Image.new('RGB', (256, 256), (0, 0, 0))
        sheet.paste((0, 200, 0), (0, 64, 64, 128))              # the second row's first cell: left and right
        out = io.BytesIO()
        sheet.save(out, 'PNG')
        hud = 'data/art/hud/'
        files = {hud + 'icons.jpg': out.getvalue(), hud + 'icons_a.jpg': picture((256, 256), 'L'),
                 **{hud + f'{name}.jpg': picture((64, 64)) for name in ('power_bar_fl', 'stick_shake_side', 'stick_shake_frontback')},
                 **{hud + f'{name}_a.jpg': picture((64, 64), 'L') for name in ('power_bar_fl', 'stick_shake_side', 'stick_shake_frontback')}}
        resources, entry = art.leash(files)
        self.assertTrue(all(i in art.SKIN_IDS for i in resources))
        arrows = Image.open(io.BytesIO(resources[entry['arrows']['leftright']])).convert('RGBA')
        self.assertEqual((arrows.size, arrows.getpixel((5, 5))), ((64, 64), (0, 200, 0, 255)))
        self.assertEqual(set(entry['stick']), {'leftright', 'updown'})
        self.assertLess(art.SLOT_BASE + 10, art.LEASH_BASE)     # clear of the slot machine's

    def test_the_slot_machines_art_comes_from_the_hud_with_its_labels_font(self):
        import io
        import x360_arena_art as art
        from PIL import Image
        from exp_runtime import x360_games

        def png(size=(64, 64), mode='RGBA'):
            out = io.BytesIO()
            Image.new(mode, size, 'white').save(out, 'PNG')
            return out.getvalue()
        sheet = Image.new('RGB', (256, 256), (0, 0, 0))
        sheet.paste((200, 0, 0), (0, 0, 64, 64))                # cell 0: the cross
        out = io.BytesIO()
        sheet.save(out, 'PNG')
        files = {'data/art/hud/icons.jpg': out.getvalue(), 'data/art/hud/icons_a.jpg': png((256, 256), 'L'),
                 'data/art/hud/narrator.png': png((512, 256)), 'data/art/hud/slot_window.png': png(),
                 'data/art/hud/clock.jpg': png(), 'data/art/hud/clock_a.jpg': png(mode='L'),
                 'data/art/fonts/bleeker.fnt': b'info face="B" size=50\ncommon lineHeight=50 base=39 pages=1\n'
                                               b'page id=0 file="bleeker_00.png"\n'
                                               b'char id=65 x=0 y=0 width=9 height=9 xoffset=0 yoffset=0 xadvance=9 page=0\n',
                 'data/art/fonts/bleeker_black.png': png(),
                 **{path: path.encode() for path in art.SLOT_SOUNDS}}
        resources, entry = art.slot(files, lambda data: data + b' pcm')
        self.assertTrue(all(i in art.SKIN_IDS for i in resources))
        cross = Image.open(io.BytesIO(resources[entry['icons']['cross']])).convert('RGBA')
        self.assertEqual((cross.size, cross.getpixel((5, 5))), ((64, 64), (200, 0, 0, 255)))
        self.assertEqual(entry['font']['pages'], [art.SLOT_BASE + 10])
        for path, resource in zip(art.SLOT_SOUNDS, (x360_games.SOUND_SUCCESS, x360_games.SOUND_MISS, x360_games.SOUND_TIMER)):
            self.assertEqual(resources[resource], path.encode() + b' pcm')

    def test_the_title_screens_layers_make_the_backdrop(self):
        import io
        import x360_arena_art as art
        from PIL import Image

        def image(mode, size, colour, fmt='JPEG'):
            out = io.BytesIO()
            Image.new(mode, size, colour).save(out, fmt)
            return out.getvalue()
        files = {art.GUI + 'background.jpg': image('RGB', (32, 32), (0, 0, 200)),
                 art.GUI + 'clouds.jpg': image('RGB', (16, 8), (255, 255, 255)),
                 art.GUI + 'clouds_a.jpg': image('L', (16, 8), 128),
                 art.GUI + 'stain_clouds.png': image('RGBA', (16, 16), (0, 0, 0, 0), 'PNG'),
                 art.GUI + 'school_building.jpg': image('RGB', (8, 8), (10, 10, 10)),
                 art.GUI + 'school_building_a.jpg': image('L', (8, 8), 255),
                 art.GUI + 'city.jpg': image('RGB', (16, 16), (0, 0, 0)),
                 art.GUI + 'city_a.jpg': image('L', (16, 16), 0),
                 art.GUI + 'black_line_a.jpg': image('L', (16, 16), 0)}
        for i in range(art.TITLE_RAYS):
            mask = Image.new('L', (64, 64), 0)
            mask.paste(255, (8 * i, 4, 8 * i + 4, 60))         # glint i: a stripe further right each time
            out = io.BytesIO()
            mask.save(out, 'JPEG', quality=95)
            files[f'{art.GUI}raylight_{i + 1}_a.jpg'] = out.getvalue()
        resources, entry = art.title(files)
        self.assertEqual(sorted(resources), list(range(art.TITLE_BASE, art.TITLE_BASE + 4)))
        self.assertTrue(all(i in art.SKIN_IDS for i in resources))
        self.assertEqual(Image.open(io.BytesIO(resources[entry['sky']])).size, art.TITLE_SIZE)
        self.assertEqual(entry['clouds'], dict(id=art.TITLE_BASE + 1, opacity=0.35, speed=0.01))
        self.assertEqual((entry['rays']['ms'], entry['rays']['every']), (50, 3000))
        frames = entry['rays']['frames']
        self.assertEqual(len(frames), art.TITLE_RAYS)
        # Each glint cut to its stripe (past the JPEG's noise), its box a fraction of the screen
        left, top, right, bottom = frames[2]['box']
        self.assertAlmostEqual(left, 16 / 64, delta=0.05)
        self.assertAlmostEqual(right, 20 / 64, delta=0.05)
        atlas = Image.open(io.BytesIO(resources[entry['rays']['atlas']]))
        x, y, w, h = frames[2]['rect']
        self.assertEqual(atlas.getpixel((x + w // 2, y + h // 2)), (255, 255, 255, 255))
        # The front: the school where it rests, over the clear stain layer
        front = Image.open(io.BytesIO(resources[entry['front']]))
        sx, sy, sw, sh = art.TITLE_SCHOOL
        w, h = art.TITLE_SIZE
        self.assertEqual(front.getpixel((round((sx + sw / 4) * w), round((sy + sh / 4) * h)))[3], 255)
        self.assertEqual(front.getpixel((10, 10))[3], 0)


if __name__ == '__main__':
    unittest.main()
