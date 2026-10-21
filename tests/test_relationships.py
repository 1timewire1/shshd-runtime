import copy
import importlib.util
from itertools import product
import json
import os
from pathlib import Path
import unittest

from exp_runtime.engine import EngineState
from exp_runtime.relationships import RelationshipAnimation, RelationshipChange
from exp_runtime.runtime import SaveError, Session
from test_runtime import Resources, answer_screen, host_call, text_words
from test_vm import program


def npc_session(*, value=0, previous_asset=3012, previous_count=-1, words=None):
    words, refs = text_words(words or 'The NPC has something to say.')
    r = Resources(program(*host_call(13, refs[0], 1),
                          *host_call(53, 1, 3000), 0x21, *host_call(53, 1, 3001), 0x21,
                          (0x1f, 0xfe02), words=words))
    s = Session(r)
    s.engine.ui_defaults = {74: 0, 75: 7}
    s.engine.character_names[1] = 'Friend'
    s.engine.character_art_variants[1] = [100] * 5
    for key, number in ((407, value), (3000, previous_asset), (3001, previous_count)):
        s.engine.numbers[s.engine.number_key(1, key)] = number
    s.advance()
    return s


class RelationshipTests(unittest.TestCase):
    def test_suppressed_android_widget_retains_cancelled_children_across_speakers_and_teardown(self):
        for kind, (value, prior_count, elapsed) in product(('apk', 'ipa'), ((0, 3, 1400), (3, 1, 1450))):
            for intervening in ('none', 'narration', 'close', 'player', 'special'):
                with self.subTest(kind=kind, value=value, intervening=intervening):
                    words, refs = text_words('X')
                    middle = (host_call(13, refs[0], 7) if intervening == 'narration' else
                              host_call(13, refs[0], 0) if intervening == 'player' else
                              host_call(39) if intervening == 'close' else [])
                    target = 45 if intervening == 'special' else 2
                    r = Resources(program(*host_call(13, refs[0], 1), *middle,
                                          *host_call(13, refs[0], target), 0x33, words=words))
                    r.library.kind = kind
                    s = Session(r)
                    s.engine.ui_defaults = {74: 0, 75: 7}
                    s.engine.character_names = {0: 'Player', 1: 'First', target: 'Next'}
                    s.engine.character_art_variants = {c: [100] * 5 for c in (0, 1, target)}
                    for key, number in ((407, value), (3000, 3012), (3001, prior_count)):
                        s.engine.numbers[s.engine.number_key(1, key)] = number
                    s.engine.numbers[s.engine.number_key(target, 629)] = 1
                    s.advance(); s.tick(elapsed)
                    frozen = s.engine.dialogue_animation.relationship.poses()
                    self.assertTrue(frozen)
                    self.assertTrue(s.engine.dialogue_animation.complete)
                    sound_serial = s.engine.sound_serial
                    s.answer()
                    if intervening in ('narration', 'player'):
                        self.assertIsNone(s.engine.dialogue_animation.relationship)
                        s.tick(2000); s.answer()
                    rel = s.engine.dialogue_animation.relationship
                    expected = () if kind == 'ipa' or intervening in ('player', 'special') else frozen
                    self.assertEqual(rel.poses(), expected)
                    self.assertEqual(s.engine.sound_serial, sound_serial)
                    saved = s.snapshot()
                    restored = Session.from_snapshot(r, json.loads(json.dumps(saved)))
                    self.assertEqual(restored.snapshot(), saved)
                    for session in (s, restored):
                        session.tick(3000)
                        self.assertEqual(session.engine.dialogue_animation.relationship.poses(), expected)

    def test_retained_pose_saves_are_validated_and_legacy_state_is_not_invented(self):
        s = npc_session(value=3, previous_count=1)
        s.tick(1450)
        s.engine.dialogue_history.remember(s.engine.dialogue_animation)
        saved = s.snapshot()
        for key, bad in (('x', float('nan')), ('rotation', -999.), ('asset_id', 42), ('flash_alpha', 201)):
            invalid = copy.deepcopy(saved)
            invalid['engine']['dialogue_history']['indicators'][0][key] = bad
            with self.subTest(key=key), self.assertRaises(SaveError):
                Session.from_snapshot(s.resources, invalid)
        old = copy.deepcopy(saved)
        old['version'] = 22
        del old['engine']['text_history']
        del old['engine']['dialogue_history']['indicators']
        del old['engine']['dialogue_animation']['relationship']['retained']
        migrated = Session.from_snapshot(s.resources, old)
        self.assertEqual(migrated.vm.snapshot(), s.vm.snapshot())
        self.assertEqual(migrated.engine.dialogue_animation.relationship.poses(),
                         s.engine.dialogue_animation.relationship.poses())
        self.assertEqual(migrated.engine.dialogue_history.indicators, [])

    def test_vm_relationship_updates_refresh_icons_and_script_visible_caches(self):
        words, refs = text_words('First meeting.', 'The relationship changes.')
        r = Resources(program(
            *host_call(52, 1, 407, 0), *host_call(13, refs[0], 1),
            *host_call(52, 1, 403, 3),  # Unrelated property must not select the icons.
            *host_call(52, 1, 407, -4), *host_call(13, refs[1], 1),
            *host_call(53, 1, 3000), 0x21, *host_call(53, 1, 3001), 0x21,
            (0x1f, 0xfe02), words=words))
        initial = Session(r)
        initial.engine.ui_defaults = {74: 0, 75: 7}
        initial.engine.character_names[1] = 'Friend'
        initial.engine.character_art_variants[1] = [100] * 5
        initial.advance()
        first = initial.engine.dialogue_animation.relationship.change
        self.assertEqual((first.asset_id, first.count), (3012, 1))
        restored = Session.from_snapshot(r, json.loads(json.dumps(initial.snapshot())))
        for session in (initial, restored):
            with self.subTest(restored=session is restored):
                self.assertEqual(answer_screen(session).name, 'dialogue')
                rel = session.engine.dialogue_animation.relationship
                self.assertEqual((rel.change.asset_id, rel.change.count,
                                  rel.change.previous_asset, rel.change.previous_count),
                                 (3011, 4, 3012, 1))
                self.assertEqual(session.engine.numbers[session.engine.number_key(1, 407)], -4)
                self.assertEqual(session.engine.numbers[session.engine.number_key(1, 403)], 3)
                self.assertEqual(session.engine.sound_ids, [8006])
                held = session.vm.snapshot()
                session.tick(rel.duration_ms)
                self.assertEqual([pose.asset_id for pose in rel.poses()], [3011] * 4)
                self.assertEqual(session.vm.snapshot(), held)
                self.assertEqual(answer_screen(session).request.args, (3011, 4))

    @unittest.skipUnless(Path('.shs-library/library.json').is_file(), 'user content unavailable')
    def test_football_star_adam_relationship_follows_the_original_script(self):
        from exp_runtime.content import ContentLibrary
        with ContentLibrary(Path('.shs-library')) as library:
            session = Session(library.open_episode('Football Star'))
            session.advance()
            seen = []
            for _ in range(60):
                action = session.pending
                if action.name == 'dialogue' and action.details['visible_character_id'] == 10:
                    change = session.engine.dialogue_animation.relationship.change
                    value = session.engine.numbers[session.engine.number_key(10, 407)]
                    seen.append((session.scene, action.request.pc, value, change.asset_id, change.count))
                    if len(seen) == 3:
                        break
                if action.name == 'choice':
                    answer_screen(session, next(i for i, enabled in enumerate(action.details['enabled']) if enabled))
                elif action.name == 'text_input':
                    session.answer('Alex')
                elif action.name == 'character_picker':
                    session.answer(0); session.tick(25); session.answer()
                elif action.name in ('dialogue', 'presentation', 'vm_pause'):
                    answer_screen(session)
                else:
                    self.fail(f'Unexpected opening action: {action.name}')
            self.assertEqual(seen, [(25006, 445, -1, 3011, 1), (25006, 453, -1, 3011, 1),
                                   (25006, 462, -4, 3011, 4)])
            rel = session.engine.dialogue_animation.relationship
            self.assertEqual((rel.change.previous_asset, rel.change.previous_count), (3011, 1))
            session.tick(rel.duration_ms)
            self.assertEqual([pose.asset_id for pose in rel.poses()], [3011] * 4)

    def test_native_icon_count_romance_suppression_and_visible_npc_rules(self):
        for value, count in ((-32768, 4), (-4, 4), (-3, 3), (-2, 2), (-1, 1),
                             (0, 1), (1, 2), (2, 3), (3, 4), (32767, 4)):
            for romance in (0, 1):
                e = EngineState()
                e.numbers[e.number_key(0, 601)] = romance
                e.numbers[e.number_key(1, 407)] = value
                rel = e.prepare_relationship(1)
                self.assertEqual((rel.asset_id, rel.count), (3011 if value < 0 else 3010 if romance else 3012, count))
                e.numbers[e.number_key(1, 629)] = 1
                hidden = e.prepare_relationship(1)
                self.assertEqual(hidden.asset_id, -1)
                self.assertFalse(RelationshipAnimation(hidden, 0).poses())
                e.numbers[e.number_key(1, 629)] = 2  # Exactly 1 suppresses.
                self.assertGreater(e.prepare_relationship(1).asset_id, 0)
        e = EngineState()
        self.assertIsNone(e.prepare_relationship(0)); self.assertIsNone(e.prepare_relationship(-1))
        self.assertEqual(e.numbers, {})
        e.character_art_variants = {1: [100], 7: [101]}
        e.ui_defaults[75] = 7
        for character in (2, 7):  # Missing art and the configured narrator.
            self.assertIsNone(e.present_dialogue(character, 0, 'Text', 0)['relationship'])
        self.assertEqual(e.numbers, {})

    def test_cache_side_effects_are_visible_to_scripts_and_not_replayed_by_render_or_load(self):
        s = npc_session(value=2, previous_count=1)
        self.assertEqual(s.engine.sound_ids, [8009])
        change = s.engine.dialogue_animation.relationship.change
        self.assertEqual((change.previous_count, change.count), (1, 3))
        self.assertEqual(s.engine.numbers[s.engine.number_key(1, 3001)], 3)
        before = s.snapshot()
        s = Session.from_snapshot(s.resources, json.loads(json.dumps(before)))
        self.assertEqual(s.snapshot(), before)
        self.assertEqual(answer_screen(s).request.args, (3012, 3))
        self.assertEqual(s.engine.result_cells, [None] * 10)

    def test_staggered_shortest_arc_gain_flash_and_dialogue_delay(self):
        s = npc_session(value=2, previous_count=1)
        motion = s.engine.dialogue_animation
        rel = motion.relationship
        self.assertEqual((rel.delay_ms, rel.change.extra_delay_ms), (550, 500))
        self.assertEqual((motion.name_delay_ms, motion.text_delay_ms), (1170, 1170))
        held = s.vm.snapshot()
        s.tick(549); self.assertEqual(rel.poses(), ())
        s.tick(1); poses = rel.poses()
        self.assertEqual(len(poses), 2)  # Old icon and the first incoming icon.
        self.assertAlmostEqual(poses[1].x, 62); self.assertAlmostEqual(poses[1].y, -17)
        s.tick(199); self.assertEqual(len(rel.poses()), 2)
        s.tick(1); self.assertEqual(len(rel.poses()), 3)
        s.tick(50)
        self.assertAlmostEqual(rel.poses()[1].rotation, -282.5)  # -210 plus half of -145.
        s.tick(300)
        self.assertTrue(0 < rel.poses()[1].flash_alpha < 200)
        self.assertTrue(.5 < rel.poses()[1].flash_scale < 2)
        self.assertEqual(motion.revealed, 0)
        s.tick(500)
        for pose in rel.poses():
            self.assertAlmostEqual(pose.rotation % 360, 5)
            self.assertEqual(pose.flash_alpha, 0)
        self.assertEqual(s.vm.snapshot(), held)
        # Native character 45 skips gain actions, but still has static icons.
        special = RelationshipChange(45, 3012, 3, 3012, 1)
        self.assertEqual(special.extra_delay_ms, 0)
        self.assertEqual(len(RelationshipAnimation(special, 0).poses()), 3)

    def test_lost_icons_wait_then_fall_and_sound_depends_on_relationship_kind(self):
        for asset, effect in ((3010, 3014), (3011, 3016), (3012, 3018)):
            change = RelationshipChange(1, asset, 1, asset, 3)
            self.assertEqual((change.extra_delay_ms, change.sound), (600, 8008))
            rel = RelationshipAnimation(change, 550)
            rel.tick(1000)
            poses = rel.poses()
            self.assertEqual([p.asset_id for p in poses], [asset, effect, effect])
            y = poses[1].y
            rel.tick(500)
            self.assertAlmostEqual(rel.poses()[1].y, y + 250)
            rel.tick(500)
            self.assertEqual([p.asset_id for p in rel.poses()], [asset])
        for old, new, sound in ((3012, 3011, 8006), (3011, 3012, 8009),
                                (3012, 3010, 8015), (3010, 3012, 8016)):
            change = RelationshipChange(1, new, 2, old, 4)
            self.assertEqual((change.gain_from, change.sound), (0, sound))
        self.assertEqual(RelationshipChange(1, 3011, 3, 3011, 1).sound, 8006)
        self.assertIsNone(RelationshipChange(1, 3012, 1, 0, 0).sound)

    def test_frame_rate_independence_save_validation_and_legacy_settled_migration(self):
        s = npc_session(value=3, previous_count=1)
        s.tick(813)
        saved = s.snapshot(); restored = Session.from_snapshot(s.resources, saved)
        self.assertEqual(restored.snapshot(), saved)
        s.tick(900)
        for _ in range(90): restored.tick(10)
        self.assertEqual(restored.snapshot(), s.snapshot())
        for path, value in ((('relationship', 'elapsed_ms'), -1),
                             (('relationship', 'delay_ms'), 851),
                             (('relationship', 'change', 'asset_id'), 99),
                             (('relationship', 'change', 'count'), 5),
                             (('relationship', 'change', 'previous_count'), 5),
                             (('relationship', 'change', 'character_id'), 2)):
            invalid = copy.deepcopy(saved); target = invalid['engine']['dialogue_animation']
            for key in path[:-1]: target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(SaveError):
                Session.from_snapshot(restored.resources, invalid)
        legacy = npc_session()
        legacy.tick(800)
        old = legacy.snapshot(); old['version'] = 5
        del old['engine']['loading']
        del old['engine']['dialogue_animation']['relationship']
        del old['pending']['details']['relationship']
        old['engine']['numbers'].pop(legacy.engine.number_key(1, 3000))
        old['engine']['numbers'].pop(legacy.engine.number_key(1, 3001))
        before = copy.deepcopy(old)
        loaded = Session.from_snapshot(legacy.resources, old)
        self.assertEqual(old, before)
        self.assertEqual(loaded.vm.snapshot(), legacy.vm.snapshot())
        self.assertEqual(loaded.engine.sound_serial, legacy.engine.sound_serial)
        self.assertEqual(loaded.engine.dialogue_animation.revealed, legacy.engine.dialogue_animation.revealed)
        self.assertEqual(loaded.engine.dialogue_animation.relationship.change.extra_delay_ms, 0)
        self.assertEqual(len(loaded.engine.dialogue_animation.relationship.poses()), 1)

    @unittest.skipUnless(importlib.util.find_spec('pygame') and Path('.shs-library/library.json').is_file(),
                         'desktop extra and user content required')
    def test_apk_art_gain_loss_pause_and_mid_animation_pixel_restore(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        from exp_runtime.content import ContentLibrary
        from exp_runtime.desktop import Desktop
        self.addCleanup(pygame.quit)
        with ContentLibrary(Path('.shs-library')) as library:
            r = library.open_episode('Football Star')
            source = Session(r); source.advance()
            for _ in range(150):
                a = source.pending
                if a.name == 'dialogue' and a.details['visible_character_id'] > 0:
                    break
                if a.name == 'choice': source.answer(next(i for i, e in enumerate(a.details['enabled']) if e))
                elif a.name == 'text_input': source.answer('Alex')
                else: answer_screen(source)
            else: self.fail('Expected an NPC in Football Star')
            character = source.pending.details['visible_character_id']
            for value, prior_asset, prior_count, romance in ((2, 3012, 1, 0), (0, 3012, 3, 0),
                                                            (2, 3010, 1, 1), (-1, 3011, 3, 0)):
                fixture = npc_session(value=value, previous_asset=prior_asset, previous_count=prior_count)
                r.programs[65000] = fixture.vm.program
                s = Session(r, start_script=65000)
                s.engine = copy.deepcopy(source.engine)
                s.engine.dialogue_animation = None
                s.engine.character_art_variants[1] = s.engine.character_art_variants[character]
                s.engine.character_names[1] = 'Friend'
                s.engine.numbers[s.engine.number_key(0, 601)] = romance
                for key, number in ((407, value), (629, 0), (3000, prior_asset), (3001, prior_count)):
                    s.engine.numbers[s.engine.number_key(1, key)] = number
                ui = Desktop(s, audio=False)
                ui.session.tick(820 if value == 2 else 1300)
                ui.render(); self.assertIsNone(ui.error)
                pixels = pygame.image.tobytes(ui.canvas, 'RGB'); saved = s.snapshot()
                ui.session = Session.from_snapshot(r, saved)
                ui.render(); self.assertIsNone(ui.error)
                self.assertEqual(pygame.image.tobytes(ui.canvas, 'RGB'), pixels)
                self.assertEqual(ui.session.snapshot(), saved)
                ui.command(('menu',)); ui.tick(2000); ui.command(('resume',))
                self.assertEqual(ui.session.snapshot(), saved)
                frames = set()
                for _ in range(12):
                    ui.tick(16); ui.render(); self.assertIsNone(ui.error)
                    frames.add(pygame.image.tobytes(ui.canvas, 'RGB'))
                self.assertEqual(len(frames), 12)
