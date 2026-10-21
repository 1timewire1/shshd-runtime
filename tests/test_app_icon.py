from io import BytesIO
import os
import plistlib
import unittest
from unittest.mock import patch
from zipfile import ZipFile

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

from PIL import Image

from exp_runtime.content import ContentLibrary


def _png(size, color):
    stream = BytesIO()
    Image.new('RGBA', (size, size), color).save(stream, format='PNG')
    return stream.getvalue()


def _library(kind, members):
    stream = BytesIO()
    with ZipFile(stream, 'w') as package:
        for name, data in members.items():
            package.writestr(name, data)
    library = ContentLibrary.__new__(ContentLibrary)
    library.kind, library.package = kind, ZipFile(stream)
    library.app_root = 'Payload/Game.app/' if kind == 'ipa' else 'assets/Assets/'
    return library


class AppIconTests(unittest.TestCase):
    def test_apk_uses_its_largest_launcher_icon(self):
        library = _library('apk', {'res/drawable-ldpi/icon.png': _png(36, 'red'),
                                   'res/drawable-hdpi/icon.png': _png(72, 'blue'),
                                   'bitmaps/close_icon.png': _png(96, 'green')})
        self.assertEqual(library.app_icon().size, (72, 72))

    def test_ipa_uses_the_largest_icon_its_info_plist_names(self):
        info = plistlib.dumps({'CFBundleIconFile': 'Icon.png', 'CFBundleIconFiles': ['Icon', 'Icon-Small.png']})
        library = _library('ipa', {'Payload/Game.app/Info.plist': info,
                                   'Payload/Game.app/Icon.png': _png(57, 'red'),
                                   'Payload/Game.app/Icon@2x.png': _png(114, 'blue'),
                                   'Payload/Game.app/Icon-Small.png': _png(29, 'red'),
                                   'Payload/Game.app/other_game_icon.png': _png(256, 'green')})
        icon = library.app_icon()
        self.assertEqual(icon.size, (114, 114))
        self.assertEqual(icon.getpixel((0, 0))[:3], (0, 0, 255))

    def test_package_without_an_icon_has_none(self):
        self.assertIsNone(_library('apk', {'assets/Assets/1': b''}).app_icon())
        self.assertIsNone(_library('ipa', {'Payload/Game.app/Info.plist': plistlib.dumps({})}).app_icon())

    def test_window_falls_back_to_the_authored_logo(self):
        import pygame
        from exp_runtime import app_icon
        pygame.display.init()
        self.addCleanup(pygame.display.quit)
        library = _library('apk', {'res/drawable-mdpi/icon.png': _png(48, 'blue')})
        with patch.object(pygame.display, 'set_icon') as set_icon:
            app_icon.set_window_icon(library)
            self.assertEqual(set_icon.call_args.args[0].get_size(), (48, 48))
            app_icon.set_window_icon(_library('apk', {}))
            self.assertIs(set_icon.call_args.args[0], app_icon.icon_surface())
            app_icon.set_window_icon(object())
            self.assertIs(set_icon.call_args.args[0], app_icon.icon_surface())


if __name__ == '__main__':
    unittest.main()
