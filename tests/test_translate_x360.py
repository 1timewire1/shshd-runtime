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
                         ['(idea >= 5)', '(idea >= 3)'])
        self.assertEqual([n.params['expression'] for n in builder.nodes if n.kind == 'set'], ['3', '2', '0'])
        record = play(compile_project(project), [1])              # the word game runs out at 0: the leash is lost
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
        self.assertFalse(any(x360.addon_holds(i) for i in (1, 25001, 26000, 26110, 26250, 27250)))

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
        self.assertEqual(addon_record(archive), ('requires', ((x360.ADDON_ID, x360.ADDON_REVISION),)))
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


@unittest.skipUnless(HAS_PIL, 'x360_arena_art.py draws with Pillow')
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

    def test_the_skin_stays_in_its_ids_and_replaces_new_rules_sounds_and_music(self):
        import x360_arena_art as art
        self.assertTrue(all(i in art.SKIN_IDS for i in (art.SPEC, art.PICTURE_BASE, art.FONT_PAGE_BASE,
                                                        art.SOUND_BASE + len(art.SOUNDS) - 1, art.MUSIC)))
        self.assertLessEqual(art.PICTURE_BASE + len(art.PICTURES) + len(art.DERIVED) + art.NR_ITEMS, art.FONT_PAGE_BASE)
        self.assertEqual(set(art.SOUND_TRACKS), {13, 1, 11})        # right, wrong, Fever's bonus noise (the swaps)
        self.assertEqual(art.MUSIC_TRACK, 14)                       # the games' music


if __name__ == '__main__':
    unittest.main()
