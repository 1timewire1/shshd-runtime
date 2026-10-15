"""Device verification using authored EXP bytes and the unmodified game engine.

This is a diagnostic host, not a replacement renderer or standalone-EXP player.
It never imports Python code or native binaries from a selected game archive.
"""
from io import BytesIO
import json
import lzma
from pathlib import Path
import platform
import struct
import sys
import tempfile
from types import SimpleNamespace
from zipfile import ZIP_DEFLATED, ZipFile

from exp_runtime.content import ExpArchive, _episode_inputs, digest
from exp_runtime.decode.bytecode import OPERAND_OPCODES, decode_program
from exp_runtime.runtime import Session
from exp_runtime.trace import trace_archive
try:
    from rar_fixture import rar4, rar5  # Staged beside this module on iOS.
except ModuleNotFoundError:
    from ios.probe.rar_fixture import rar4, rar5  # Desktop source tests.


class ProbeResources:
    """Authored, asset-free test context; never used as a game asset fallback."""
    def __init__(self, data, directory, game):
        archive = ExpArchive(data)
        self.programs = archive.programs()
        self.library = SimpleNamespace(directory=Path(directory), game_id=game)
        self.record = dict(titles=list(archive.metadata().titles))
        self.identity = dict(profile=f'authored-ios-probe-{game}', episode_sha256=digest(data))

    def program(self, resource):
        return self.programs[resource]

    def exists(self, resource):
        return resource in self.programs


def _authored_exp(service=1):
    # Assemble a small original fixture, using the production lossless decoder.
    strings = ('Choose', 'Left|Right', 'Authored iOS check', 'Continued.')
    text, refs = bytearray(), []
    for string in strings:
        refs.append(len(text) // 2)
        text.extend(string.encode('latin-1') + b'\0')
        if len(text) % 2:
            text.append(0)
    instructions = [(0x1a, n) for n in (refs[0], refs[1], refs[2], 1000, 1, -1, -1, 0)]
    # 255 is an unsupported service in every game (this fork's SHS uses 101 for the Decision Tree).
    instructions += [(0x1f, service << 8 | 8), (0x21, None), (0x1f, 255 << 8 | 1)]
    code = bytearray()
    for op, arg in instructions:
        code.append(op)
        if op in OPERAND_OPCODES:
            code.extend(struct.pack('>H', arg & 0xffff))
    script = b'kiwi\x02\x00\x00' + struct.pack('>4H', len(text) // 2, 0, 0, len(instructions)) + text + code
    assert decode_program(script).to_bytes() == script
    title = b'Authored iOS verification'
    metadata = struct.pack('>HH', 0, 1) + (struct.pack('>H', len(title)) + title) * 5
    entries, records = [], bytearray()
    for resource, payload in ((1, metadata), (25001, script)):
        entries.append(struct.pack('>HI', resource, 21 + len(records)))
        alone = lzma.compress(payload, format=lzma.FORMAT_ALONE,
                              filters=[dict(id=lzma.FILTER_LZMA1, dict_size=4096)])
        compressed = alone[:5] + struct.pack('<II', len(payload), len(payload)) + alone[13:]
        records.extend(struct.pack('>III', len(compressed), len(payload), 1) + compressed)
    return b'CSPUD' + struct.pack('>I', 2) + b''.join(entries) + records


def verify(directory):
    from PIL import Image, ImageFont, __version__ as pillow_version
    checks = []
    image = Image.new('RGBA', (4, 4), (23, 45, 67, 255))
    stream = BytesIO()
    image.save(stream, format='PNG')
    assert Image.open(BytesIO(stream.getvalue())).convert('RGBA').tobytes() == image.tobytes()
    assert ImageFont.load_default().getlength('EXP') > 0
    checks.append('Pillow PNG decoding and FreeType font metrics')
    data = _authored_exp()
    with tempfile.TemporaryDirectory(prefix='exp-probe-', dir=directory) as temporary:
        source = Path(temporary) / 'Authored.exp'
        source.write_bytes(data)
        zipped = Path(temporary) / 'Episodes.zip'
        with ZipFile(zipped, 'w', compression=ZIP_DEFLATED) as package:
            package.writestr('Episodes/nested/Authored.exp', data)
            package.writestr('__MACOSX/Episodes/._Authored.exp', b'Ignored metadata')
        for game in ('shs', 'cod'):
            with _episode_inputs([zipped], game=game) as (episodes, catalog):
                assert len(episodes) == 1 and episodes[0].name == source.name
                imported = episodes[0].read_bytes()
                assert imported == data and not catalog.entries
            resources = ProbeResources(imported, temporary, game)
            checks.append(f'{game}: ZIP import with subfolders, metadata filtering and compressed EXP data')
            for encode in (rar4, rar5):
                rar = Path(temporary) / 'Episodes.rar'
                rar.write_bytes(encode([('Episodes/nested/Authored.exp', data),
                                        ('__MACOSX/._Authored.exp', b'Ignored metadata')]))
                with _episode_inputs([rar], game=game) as (episodes, catalog):
                    assert len(episodes) == 1 and episodes[0].read_bytes() == data and not catalog.entries
                checks.append(f'{game}: {encode.__name__.upper()} import through the native decoder')
            session = Session(resources)
            assert session.advance().name == 'choice'
            session.tick(250)
            assert session.remaining_ms == 750
            before = json.loads(json.dumps(session.snapshot()))
            save = session.save(Path(temporary) / f'{game}.json')
            restored = Session.load(resources, save)
            assert json.loads(json.dumps(restored.snapshot())) == before
            assert restored.answer(0).name == 'unhandled_yield'
            assert restored.pending.request.args == (0,)
            expired = Session.load(resources, save)
            assert expired.tick(750).name == 'choice'
            assert expired.tick(1).name == 'unhandled_yield'
            assert expired.pending.request.args == (1,)
            stopped = Session.from_snapshot(resources, expired.snapshot())
            assert stopped.vm.snapshot() == expired.vm.snapshot()
            assert stopped.pending.request.args == (1,)
            checks.append(f'{game}: compressed EXP, VM choice/timer, atomic save/load, retained unknown call')
            moving = Session(resources)
            moving.advance()
            moving.engine.background_pan.configure(False, 1)
            moving.tick(100)
            assert moving.engine.background_pan.origin(640, 360) == (-96, 0)
            resumed = Session.from_snapshot(resources, json.loads(json.dumps(moving.snapshot())))
            assert resumed.snapshot() == moving.snapshot()
            resumed.tick(150)
            assert resumed.engine.background_pan.origin(640, 360) == (0, 0)
            assert resumed.remaining_ms == 750
            assert resumed.vm.snapshot() == moving.vm.snapshot()
            checks.append(f'{game}: background pan, saved alignment and active clock')
        # Also exercise the same public archive inspector used by the CLI.
        assert trace_archive(source)['status'] == 'choice'
        checks.append('Public EXP trace through the production engine')
    return dict(status='passed', python=platform.python_version(), pillow=pillow_version,
                platform=sys.platform, machine=platform.machine(), checks=checks)


def request(payload, directory):
    message = json.loads(payload)
    if message['operation'] == 'verify':
        try:
            result = verify(directory)
        except Exception as error:
            result = dict(status='failed', error=f'{type(error).__name__}: {error}', platform=sys.platform)
        report = json.dumps(result, indent=2)
        Path(directory, 'ios-verification.json').write_text(report + '\n', encoding='utf-8')
        print('EXP_IOS_VERIFICATION ' + json.dumps(result), flush=True)
        return report
    if message['operation'] == 'inspect':
        result = trace_archive(Path(message['path']))
        # Do not persist traces or the player's script text in diagnostic files.
        return json.dumps(dict(status=result['status'], error=result['error'], scene=result['scene'],
                               pc=result['pc'], events=len(result['events'])), indent=2)
    raise ValueError('Unknown prototype operation')


def drawing_fixture():
    """Asymmetric authored pixels catch flipped images, crop and alpha errors."""
    from PIL import Image
    from exp_runtime.platforms.drawing import Draw, FrameEncoder, Surface, Transform, raster, SRCALPHA
    target = Surface((320, 276))
    target.fill((10, 20, 30))
    tile = Surface.from_pixels(Image.new('RGBA', (4, 6), (240, 10, 20, 255)))
    tile.fill((10, 230, 20), (0, 0, 4, 2))
    target.blit(tile, (2, 3))
    target.blit(Transform.flip(tile, False, True), (8, 3))
    target.blit(Transform.rotate(tile, 90), (14, 3))
    target.blit(Transform.scale(tile, (8, 12)), (2, 12))
    target.set_clip((16, 16, 8, 8))
    Draw.rect(target, (30, 40, 220), (12, 12, 16, 16))
    target.set_clip(None)
    translucent = Surface((4, 4), SRCALPHA)
    translucent.fill((200, 100, 50, 128))
    target.blit(translucent, (26, 26))
    from exp_runtime import graphics
    graphics.project_quad(target, tile, ((24, 10), (28, 10), (32, 16), (24, 16)))
    from exp_runtime.projection import draw_quad
    solid = tile.copy()
    solid.fill((20, 10, 220), (2, 4, 2, 2))
    solid.set_alpha(128)
    target.set_clip((36, 4, 25, 25))
    draw_quad(target, solid, ((34, 5), (59, 1), (62, 28), (36, 24)))
    target.set_clip(None)
    points = [(0, 0), (2, 3), (2, 8), (8, 3), (8, 8), (14, 3), (18, 3),
              (2, 12), (3, 23), (15, 15), (16, 16), (23, 23), (24, 24), (27, 27),
              (24, 10), (27, 11), (25, 15), (23, 15), (31, 15),
              (35, 6), (40, 6), (41, 20), (57, 24), (61, 24)]
    # Render the real shared background helper at the start, midpoint and end
    # of opposite pans. Swift checks these cropped pixels with CoreGraphics.
    from exp_runtime.desktop_dialogue import DialogueRenderer
    from exp_runtime.engine import EngineState
    art = DialogueRenderer.__new__(DialogueRenderer)
    background = Surface((640, 360))
    for column in range(8):
        background.fill((column * 30, 255 - column * 30, column * 10), (column * 80, 0, 80, 360))
    art.image = lambda _: background
    engine = EngineState()
    engine.background_pan.align(1)
    for row, ms in enumerate((0, 125, 125, 125, 125)):
        if row == 3:
            engine.background_pan.align(3)
        engine.background_pan.tick(ms)
        scene = Surface((320, 480))
        art.draw_background(scene, engine)
        y = 38 + row * 14
        target.blit(scene, (0, y), (0, 150, 320, 12))
        points.extend((x, y + 5) for x in (0, 79, 80, 159, 160, 239, 240, 319))
    # The production nine-piece box at native entrance keyframes. Borders
    # stay fixed-size while the center and straight edges expand.
    from exp_runtime.dialogue_animation import DialogueAnimation, DialoguePortrait
    from exp_runtime.ui_assets import Rect
    center, edge = Surface((2, 2)), Surface((4, 4))
    center.fill((230, 220, 180)); edge.fill((80, 110, 200))
    art.frame = lambda asset, index: center if asset == 126 else edge
    motion = DialogueAnimation(20, portrait=DialoguePortrait(1, 100, 1, 1), box_grow=True)
    for column, elapsed in enumerate((550, 610, 670, 770, 870)):
        motion.tick(elapsed - motion.elapsed_ms)
        scene = Surface((64, 100))
        scene.fill((10, 20, 30))
        box = motion.box_rect(Rect(10, 20, 44, 70), Rect(20, 0, 20, 20))
        art.box(scene, box, 1)
        target.blit(scene, (column * 64, 112))
        points.extend((column * 64 + x, 112 + y) for x in (7, 11, 29, 40, 55)
                      for y in (4, 15, 21, 39, 65, 89, 93))
    # Native housing cutout and expression layers: clipping may erase only
    # frame 37, and transparent fades must preserve the ring and old art.
    housing, ring = Surface((60, 60), SRCALPHA), Surface((30, 30), SRCALPHA)
    housing.fill((200, 0, 0)); ring.fill((0, 200, 0))
    old, new = Surface((10, 30), SRCALPHA), Surface((10, 30), SRCALPHA)
    old.fill((0, 0, 200)); new.fill((200, 200, 0))
    new.fill((0, 0, 0, 0), (0, 0, 5, 30))
    art.frame = lambda _, index: housing if index == 37 else ring
    art.portrait = lambda asset, _: old if asset == 100 else new
    portrait, initial = DialoguePortrait(0, 101, 1, 1), DialoguePortrait(0, 100, 1, 1)
    motion = DialogueAnimation(20, portrait=portrait, initial_portrait=initial)
    for column, elapsed in enumerate((1000, 1500, 1600, 2000, 2400)):
        motion.tick(elapsed - motion.presentation_ms)
        layer, _ = art.portrait_group(portrait, (-30, 0, 60, 35), initial, *motion.expression_alphas)
        target.blit(layer, (column * 64, 214))
        points.extend((column * 64 + x, 214 + y) for x, y in ((1, 31), (1, 42), (20, 42), (27, 42), (30, 42)))
    expected = raster(target.snapshot())
    return dict(frame=FrameEncoder().encode(target), samples=[dict(at=p, rgba=expected.getpixel(p)) for p in points])


def _authored_football():
    """Service 94 fixture, using only supplied artwork when available."""
    text = b'Attack\0\0Defend\0\0'
    words = list(struct.unpack('>8H', text))
    labels = len(words); words += [0, 4] * 3
    plan = len(words); words += [3, 0, 0, 100, 0x7ffe]
    args = [100, 100, *([plan] * 6), labels, 1, 1, 2, 60, 40, 14, 7, 0, 0, 0, 1, -1, -1]
    code = b''.join(b'\x1a' + struct.pack('>H', arg & 0xffff) for arg in args)
    code += b'\x1f' + struct.pack('>H', 94 << 8 | len(args)) + b'\x33'
    return decode_program(b'kiwi\x02\0\0' + struct.pack('>4H', len(words), 0, 0, len(args) + 2)
                          + struct.pack(f'>{len(words)}H', *words) + code)


def _authored_word_game(grid=False):
    strings = (('Find a word', 'CAT', 'cat', 'catx', 'cat\ncat', 'Learn',
                'Trace the letters', 'Correct', 'Try again') if grid else
               ('Ignored title', 'Pick the right word', 'yes|right', 'no|wrong|bad'))
    text, refs = bytearray(), []
    for string in strings:
        refs.append(len(text) // 2)
        text.extend(string.encode('ascii') + b'\0')
        if len(text) % 2: text.append(0)
    words = list(struct.unpack(f'>{len(text) // 2}H', text))
    if grid:
        table = len(words); words += [5, 5, *refs[:4], 1, 0, 1, -1]
        args = [20, 200, 5000, 500, 0, -1, -1, 0, -1, 0, 0, 1, table, 1, refs[7], refs[8], 0, 0, 0, 0]
    else:
        args = [*refs, 20000, -1, 1, 3000]
    code = b''.join(b'\x1a' + struct.pack('>H', arg & 0xffff) for arg in args)
    code += b'\x1f' + struct.pack('>H', (96 if grid else 71) << 8 | len(args)) + b'\x33'
    return decode_program(b'kiwi\x02\0\0' + struct.pack('>4H', len(words), 0, 0, len(args) + 2)
                          + struct.pack(f'>{len(words)}H', *(w & 0xffff for w in words)) + code)


def audio_fixture():
    """Silent authored PCM; exercises real native playback without original audio."""
    import base64
    import wave
    stream = BytesIO()
    with wave.open(stream, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b'\0\0' * 32000)
    return base64.b64encode(stream.getvalue()).decode('ascii')


def presentation_steps(host):
    """Exercise real app paths; optional originals stay in the simulator data container."""
    from exp_runtime.ios_fonts import render_font
    from exp_runtime.launcher import default_library
    from exp_runtime.app_info import PROJECT_URL, runtime_version
    from exp_runtime.platforms.drawing import raster
    from types import SimpleNamespace
    app = host.app
    assert 'pygame' not in sys.modules, 'Mobile host accidentally imported pygame'
    assert app.screen == 'games'
    assert runtime_version() != 'development', 'Embedded runtime version is missing'
    host.handle_events([dict(kind='down', point=(200, 300), generation=-1),
                        dict(kind='up', point=(200, 300), generation=-1)])
    assert app.screen == 'games', 'A stale gesture answered a different screen'
    yield 'Shared game chooser and native default font'
    from concurrent.futures import Future
    from exp_runtime.settings import AppSettings
    from exp_runtime.updates import UpdateCheck
    def offer_update():
        future = Future()
        future.set_result(json.dumps(dict(tag_name='v999.0.0', draft=False, prerelease=False)))
        app.updates = UpdateCheck(lambda: future)
        app.updates.start()
        app.tick(0)
        app.render()
        assert app.update_prompt is not None
        assert [command for _, command in app.buttons] == [('update_no',), ('update_yes',)]
    app.command(('options',)); app.tick(200); app.render()
    assert ('toggle_updates',) in [command for _, command in app.buttons]
    app.command(('toggle_updates',))
    assert not AppSettings(app.settings.path).check_for_updates
    app.command(('toggle_updates',))
    assert AppSettings(app.settings.path).check_for_updates
    app.command(('back',)); app.tick(200)
    offer_update()
    app.command(('update_no',))
    app.tick(20)
    assert app.update_prompt is None and host.url is None
    app.render()
    yield 'Shared launch update prompt, persistent opt-out and No dismissal (authored metadata, offline)'
    # Input uses the real shared hit regions, not a test-only game-selection API.
    for key in ('shs', 'cod'):
        rect = next(rect for rect, command in app.buttons if command == ('choose_game', key))
        x, y = rect.center
        host._event(dict(kind='down', point=(x * 1.5, y * 1.5)))
        host._event(dict(kind='up', point=(x * 1.5, y * 1.5)))
        assert app.selected_game == key and app.screen == 'setup'
        yield f'{key}: shared touch hit testing and asset setup'
        app.command(('browse', 'apk'))
        assert host.picker == 'apk'
        host.picker = None
        app.command(('switch_games',))
        yield f'{key}: native document request and switch game'
    fake = SimpleNamespace(game_id='shs', base_members={})
    for name in ('ArialRoundedMTBold16', 'ArialMT15', 'TrebuchetMS_Bold20', 'PajamaHip26'):
        font, atlas = render_font(fake, name)
        assert font.glyphs[65].advance > 0 and font.cap_height > 0
        glyph = font.glyphs[65]
        assert atlas.crop((glyph.x, glyph.y, glyph.x + glyph.width, glyph.y + glyph.height)).getbbox()
    cod = SimpleNamespace(game_id='cod', base_members={})
    cod_font, cod_atlas = render_font(cod, 'PajamaHip26')
    assert cod_font.cap_height > 0 and cod_atlas.getbbox()
    yield 'Native original-font lookup, fallback, glyph atlas and metrics'
    config = host.directory / 'ios-playback-input.json'
    if config.is_file():
        for index, item in enumerate(json.loads(config.read_text())):
            # Each archive variant gets a fresh diagnostic library. Choosing
            # SHS again must not reuse the preceding IPA as the APK test's base.
            root = host.directory / 'Verification' / str(index)
            app.library_path = lambda key, root=root: root / key
            app.choose_game(item['game'])
            app.import_paths([item['path']])
            for count in range(3600):
                if not app.busy:
                    break
                yield None
            assert not app.busy, 'Original asset import timed out'
            assert app.library is not None, app.message
            app.tick(3000)
            yield f"{item['game']}: {app.library.kind.upper()} import and shared main menu"
            assert ('switch_games',) in [command for _, command in app.buttons], 'Main menu has no Switch Game action'
            offer_update()
            no_rect, yes_rect = (next(rect for rect, command in app.buttons if command == (kind,))
                                 for kind in ('update_no', 'update_yes'))
            assert tuple(no_rect) == (34, 288, 78, 29), 'No must use the left footer button region'
            assert tuple(yes_rect) == (208, 288, 78, 29), 'Yes must use the right footer button region'
            rect = next(rect for rect, command in app.buttons if command == ('update_yes',))
            point = [int(v * 1.5) for v in rect.center]
            normal = raster(app.renderer.canvas.snapshot()).tobytes()
            host._event(dict(kind='down', point=point)); app.render()
            assert app.pressed == ('update_yes',)
            assert raster(app.renderer.canvas.snapshot()).tobytes() != normal
            yield f"{item['game']}: native Yes/No update prompt and held button"
            host._event(dict(kind='up', point=point))
            assert host.url == PROJECT_URL + '/releases/tag/v999.0.0'
            host.url = None  # Verify handoff without opening a fictitious release.
            assert app.update_prompt is None and app.screen == 'main'
            yield f"{item['game']}: update acceptance opens only the release page"
            app.command(('help',))
            app.tick(200)  # Finish the native input-gated menu transition.
            app.render()
            assert ('project',) in [command for _, command in app.buttons], 'Help/About has no project link'
            app.command(('project',))
            assert host.url == PROJECT_URL, 'Project link did not reach the native host'
            host.url = None  # Verify the native handoff without launching Safari in diagnostics.
            assert any(command['kind'] == 'sound' for command in host.backend.mixer.commands), 'Menu click was not queued'
            yield f"{item['game']}: runtime version, project link and menu click"
            app.command(('back',))
            app.selected = app.library.episodes[0]['id']
            app.start(resume=False)
            seen = set()
            for count in range(600):
                session = app.game.session
                assert app.game.error is None, app.game.error
                if session.pending:
                    name = session.pending.name
                    seen.add(name)
                    if name == 'dialogue':
                        if not session.engine.dialogue_animation.complete:
                            # Let the native clock reveal text before the next tap.
                            pass
                        elif count % 30 == 0:
                            app.game.command(('continue',))
                    elif name in ('presentation', 'message_panel') and count % 30 == 0:
                        app.game.command(('continue',))
                    elif name == 'text_input' and count % 30 == 0:
                        # Type through the same byte/name validation path as UIKit.
                        for _ in session.pending.details.get('draft', ''):
                            host._event(dict(kind='key', key='backspace'))
                        pending = session.pending
                        host.handle_events([dict(kind='text', text=char) for char in 'Alex'])
                        assert pending.details['draft'] == 'Alex', 'Queued keyboard characters were lost'
                        host._event(dict(kind='key', key='return'))
                    elif name == 'choice' and count % 30 == 0:
                        selected = next((i for i, enabled in enumerate(session.pending.details['enabled']) if enabled), None)
                        if selected is not None:
                            app.game.command(('choose', selected))
                    elif name == 'character_picker' and count % 30 == 0:
                        app.game.command(('choose', 0))
                        app.game.command(('continue',))
                yield None
            assert app.game.error is None, app.game.error
            # Background checkpoints and manual slots use exactly MenuState/Session.
            before = app.game.session.snapshot()
            host.active(False)
            assert app.state.resume_path(app.selected).is_file()
            host.active(True)
            assert app.game.session.snapshot() == before
            yield f"{item['game']}: original playback ({', '.join(sorted(seen))}) and checkpoint"
            app.game.render()
            rect = next(rect for rect, command in app.game.buttons if command == ('menu',))
            x, y = rect.center
            host._event(dict(kind='down', point=(x, y)))
            assert app.game.press.pressed == ('menu',) and not app.game.menu_open
            yield f"{item['game']}: orange gear held before pause opens"
            host._event(dict(kind='up', point=(x, y)))
            assert app.game.menu_open and not app.game.pause_elapsed_ms
            from exp_runtime.games import GAMES
            import base64
            profile = GAMES[item['game']]
            opening = base64.b64encode(app.library.read_asset(profile.PAUSE_SOUND)).decode('ascii')
            assert dict(kind='sound', data=opening) in host.backend.mixer.commands
            frozen = app.game.session.snapshot()
            yield f"{item['game']}: pause opening and native menu click"
            app.tick(100)
            app.game.render()
            assert 0 < app.game.pause_elapsed_ms < 400 and not app.game.buttons
            assert app.game.session.snapshot() == frozen
            yield f"{item['game']}: pause centered zoom with frozen story and gated input"
            app.tick(400)
            app.game.render()
            assert [command for _, command in app.game.buttons] == [
                ('resume',), ('pause_page', 'options'), ('pause_page', 'help'), ('main_menu',)]
            rect = next(rect for rect, command in app.game.buttons if command == ('pause_page', 'options'))
            x, y = rect.center
            host._event(dict(kind='down', point=(x, y)))
            assert app.game.press.pressed == ('pause_page', 'options'), 'Pause row did not highlight under the finger'
            app.tick(1000)
            assert app.game.session.snapshot() == frozen
            yield f"{item['game']}: pause held selection and intact row borders"
            host._event(dict(kind='move', point=(0, 0)))
            assert app.game.press.pressed is None
            host._event(dict(kind='up', point=(0, 0)))
            assert app.screen == 'game' and app.game.menu_open
            host._event(dict(kind='down', point=(x, y)))
            host._event(dict(kind='up', point=(x, y)))
            assert app.paused_menu and app.screen == 'options'
            click = base64.b64encode(app.library.read_asset(profile.CLICK_SOUND)).decode('ascii')
            assert dict(kind='sound', data=click) in host.backend.mixer.commands
            yield f"{item['game']}: pause Options action and native menu click"
            app.command(('cheats',)); app.command(('toggle', 'choice_hints'))
            assert app.game.choice_hints
            app.tick(2000)
            assert app.game.session.snapshot() == frozen
            app.back()
            app.command(('save',))
            app.message = ''
            saved = app.game.session.snapshot()
            app.command(('load',))
            assert app.screen == 'game'
            assert app.game.session.snapshot() == saved
            yield f"{item['game']}: native pause menu, choice hint setting, frozen clocks and manual save/load"
            if item['game'] == 'shs':
                from exp_runtime.desktop import Desktop
                original = app.game
                app.game = Desktop(Session(app.library.open_episode('Football_Star.exp')),
                                   audio=False, window=app.window)
                app.game.tick(4000)
                app.game.command(('continue',))
                app.game.tick(4000)
                badge = app.game.session.engine.scene_badge
                assert badge and badge.text == 'Before School'
                if app.library.kind == 'ipa':
                    from exp_runtime.scene_badge import outline_badge_text
                    region = app.game.session.resources.dialogue_layout().bank.rectangle(67, 3)
                    font = app.game.story_text.font('ArialMT14')
                    layout, (x, y), scale = outline_badge_text(badge.text, font, region, (0, 0, 0))
                    left, top, right, bottom = layout.ink_bounds
                    assert len(layout.lines) == 1 and scale == 1
                    assert region.x <= x + left and x + right <= region.x + region.width
                    assert region.y <= y + top and y + bottom <= region.y + region.height
                yield 'shs: Football Star scene badge within its native text region'
                # Reach the original classroom quiz through the story's normal
                # setup and choices. Original script data stays in this library.
                session = app.game.session
                for _ in range(400):
                    action = session.pending
                    if session.scene == 25004 and action.name == 'choice' and action.request.pc == 300:
                        break
                    if action.name == 'choice':
                        session.answer(next(i for i, on in enumerate(action.details['enabled']) if on))
                    elif action.name == 'text_input':
                        session.answer('Alex')
                    elif action.name == 'character_picker':
                        session.answer()
                    elif action.name in ('dialogue', 'presentation', 'message_panel'):
                        session.tick(4000)
                        session.answer()
                    else:
                        raise AssertionError(f'Unexpected pre-quiz action: {action.name}')
                else:
                    raise AssertionError('Football Star did not reach its classroom quiz')
                from copy import deepcopy
                before = session.snapshot()
                expected = []
                for i in range(len(session.pending.details['options'])):
                    branch = deepcopy(session, {id(session.resources): session.resources,
                                                 id(session.vm.program): session.vm.program})
                    response = branch.answer(i).details['text']
                    assert response in ('Correct!', 'Wrong!')
                    expected.append('gain' if response == 'Correct!' else 'loss')
                app.game.choice_hints = True
                app.game.render()
                assert [hint.kind for hint in app.game.choice_renderer.hints] == expected
                assert expected.count('gain') == 1 and session.snapshot() == before
                yield 'shs: original classroom quiz hints with shuffled answers and untouched state'
                resources = app.library.open_episode(app.selected)
                resources.programs[25001] = _authored_football()
                app.game = Desktop(Session(resources), audio=False, window=app.window)
                session = app.game.session
                held = session.vm.snapshot()
                for _ in range(15):
                    session.tick(250)
                session.answer()
                for _ in range(100):
                    assert app.game.error is None, app.game.error
                    yield None
                assert session.pending.name == 'football'
                assert session.vm.snapshot() == held
                assert app.game.football_renderer.score_font()[0].height == 15
                yield 'shs: football scoreboard, native sprite scaling and held VM'
                for grid in (False, True):
                    resources = app.library.open_episode(app.selected)
                    resources.programs[25001] = _authored_word_game(grid)
                    app.game = Desktop(Session(resources), audio=False, window=app.window)
                    app.game.choice_hints = True
                    session = app.game.session
                    held = session.vm.snapshot()
                    if grid:
                        for _ in range(60):
                            if session.engine.word_grid.phase == 1: break
                            session.tick(250)
                        assert session.engine.word_grid.phase == 1
                    for frame in range(60):
                        assert app.game.error is None, app.game.error
                        if not grid and frame % 12 == 11 and frame < 48:
                            session.answer(session.engine.word_game.weights.index(1))
                        yield None
                    assert session.pending.name == ('word_grid' if grid else 'word_game')
                    assert session.vm.snapshot() == held
                    yield 'shs: word grid projection and held VM' if grid else 'shs: timed word choices, score and held VM'
                    if grid:
                        game = session.engine.word_grid
                        path = game.find_path(game.starts[0], game.problem.words[0])
                        for index, cell in enumerate(path):
                            session.grid_pointer('move' if index else 'down', cell)
                        assert game.explosions and game.pop_ms
                        session.tick(100)
                        saved = session.snapshot()
                        assert Session.from_snapshot(resources, saved).snapshot() == saved
                        yield 'shs: grid tile fragments, pop animation and in-flight save restoration'
                        for _ in range(30):
                            if game.phase == 4: break
                            session.tick(250)
                        assert game.phase == 4
                        session.tick(250)
                        yield 'shs: solid grid tile flip and side faces'
                    else:
                        app.game.render()
                        game = session.engine.word_game
                        hints = app.game.choice_renderer.hints
                        assert [h.kind for h in hints] == ['gain' if w > 0 else 'loss' for w in game.weights]
                        index = game.weights.index(1)
                        rect = next(rect for rect, command in app.game.buttons if command == ('choose', index))
                        x, y = rect.center
                        score = game.score
                        host._event(dict(kind='down', point=(x, y)))
                        assert game.score == score and app.game.press.pressed == ('choose', index)
                        yield 'shs: word choice hints and held selection before release'
                        host._event(dict(kind='up', point=(x, y)))
                        assert game.score > score
                app.game = original
            app.return_to_menu()
            app.tick(1000)
            app.render()
            rect = next(rect for rect, command in app.buttons if command == ('switch_games',))
            x, y = rect.center
            host._event(dict(kind='down', point=(x * 1.5, y * 1.5)))
            host._event(dict(kind='up', point=(x * 1.5, y * 1.5)))
            other = 'cod' if item['game'] == 'shs' else 'shs'
            expected = 'main' if (app.library_path(other) / 'library.json').is_file() else 'games'
            assert app.screen == expected, 'Switch Game did not select the other installed game or chooser'
            if expected == 'main':
                assert app.selected_game == other
            yield f"{item['game']}: switch to the other installed game, or chooser when absent"
    yield 'Shared presentation verification complete'
