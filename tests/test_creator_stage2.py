"""Creator catch-up Stage 2 (2026-11-17): Surviving Hollywood as a primary add-on, the quest journal, option details, the word
grid's part score and the stat-changes page, each compiled and played in the engine."""
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

from exp_runtime.creator.compiler import compile_project
from exp_runtime.creator.model import Choice, Node, Project, ProjectError, project_from_record, project_record
from exp_runtime.exp import ExpArchive


def session_for(project):
    from exp_runtime.presentation import presentation_record
    from exp_runtime.runtime import Session
    archive = ExpArchive(compile_project(project))
    resources = SimpleNamespace(library=SimpleNamespace(game_id='shs', directory=Path(tempfile.gettempdir())),
                                record={'titles': ['T'] * 5, 'id': 'x', 'pack_id': project.pack_id,
                                        'episode_id': project.episode_id},
                                identity=dict(profile='test', episode_sha256='0' * 64),
                                presentation=presentation_record(archive),
                                program=archive.programs().__getitem__, linked_program=lambda: None,
                                exists=lambda key: key in archive.entries, read_asset=archive.read)
    session = Session(resources, ephemeral=True)
    session.advance()
    return session


def story(*nodes, **fields):
    nodes = list(nodes) + [Node('end', 'end')]
    return Project(title='Stage 2', game='shs', start=nodes[0].id, nodes=nodes, **fields)


def through(session, until=('finished', 'episode_exit'), line=None):
    """Acknowledge dialogue and panels until a choice, the end or the dialogue `line`; returns the pending action."""
    for _ in range(50):
        action = session.pending
        if action is None or action.name in until or action.name == 'choice':
            return action
        if line is not None and action.name == 'dialogue' and action.details.get('text') == line:
            return action
        if session.transitioning:                   # (a scene label's own entrance holds input)
            session.tick(100)
            continue
        if action.name == 'dialogue' and not session.engine.dialogue_animation.complete or action.name == 'message_panel':
            session.tick(1000)                      # the line's reveal, the panel's entrance
            continue
        session.answer(None)
    return session.pending


class Journal(unittest.TestCase):
    def project(self, episode_id=1):
        return story(
            Node('q0', 'quest', params={'number': 0, 'title': 'Get the part'}, text='Rehearse\nImpress $USR', next='q2'),
            Node('q2', 'quest', params={'number': 2, 'title': 'Pay rent'}, text='$500 by Friday', next='u'),
            Node('u', 'journal_updated', params={'sound': 8007}, next='say'),
            Node('say', text='Done.', next='gone'),
            Node('gone', 'quest', params={'number': 0, 'title': ''}, text='', next='later'),
            Node('later', text='Later.', next='end'),
            journal=[dict(label='Money', key=500, prefix='$'), dict(label='Looks', key=501, prefix='')],
            episode_id=episode_id)

    def test_the_record_names_the_episode_s_own_keys_and_stats(self):
        from exp_runtime.presentation import presentation_record
        record = presentation_record(ExpArchive(compile_project(self.project())))
        count, title, lines, stats = record['journal']
        self.assertEqual(count, 31728)
        self.assertEqual((title % 3, lines % 3), ('{quest 30000.1 title 3}', '{quest 30000.1 lines 3}'))
        self.assertEqual(stats, (('Money', 500, '$'), ('Looks', 501, '')))
        other = presentation_record(ExpArchive(compile_project(self.project(episode_id=2))))
        self.assertNotEqual(other['journal'][1], title)      # the shared names table never mixes two episodes' quests

    def test_the_pause_menu_reads_the_quests_and_stats(self):
        from exp_runtime import quest_journal
        session = session_for(self.project())
        session.engine.strings['$USR'] = 'Riley'
        session.engine.numbers[session.engine.number_key(0, 500)] = 55
        self.assertEqual(session.pending.details['text'], 'Done.')          # both quests set, the label shown
        self.assertEqual(quest_journal.quests(session), [('Get the part', 'Rehearse\nImpress Riley'),
                                                         ('Pay rent', '$500 by Friday')])
        self.assertEqual(quest_journal.stats(session), 'Money: $55\nLooks: 0')
        through(session, line='Later.')
        self.assertEqual([title for title, _ in quest_journal.quests(session)], ['Pay rent'])      # an empty title takes it off

    def test_journal_updated_is_a_scene_label_with_its_sound(self):
        from exp_runtime.decode.bytecode import decode_program
        program = decode_program(ExpArchive(compile_project(self.project())).read(25001))
        calls = [i.operand >> 8 for i in program.instructions if i.opcode == 0x1f]
        self.assertIn(90, calls)
        self.assertIn(79, calls)
        self.assertIn('Quest journal updated', program.strings() if hasattr(program, 'strings') else
                      ExpArchive(compile_project(self.project())).read(25001).decode('latin-1'))

    def test_a_project_without_quests_or_stats_has_no_journal(self):
        from exp_runtime.presentation import presentation_record
        record = presentation_record(ExpArchive(compile_project(story(Node('a', text='Hi.', next='end')))))
        self.assertNotIn('journal', record)

    def test_quests_are_shs_only_and_numbered_0_to_63(self):
        bad = self.project()
        bad.nodes[0].params['number'] = 64
        with self.assertRaisesRegex(ProjectError, '0 to 63'):
            compile_project(bad)
        cod = self.project()
        cod.game = 'cod'
        with self.assertRaises(ProjectError):
            compile_project(cod)

    def test_stats_are_checked(self):
        for journal in ([dict(label='', key=1, prefix='')], [dict(label='A', key=1)], [dict(label='A', key=1, prefix='')] * 9):
            with self.subTest(journal=journal):
                with self.assertRaises(ProjectError):
                    compile_project(story(Node('a', text='Hi.', next='end'), journal=journal))

    def test_the_record_member_is_checked(self):
        from exp_runtime.presentation import FORMAT, VERSION, normalize
        good = dict(count=1, title='{t %d}', lines='{l %d}', stats=[['Money', 2, '$']])
        self.assertEqual(normalize(dict(format=FORMAT, version=VERSION, journal=good))['journal'],
                         (1, '{t %d}', '{l %d}', (('Money', 2, '$'),)))
        for bad in (dict(good, title='{t}'), dict(good, lines='{l %d %d}'), dict(good, stats=[['', 2, '']]),
                    dict(good, stats=[['A', 2]]), {k: v for k, v in good.items() if k != 'stats'}):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    normalize(dict(format=FORMAT, version=VERSION, journal=bad))


class OptionDetails(unittest.TestCase):
    def test_a_detail_rides_under_its_option(self):
        project = story(Node('c', 'choice', text='Where to?', options=[
            Choice('Mall', 'end', detail='Open 9 am to 9 pm'), Choice('Home', 'end')]))
        session = session_for(project)
        action = through(session)
        self.assertEqual(action.details['options'], ['Mall', 'Home'])
        self.assertEqual(action.details['details'], ['Open 9 am to 9 pm', ''])

    def test_a_detail_is_one_plain_line_and_is_translatable(self):
        from exp_runtime.creator.features import text_fields
        project = story(Node('c', 'choice', text='Where to?', options=[
            Choice('Mall', 'end', detail='Open\nlate'), Choice('Home', 'end')]))
        with self.assertRaises(ProjectError):
            compile_project(project)
        project.nodes[0].options[0].detail = 'Open late'
        self.assertEqual(text_fields(project)['node.c.option.0.detail'], 'Open late')

    def test_an_older_project_without_details_or_a_journal_still_opens(self):
        record = project_record(story(Node('c', 'choice', text='Pick', options=[Choice('A', 'end'), Choice('B', 'end')])))
        for node in record['nodes']:
            for option in node['options']:
                del option['detail']
        del record['journal']
        project = project_from_record(record)
        self.assertEqual([o.detail for o in project.nodes[0].options], ['', ''])
        self.assertEqual(project.journal, [])


class GridPartScore(unittest.TestCase):
    def project(self, part_score='letters'):
        from copy import deepcopy
        from exp_runtime.creator.features import DEFAULTS
        params = deepcopy(DEFAULTS['grid'])
        params['part_score'] = part_score
        return story(Node('g', 'grid', params=params, next='end'))

    def test_it_reads_service_224_right_after_the_grid(self):
        from exp_runtime.decode.bytecode import decode_program
        program = decode_program(ExpArchive(compile_project(self.project())).read(25001))
        calls = [i.operand >> 8 for i in program.instructions if i.opcode == 0x1f]
        self.assertEqual(calls[calls.index(96) + 1], 224)
        plain = decode_program(ExpArchive(compile_project(self.project(''))).read(25001))
        self.assertNotIn(224, [i.operand >> 8 for i in plain.instructions if i.opcode == 0x1f])

    def test_it_stores_the_part_score_and_counts_as_this_runtime_s(self):
        from exp_runtime.creator.addons import mechanics
        from exp_runtime.creator.debugger import DebugSession
        self.assertIn("the word grid's part score", mechanics(self.project()))
        self.assertNotIn("the word grid's part score", mechanics(self.project('')))
        debugger = DebugSession(self.project(), seed=1)
        try:
            debugger.resume()
            self.assertEqual(debugger.session.pending.name, 'word_grid')
            debugger.session.engine.word_grid.part_score = 2
            debugger.paused, debugger._step = False, False
            try:
                debugger.session.skip_minigame(False)
            except Exception as error:
                if type(error).__name__ != '_Paused':
                    raise
            debugger.resume()
            self.assertEqual(debugger.state()['variables']['letters'], 2)
        finally:
            debugger.close()

    def test_the_variable_must_be_a_name(self):
        with self.assertRaises(ProjectError):
            compile_project(self.project('two words'))

    def test_the_constants_match_the_engine(self):
        from exp_runtime import engine
        from exp_runtime.creator import compiler
        self.assertEqual((compiler.GRID_PART_SCORE, compiler.OPTION_DETAIL), (engine.GRID_PART_SCORE, engine.OPTION_DETAIL))


class StatChanges(unittest.TestCase):
    def test_the_preset_signs_each_rise(self):
        from exp_runtime.creator.stat_pages import stat_changes_page
        self.assertEqual(stat_changes_page([('Looks', 501), ('Stress', 503)]),
                         ('Stat changes', 'Looks: {+prop(0, 501)}\nStress: {+prop(0, 503)}'))
        self.assertEqual(stat_changes_page([('Looks', 501)], signed=False)[1], 'Looks: {prop(0, 501)}')

    def test_a_signed_placeholder_shows_plus_before_a_rise_only(self):
        for value, shown in ((3, 'Looks: +3'), (-2, 'Looks: -2'), (0, 'Looks: 0')):
            with self.subTest(value=value):
                project = story(
                    Node('s', 'score', params={'owner': 0, 'key': 501, 'operation': 'set', 'value': value, 'result': 'looks'},
                         next='m'),
                    Node('m', 'message', params={'title': 'Stat changes'}, text='Looks: {+prop(0, 501)}', next='end'))
                session = session_for(project)
                self.assertEqual(session.pending.name, 'message_panel')
                self.assertEqual((session.engine.message_panel.title, session.engine.message_panel.text),
                                 ('Stat changes', shown))


class HollywoodPrimary(unittest.TestCase):
    def test_its_settings_come_from_its_pack(self):
        from exp_runtime.shs import profile
        self.assertEqual(profile.ADDON_FEATURE_PACKS[('shshw', '')], 31700)
        from exp_runtime.creator.addons import ADDON_FEATURES
        self.assertIn('shshw', ADDON_FEATURES)

    def test_its_catch_game_needs_nothing_from_brew(self):
        from copy import deepcopy
        from exp_runtime.creator.addons import drop_unused_addons, node_addon
        from exp_runtime.creator.features import DEFAULTS
        params = deepcopy(DEFAULTS['brew_catch'])
        params['sizes'] = {'109': [20, 24], '149': [18, 18], '156': [16, 16]}
        project = story(Node('q', 'minigames_available', params={'for': 'brew_catch', 'result': 'real'}, next='c'),
                        Node('c', 'brew_catch', params=params, next='end'),
                        addons=[dict(id='shshw', revision=6, primary=True, edition='')])
        self.assertEqual(node_addon(project, 'brew_catch'), 'shshw')
        compile_project(project)                                        # no shsbrew asked for
        drop_unused_addons(project)
        self.assertEqual([entry['id'] for entry in project.addons], ['shshw'])
        project.addons[0]['primary'] = False
        self.assertEqual(node_addon(project, 'brew_catch'), 'shsbrew')
        with self.assertRaisesRegex(ProjectError, 'shsbrew'):
            compile_project(project)

    def test_a_creator_episode_on_it_takes_its_backdrop_and_catch_skin(self):
        from exp_runtime.content import pack_setting
        resources = SimpleNamespace(library=SimpleNamespace(game_id='shs'), record={'pack_id': 30000},
                                    presentation={'addons': ('shshw', '')})
        self.assertEqual(pack_setting(resources, 'TRANSLATED_CATCH_ADDON'), 'shshw')
        self.assertEqual(pack_setting(resources, 'TRANSLATED_FRAME_BACKDROP'), 26990)



def png():
    from io import BytesIO
    from PIL import Image
    output = BytesIO()
    Image.new('RGB', (16, 16), (200, 40, 40)).save(output, format='PNG')
    return output.getvalue()


class FakeArchive:
    def __init__(self, entries):
        self.data = entries
        self.entries = set(entries)

    def read(self, resource):
        return self.data[resource]


class FakeLibrary:
    """A library holding only the add-ons given, as content.ContentLibrary answers `addon`."""
    game_id = 'shs'

    def __init__(self, **addons):
        self.addons_held = addons
        self.dsi_backgrounds = self.hollywood_art = True

    def addon(self, addon_id):
        archive = self.addons_held.get(addon_id)
        return None if archive is None else ({'addon': addon_id, 'title': addon_id, 'revision': 1, 'file': addon_id}, archive)


def dsi_addon():
    import json
    spec = dict(screens={'Beach_Night': [26001, 26002], 'Classroom_Day': [26003, 26004]}, bank={}, stories=[])
    return FakeArchive({26000: json.dumps(spec).encode(), 26001: b'l', 26002: b'r', 26003: b'l', 26004: b'r'})


@unittest.skipUnless(__import__('importlib').util.find_spec('PIL'), 'needs Pillow')
class OptionalArt(unittest.TestCase):
    def project(self, art):
        project = story(Node('b', 'background', next='a'), Node('a', text='Hi.', next='end'))
        picture = project.add_image('Beach', png())
        project.nodes[0].asset = picture.id
        project.optional_art = art(picture.id)
        return project, picture.id

    def test_the_record_carries_it_and_the_add_on_stays_optional(self):
        from exp_runtime.presentation import presentation_record
        project, own = self.project(lambda own: {'shsdsi': {str(own): 26001}, 'shshw': {str(own): 26100}})
        record = presentation_record(ExpArchive(compile_project(project)))
        self.assertEqual(record['optional_art'], {'shsdsi': {own: 26001}, 'shshw': {own: 26100}})
        self.assertNotIn('addons', record)
        self.assertEqual(project.addons, [])

    def test_it_is_checked(self):
        for art in ({'shsbrew': {'26000': 1}}, {'shsdsi': {'12': 26001}}, {'shsdsi': {'x': 26001}}, {'shsdsi': {'26000': -1}}):
            with self.subTest(art=art):
                project, _ = self.project(lambda own: art)
                with self.assertRaises(ProjectError):
                    compile_project(project)

    def test_a_picture_named_as_a_dsi_location_shows_it(self):
        from exp_runtime import dsi
        from exp_runtime.presentation import presentation_record
        project, own = self.project(lambda own: {'shsdsi': {str(own): 26001}})
        archive = ExpArchive(compile_project(project))
        library = FakeLibrary(shsdsi=dsi_addon())
        resources = SimpleNamespace(library=library, record={'pack_id': 30000, 'titles': ['Stage 2']},
                                    presentation=presentation_record(archive), required_addons=(),
                                    programs=archive.programs(), exists=lambda key: key in archive.entries)
        self.assertEqual(dsi.episode_pictures(resources), {own: 'Beach_Night'})
        resources.presentation = {}                         # unnamed, its own picture has no counterpart
        self.assertIsNone(dsi.episode_pictures(resources))

    def test_the_dialog_lists_each_add_on_s_pictures(self):
        from exp_runtime.creator.optional_art import addon_pictures
        library = FakeLibrary(shsdsi=dsi_addon(), shshw=FakeArchive({26100: png(), 26101: b'not a picture', 31000: png()}))
        self.assertEqual(addon_pictures(library, 'shsdsi'), [('Beach_Night (DSi)', 26001), ('Classroom_Day (DSi)', 26003)])
        self.assertEqual(addon_pictures(library, 'shshw'), [('26100 (shshw)', 26100), ('31000 (shshw)', 31000)])
        self.assertEqual(addon_pictures(FakeLibrary(), 'shshw'), [])

    def test_hollywood_art_reads_through_the_episode(self):
        from exp_runtime.content import optional_art_offered
        resources = SimpleNamespace(library=FakeLibrary(shshw=FakeArchive({26100: png()})),
                                    presentation={'optional_art': {'shshw': {26000: 26100}}}, record={'pack_id': 30000})
        self.assertTrue(optional_art_offered(resources, 'hollywood_art'))



class HollywoodArtNames(unittest.TestCase):
    def test_its_portraits_silhouettes_and_backgrounds_are_named(self):
        import json
        from exp_runtime.creator.assets import addon_asset_labels
        spec = dict(portraits={'2012': 27012}, flipped={'2012': 27112}, silhouettes=[27200, 27201],
                    backgrounds={'1504': [26012, 26013, 26014]})
        library = FakeLibrary(shshw=FakeArchive({26998: json.dumps(spec).encode(), 27012: b'', 27112: b'', 27200: b''}))
        self.assertEqual(addon_asset_labels(library, 'shshw'), {
            27012: 'portrait 2012', 27112: 'portrait 2012, facing left', 27200: 'silhouette 1', 27201: 'silhouette 2',
            26012: 'background 1504, day', 26013: 'background 1504, night', 26014: 'background 1504, sunset'})
        self.assertEqual(addon_asset_labels(FakeLibrary(shsbrew=FakeArchive({26998: b'{"catch": {}}'})), 'shsbrew'), {})
        self.assertEqual(addon_asset_labels(FakeLibrary(), 'shshw'), {})


if __name__ == '__main__':
    unittest.main()
