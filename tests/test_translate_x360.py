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
    OpenDialog("a",1)
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
        self.assertEqual(proto.text('t/hello'), '&:130 180 80;Hi Andy!')
        self.assertEqual(x360.story_text(proto.text('t/hello')), 'Hi Andy!')
        self.assertEqual(x360.story_text('Say `yes`', label=True), 'Say yes')
        self.assertEqual(x360.story_text(proto.text('t/sad')), 'Oh well...')

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
        self.assertEqual(lines(first), ['Hi Andy!', 'Glad you said yes.', 'You scored.', 'The end'])
        self.assertEqual([e['expression'] for e in first if e['kind'] == 'line'][:2], [0, 2])   # yes: happy
        self.assertEqual(first[-1]['kind'], 'exit')
        self.assertEqual(lines(play(data, [2])), lines(first))     # "Secret" is locked: the first answer plays
        self.assertEqual(lines(play(data, [1])), ['Hi Andy!', 'Oh well...', 'The end'])

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


if __name__ == '__main__':
    unittest.main()
