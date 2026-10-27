"""tools/translate x360.py and lua_subset.py on authored data (no prototype content): the pak and string encodings,
the Lua subset, and a small story played through the production Session."""
import importlib.util
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

        story = x360.Story('Test', 1, ['t/one'], [x360.Cast('a', 'Andy', 1, bank=2050)], {'lot': 23}, player='a')
        project = x360.translate(self.prototype(), story, Art(),
                                 music_files={'dont_trust_me': b'intro', 'dont_trust_me_loop': b'loop'})
        self.assertEqual([n.params for n in project.nodes if n.kind == 'music'],
                         [{'resource': x360.MUSIC_INTRO, 'loop': True}])
        self.assertEqual({a.id for a in project.assets} >= {x360.MUSIC_INTRO, x360.MUSIC_LOOP}, True)

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


if __name__ == '__main__':
    unittest.main()
