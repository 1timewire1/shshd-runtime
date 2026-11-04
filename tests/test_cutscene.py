"""Storyboard cutscenes: the clock, the session's part, the creator's nodes and the drawing."""
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

from exp_runtime.creator import Asset, Node
from exp_runtime.creator.model import VERSION as PROJECT_VERSION
from exp_runtime.cutscene import CUTSCENE, Cutscene, moved, read_spec
from exp_runtime.runtime import SaveError, Session
from test_creator import session_for as authored_session
from test_creator_features import sequence
from test_runtime import host_call
from test_vm import program

SPEC_ID = 30000
RED, BLUE, STAMP, WHIP = 30001, 30002, 30003, 30004


def spec(**more):
    return {**dict(format='shshd-cutscene', version=1, size=[20, 40], hold=3000, skip=2000,
                   shots=[dict(image=RED, start=0, end=1000, **{'from': [0, 0, 20, 40], 'to': [20, 0, 20, 40]}),
                          dict(image=BLUE, start=2000, end=2000, **{'from': [0, 0, 20, 40], 'to': [0, 0, 20, 40]})],
                   overlays=[dict(image=STAMP, start=2000, end=2500, **{'from': [10, 20, 80, 80], 'to': [10, 20, 4, 4]})],
                   sounds=[dict(at=500, sound=WHIP), dict(at=2000, sound=WHIP + 1)]), **more}


def encoded(**more):
    return json.dumps(spec(**more)).encode('utf-8')


class ClockTests(unittest.TestCase):
    def test_it_runs_to_the_hold_and_stays(self):
        game = Cutscene.opened(SPEC_ID, encoded())
        game.tick(2999)
        self.assertFalse(game.held)
        game.tick(5000)
        self.assertTrue(game.held)
        self.assertEqual(game.elapsed_ms, 3000)
        self.assertFalse(game.finished)

    def test_a_press_jumps_to_the_skip_then_the_hold_then_ends(self):
        game = Cutscene.opened(SPEC_ID, encoded())
        game.tick(100)
        game.press()
        self.assertEqual(game.elapsed_ms, 2000)
        self.assertEqual(game.sounds, [WHIP + 1])       # the card's sound, not the one it jumped over
        game.press()
        self.assertTrue(game.held)
        self.assertFalse(game.finished)
        game.press()
        self.assertTrue(game.finished)

    def test_each_sound_plays_once_at_its_moment(self):
        game = Cutscene.opened(SPEC_ID, encoded())
        game.tick(499)
        self.assertEqual(game.sounds, [])
        game.tick(1)
        self.assertEqual(game.sounds, [WHIP])
        game.tick(5000)
        self.assertEqual(game.sounds, [WHIP, WHIP + 1])

    def test_the_music_keeps_the_clock_until_a_jump_and_never_replays_a_sound(self):
        game = Cutscene.opened(SPEC_ID, encoded(music=26900))
        self.assertEqual(game.music, 26900)
        game.sync(600)
        self.assertEqual((game.elapsed_ms, game.sounds), (600, [WHIP]))
        game.sync(400)                                  # it runs behind: the clock follows
        self.assertEqual(game.elapsed_ms, 400)
        game.sync(700)
        self.assertEqual(game.sounds, [WHIP])
        game.press()
        self.assertEqual(game.music, -1)                # the music plays on from where it was

    def test_a_window_moves_and_can_ease_out(self):
        shot = dict(start=1000, end=2000, **{'from': [0, 0, 10, 10], 'to': [100, 0, 10, 10]})
        self.assertEqual(moved(shot, 500)[0], 0)
        self.assertEqual(moved(shot, 1500)[0], 50)
        self.assertEqual(moved(shot, 9000)[0], 100)
        self.assertEqual(moved(dict(shot, ease='out'), 1500)[0], 75)

    def test_a_bad_spec_is_refused(self):
        read_spec(encoded())
        for bad in (b'not json', b'{}', encoded(hold=1000), json.dumps(dict(spec(), shots=[])).encode(),
                    json.dumps(dict(spec(), size=[0, 40])).encode(),
                    json.dumps(dict(spec(), sounds=[dict(at=5, sound=1), dict(at=1, sound=1)])).encode()):
            with self.subTest(bad=bad[:30]), self.assertRaises(ValueError):
                read_spec(bad)


def story():
    """Plays where the player draws cutscenes, fading out of its last press; otherwise goes straight on."""
    project = sequence(Node('q', 'cutscene_available', params={'result': 'shown'}),
                       Node('b', 'branch', params={'expression': '(shown == 1)'}, next='f', otherwise='after'),
                       Node('f', 'transition', params={'selector': 20}), Node('c', 'cutscene', params={'spec': SPEC_ID}, next='after'),
                       Node('after', text='After'))
    project.assets.append(Asset(SPEC_ID, 'spec', encoded()))
    project.assets += [Asset(resource, 'art', b'\x89PNG\r\n\x1a\n') for resource in (RED, BLUE, STAMP, WHIP, WHIP + 1)]
    return project


def session_for(project):
    session = authored_session(project)
    session.resources.read_asset = {SPEC_ID: encoded()}.__getitem__
    return session


class SessionTests(unittest.TestCase):
    def test_a_player_that_doesnt_draw_them_goes_straight_on(self):
        session = session_for(story())
        action = session.advance()
        self.assertEqual((action.name, action.details['text']), ('dialogue', 'After'))
        self.assertIsNone(session.engine.cutscene)

    def played(self):
        session = session_for(story())
        session.cutscenes = True
        return session, session.advance()

    def test_it_waits_for_its_presses_and_runs_a_queued_transition_under_itself(self):
        session, action = self.played()
        self.assertEqual(action.name, 'cutscene')
        session.tick(100)
        session.answer()
        session.answer()
        self.assertEqual(session.pending.name, 'cutscene')
        self.assertFalse(session.transitioning)
        session.answer()
        self.assertEqual(session.pending.name, 'cutscene')      # the card stays up as the blinds close
        self.assertTrue(session.transitioning)
        for _ in range(400):
            action = session.tick(50)
            if not session.transitioning:
                break
        self.assertEqual((action.name, action.details['text']), ('dialogue', 'After'))
        self.assertIsNone(session.engine.cutscene)

    def test_its_held_picture_is_the_episodes_title_card_for_the_picker(self):
        from exp_runtime import episode_thumbnails
        session = session_for(story())
        self.assertTrue(episode_thumbnails.run_to_title_card(session))
        self.assertEqual(session.pending.name, 'cutscene')
        self.assertTrue(session.engine.cutscene.held)
        self.assertFalse(session.transitioning)

    def test_it_takes_only_a_press(self):
        session, _ = self.played()
        with self.assertRaises(ValueError):
            session.answer(1)

    def test_its_sounds_go_through_the_engine(self):
        session, _ = self.played()
        session.tick(600)
        self.assertEqual(session.engine.sound_ids, [WHIP])
        self.assertEqual(session.engine.cutscene.sounds, [])

    def test_it_saves_where_it_is(self):
        session, _ = self.played()
        session.tick(700)
        state = session.snapshot()
        self.assertEqual(state['version'], 36)
        restored = Session.from_snapshot(session.resources, state)
        self.assertEqual(restored.pending.name, 'cutscene')
        self.assertEqual(restored.engine.cutscene.elapsed_ms, 700)
        self.assertIsInstance(restored.engine.cutscene, Cutscene)
        restored.answer()
        self.assertEqual(restored.engine.cutscene.elapsed_ms, 2000)

    def test_a_damaged_save_is_refused_and_an_older_one_never_had_one(self):
        session, _ = self.played()
        state = session.snapshot()
        state['engine']['cutscene']['elapsed_ms'] = 99999
        with self.assertRaises(SaveError):
            Session.from_snapshot(session.resources, state)
        plain = session_for(story())
        plain.advance()
        state = plain.snapshot()
        state['version'] = 34
        del state['engine']['cutscene']
        self.assertIsNone(Session.from_snapshot(plain.resources, state).engine.cutscene)


class CreatorTests(unittest.TestCase):
    def test_its_nodes_dont_change_the_project_format(self):
        self.assertEqual(PROJECT_VERSION, 3)

    def test_the_spec_must_be_a_resource_id(self):
        from exp_runtime.creator import ProjectError, compile_project
        with self.assertRaises(ProjectError):
            compile_project(sequence(Node('c', 'cutscene', params={'spec': -1})))

    def test_the_nodes_survive_a_save(self):
        from exp_runtime.creator.model import project_from_record, project_record
        again = project_from_record(project_record(story()))
        self.assertEqual({n.kind for n in again.nodes} >= {'cutscene_available', 'cutscene'}, True)
        self.assertEqual(next(n for n in again.nodes if n.kind == 'cutscene').params['spec'], SPEC_ID)


class PlayerTests(unittest.TestCase):
    def setUp(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        pygame.init()
        pygame.display.set_mode((64, 64))
        self.pygame = pygame

    def png(self, colour, size=(40, 40)):
        surface = self.pygame.Surface(size, self.pygame.SRCALPHA)
        surface.fill(colour)
        buffer = io.BytesIO()
        self.pygame.image.save(surface, buffer, 'x.png')
        return buffer.getvalue()

    def desktop(self, temporary, **more):
        from exp_runtime.desktop import Desktop
        from test_desktop import Resources
        assets = {SPEC_ID: encoded(**more), RED: self.png((200, 0, 0, 255)), BLUE: self.png((0, 0, 200, 255)),
                  STAMP: self.png((0, 200, 0, 255))}
        resources = Resources(program(*host_call(CUTSCENE, SPEC_ID), 0x33))
        resources.read_asset = assets.__getitem__
        resources.library.directory = Path(temporary)
        session = Session(resources, ephemeral=True)
        ui = Desktop(session, audio=False)
        session.advance()
        return ui, session

    def test_the_player_says_it_draws_them(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, session = self.desktop(temporary)
            self.assertTrue(session.cutscenes)
            self.assertEqual(session.pending.name, 'cutscene')

    def test_it_draws_the_shot_then_the_overlay_where_it_lands(self):
        with tempfile.TemporaryDirectory() as temporary:
            ui, session = self.desktop(temporary)
            ui.cutscene_renderer.draw(session)
            canvas = ui.cutscene_renderer.canvas
            self.assertEqual(canvas.get_size(), (20, 40))
            self.assertEqual(canvas.get_at((5, 5))[:3], (200, 0, 0))
            session.tick(2000)
            ui.cutscene_renderer.draw(session)
            self.assertEqual(canvas.get_at((10, 20))[:3], (0, 200, 0))      # the stamp, cut to what shows, covers the frame
            self.assertEqual(canvas.get_at((1, 1))[:3], (0, 200, 0))
            session.tick(1000)
            ui.cutscene_renderer.draw(session)
            self.assertGreater(canvas.get_at((10, 20))[1], 150)             # landed: 4 x 4 at the centre
            self.assertEqual(canvas.get_at((1, 1))[:3], (0, 0, 200))

    def test_a_click_presses_and_the_screen_has_no_buttons_of_its_own(self):
        with tempfile.TemporaryDirectory() as temporary:
            ui, session = self.desktop(temporary)
            ui.render()
            self.assertEqual([command for _, command in ui.buttons], [('continue',)])
            ui.command(('continue',))
            self.assertEqual(session.engine.cutscene.elapsed_ms, 2000)

    def test_autoplay_waits_for_the_hold_then_a_title_cards_time(self):
        with tempfile.TemporaryDirectory() as temporary:
            ui, session = self.desktop(temporary)
            ui.autoplay = True
            game = session.engine.cutscene
            session.tick(1000)
            ui._tick_autoplay(ui.AUTOPLAY_TITLE_WAIT_MS)
            self.assertEqual(game.elapsed_ms, 1000)         # it doesn't skip
            session.tick(5000)
            ui._tick_autoplay(ui.AUTOPLAY_TITLE_WAIT_MS - 1)
            self.assertFalse(game.finished)
            ui._tick_autoplay(1)
            self.assertTrue(game.finished)

    def test_the_named_track_keeps_the_clock(self):
        with tempfile.TemporaryDirectory() as temporary:
            ui, session = self.desktop(temporary, music=26900)
            stream = ui.music_stream
            stream.current = dict(id=26900, flag=True, start=1.25, played=0, length=30, loop=None)
            stream.paused = False
            ui._sync_cutscene()
            self.assertEqual(session.engine.cutscene.elapsed_ms, 1250)
            stream.current['id'] = 5
            session.engine.cutscene.tick(10)
            ui._sync_cutscene()
            self.assertEqual(session.engine.cutscene.elapsed_ms, 1260)      # another track, or Music off: its own clock
            stream.current = None


if __name__ == '__main__':
    unittest.main()
