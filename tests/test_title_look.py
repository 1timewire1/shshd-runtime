"""Add-Ons' Title Screen Look (owner, 2026-11-16): a translated game's title art in the HD main menu, from its addon."""
from io import BytesIO
import json
from types import SimpleNamespace
import unittest

import pygame

from exp_runtime.hd_ui import FRAME, HdUi
from exp_runtime.hd_scale import S
from exp_runtime.title_look import TitleLook


def png(size, colour):
    surface = pygame.Surface(size, pygame.SRCALPHA)
    surface.fill(colour)
    out = BytesIO()
    pygame.image.save(surface, out, 'look.png')
    return out.getvalue()


class Library:
    """An addon `shsnr` holding `resources`."""
    def __init__(self, resources):
        self.resources = resources

    def addon_resource(self, addon, resource):
        return self.resources.get(resource) if addon == 'shsnr' else None


def look(spec, pictures):
    return TitleLook.load(Library({26960: json.dumps(dict(version=1, **spec)).encode(), **pictures}), 'shsnr', 26960)


def layout(the_look, height):
    """HdUi.main_layout with `the_look` chosen."""
    ui = HdUi.__new__(HdUi)
    HdUi.look_source = lambda: the_look
    try:
        return ui.main_layout(height)
    finally:
        HdUi.look_source = None


class TitleLookTests(unittest.TestCase):
    def setUp(self):
        pygame.init()
        pygame.display.set_mode((1, 1))

    def test_a_missing_spec_or_one_of_another_version_is_no_look(self):
        self.assertIsNone(TitleLook.load(Library({}), 'shsnr', 26960))
        self.assertIsNone(TitleLook.load(Library({26960: b'not json'}), 'shsnr', 26960))
        self.assertIsNone(TitleLook.load(Library({26960: json.dumps({'version': 2, 'background': {}}).encode()}), 'shsnr', 26960))

    def test_layers_go_where_hds_own_do_in_every_frame(self):
        the_look = look({'background': {'cover': {'id': 26961, 'scale': 2, 'smooth': False}},
                         'photo': {'picture': {'id': 26962}, 'centre': [384, 560]},
                         'title': {'picture': {'id': 26963, 'scale': 3, 'smooth': False}, 'centre': [384, 192]}},
                        {26961: png((384, 1024), (0, 0, 255, 255)), 26962: png((400, 300), (255, 255, 255, 255)),
                         26963: png((200, 100), (255, 0, 0, 255))})
        for height in (1024, 1365, 1664):
            with self.subTest(height=height):
                background, photo, ribbon, title = layout(the_look, height)
                self.assertEqual(background[0].get_size(), (FRAME[0] * S, round(height * S)))     # the frame exactly
                self.assertIsNone(ribbon)
                self.assertEqual(title[1], (384, 192))                                           # the title stays put
                self.assertEqual(title[0].get_size(), (600 * S, 300 * S))
                raised = HdUi.buttons_raise(height)
                between = (height - raised) / 2 if height > FRAME[1] else FRAME[1] / 2
                self.assertEqual(photo[1], (384, 560 + between - FRAME[1] / 2))                 # moved as HD's photo is
        self.assertEqual(layout(the_look, 1024)[1][0].get_size(), (400 * S, 300 * S))
        self.assertGreater(layout(the_look, 1664)[1][0].get_width(), 400 * S)                   # ...and grown

    def test_a_sliced_background_is_built_at_the_frames_height_and_the_scene_follows_the_buttons(self):
        the_look = look({'background': {'top': {'id': 26961}, 'middle': {'id': 26962}, 'bottom': {'id': 26963}},
                         'scene': {'picture': {'id': 26964}, 'left': 0, 'bottom': 1000}},
                        {26961: png((768, 100), (255, 0, 0, 255)), 26962: png((768, 50), (0, 255, 0, 255)),
                         26963: png((768, 100), (0, 0, 255, 255)), 26964: png((768, 10), (255, 255, 255, 255))})
        for height in (1024, 1500):
            with self.subTest(height=height):
                background, photo, _, title = layout(the_look, height)
                surface = background[0]
                self.assertIsNone(photo)                    # nothing to drop in
                self.assertIsNone(title)
                self.assertEqual(surface.get_at((10, 10 * S))[:3], (255, 0, 0))
                self.assertEqual(surface.get_at((10, round((height - 10) * S)))[:3], (0, 0, 255))
                self.assertEqual(surface.get_at((10, round(height / 2 * S)))[:3], (0, 255, 0))
                extra = max(0, height - FRAME[1]) - HdUi.buttons_raise(height)
                self.assertEqual(surface.get_at((10, round((995 + extra) * S)))[:3], (255, 255, 255))


class TitleLookChoiceTests(unittest.TestCase):
    """Which look shows: Default, Auto (the game last played, BREW's editions apart), or a game whose addon carries one."""

    def app(self, choice, last='default', addons=('shsbrew', 'shsnr')):
        from exp_runtime.application import Application
        specs = {26960: json.dumps({'version': 1, 'background': {'cover': {'id': 26961}}}).encode()}
        held = {name: specs for name in addons}
        has = lambda name, resource: resource in held.get(name, {})           # noqa: E731
        library = SimpleNamespace(game_id='shs', addons=[{'addon': name, 'id': name + '-file'} for name in addons],
                                  addon_has=has, addon_resource=lambda name, resource: held.get(name, {}).get(resource))
        app = SimpleNamespace(library=library, _title_look=(None, None),
                              state=SimpleNamespace(title_look=choice, last_title_look=last, last_title_game='default',
                                                    persist=lambda: None),
                              _attempt=lambda action: action())
        for name in ('title_look', 'title_look_offered', 'remember_title_game'):
            setattr(app, name, getattr(Application, name).__get__(app))
        return app

    def test_the_chosen_look_or_none(self):
        self.assertEqual(self.app('nr').title_look().addon, 'shsnr')
        self.assertEqual(self.app('brew07').title_look().spec_id, 26960)
        self.assertIsNone(self.app('brew08').title_look())                  # this addon carries '07's look only
        self.assertIsNone(self.app('x360').title_look())                    # no addon
        self.assertIsNone(self.app('default').title_look())
        self.assertEqual(self.app('auto', last='nr').title_look().addon, 'shsnr')
        self.assertEqual(self.app('default').title_look_offered(), ['default', 'auto', 'nr', 'brew07'])

    def test_auto_tells_brews_editions_apart(self):
        from test_addon_features import episode
        app = self.app('auto')
        for pack, look, tune in ((31000, 'brew08', 'brew'), (31100, 'brew07', 'brew'), (31200, 'brew07', 'brew'),
                                 (31300, 'nr', 'nr'), (5, 'default', 'default')):
            with self.subTest(pack=pack):
                app.remember_title_game(episode(pack))
                self.assertEqual((app.state.last_title_look, app.state.last_title_game), (look, tune))


if __name__ == '__main__':
    unittest.main()
