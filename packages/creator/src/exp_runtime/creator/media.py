"""Asset inspection and isolated rendering with the production player."""
import base64
from io import BytesIO
import json
import os
import subprocess
import sys
import wave

from .model import ProjectError


def audio_type(data):
    if data[:4] == b'RIFF' and data[8:12] == b'WAVE': return 'audio/wav'
    if data[:4] == b'FORM' and data[8:12] in (b'AIFF', b'AIFC'): return 'audio/aiff'
    if data[:3] == b'ID3' or data[:1] == b'\xff' and len(data) > 1 and data[1] & 0xe0 == 0xe0:
        return 'audio/mpeg'
    if data[:4] == b'OggS': return 'audio/ogg'
    return None


def worker(request):
    """SDL stays in a short-lived child: no windows, audio devices or live-state mutation."""
    env = dict(os.environ, PYGAME_HIDE_SUPPORT_PROMPT='1', SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy')
    try:
        result = subprocess.run([sys.executable, '-m', 'exp_runtime.creator.media'],
            input=json.dumps(request).encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, timeout=30, check=False)
    except subprocess.TimeoutExpired as error:
        raise ProjectError('Media preview exceeded its 30-second budget') from error
    if result.returncode:
        raise ProjectError('Media preview failed: ' + result.stderr.decode(errors='replace')[-2000:])
    return result.stdout


def inspect_asset(data):
    result = dict(bytes=len(data), type='unknown')
    mime = audio_type(data)
    if mime:
        result.update(type='audio', mime_type=mime)
        try:
            if mime == 'audio/wav':
                with wave.open(BytesIO(data)) as sound:
                    result['duration_ms'] = round(sound.getnframes() * 1000 / sound.getframerate())
            else:
                result.update(json.loads(worker(dict(mode='audio_info', data=base64.b64encode(data).decode()))))
        except (ValueError, wave.Error) as error: result['preview_error'] = str(error)
        return result
    if data.startswith(b'kiwi'):
        result['type'] = 'script'; return result
    try:
        from PIL import Image
        from exp_runtime.ui_assets import ImagePack
        if data.startswith((b'\x89PNG', b'\xff\xd8')):
            with Image.open(BytesIO(data)) as image:
                result.update(type='image', width=image.width, height=image.height, frames=1)
        else:
            pack = ImagePack.parse(data)
            result.update(type='image' if len(pack.images) == 1 else 'atlas', frames=len(pack.images),
                          width=pack.images[0].width if pack.images else 0,
                          height=pack.images[0].height if pack.images else 0)
    except (ValueError, OSError): pass
    return result


def thumbnail(data, *, frame=0, size=256):
    from PIL import Image
    from exp_runtime.ui_assets import ImagePack
    if type(frame) is not int or frame < 0 or type(size) is not int or not 32 <= size <= 1024:
        raise ProjectError('Use a nonnegative image frame and thumbnail size 32–1024')
    if data.startswith((b'\x89PNG', b'\xff\xd8')):
        if frame: raise ProjectError('This image has only frame 0')
        with Image.open(BytesIO(data)) as original: image = original.convert('RGBA')
    else:
        pack = ImagePack.parse(data)
        if frame >= len(pack.images): raise ProjectError('Frame does not exist in this image pack')
        raster = pack.images[frame]
        if raster.mode != 'RGBA': raise ProjectError('This image frame is a mask, not an RGBA image')
        image = Image.frombytes('RGBA', (raster.width, raster.height), raster.pixels)
    image.thumbnail((size, size))
    output = BytesIO(); image.save(output, format='PNG')
    return output.getvalue(), dict(width=image.width, height=image.height, frame=frame)


def audio_preview(data, *, start_ms=0, duration_ms=5000):
    if type(start_ms) is not int or not 0 <= start_ms <= 3600000 or type(duration_ms) is not int or not 1 <= duration_ms <= 10000:
        raise ProjectError('Audio start must be 0–3600000 ms and duration 1–10000 ms')
    if not audio_type(data): raise ProjectError('This resource is not a recognized audio stream')
    return worker(dict(mode='audio', data=base64.b64encode(data).decode(), start_ms=start_ms, duration_ms=duration_ms))


def render_playtest(debugger):
    if debugger.context is None:
        raise ProjectError('Start the playtest with an imported library for visual preview')
    if debugger.session.pending is None:
        raise ProjectError('Run to a visible input screen before rendering a preview')
    return worker(dict(mode='render', library=str(debugger.project.library), game=debugger.project.game,
        data=base64.b64encode(debugger.compilation.data).decode(), snapshot=debugger.session.snapshot()))


def main():
    request = json.load(sys.stdin)
    import pygame
    data = base64.b64decode(request['data'], validate=True)
    output = BytesIO()
    try:
        if request['mode'] in ('audio', 'audio_info'):
            pygame.mixer.init(frequency=22050, size=-16, channels=2)
            sound = pygame.mixer.Sound(file=BytesIO(data))
            if request['mode'] == 'audio_info':
                sys.stdout.write(json.dumps(dict(duration_ms=round(sound.get_length() * 1000)))); return
            frequency, size, channels = pygame.mixer.get_init()
            pcm = sound.get_raw()
            stride = channels * abs(size) // 8
            first = request['start_ms'] * frequency // 1000 * stride
            length = request['duration_ms'] * frequency // 1000 * stride
            if first >= len(pcm): raise ProjectError('Audio start is beyond the end of the resource')
            clip = pcm[first:first + length]
            if sys.byteorder == 'big':
                from array import array
                words = array('h'); words.frombytes(clip); words.byteswap(); clip = words.tobytes()
            with wave.open(output, 'wb') as wav:
                wav.setparams((channels, 2, frequency, 0, 'NONE', 'not compressed')); wav.writeframes(clip)
        elif request['mode'] == 'render':
            from .preview import preview_resources
            from exp_runtime.runtime import Session
            from exp_runtime.desktop import Desktop
            with preview_resources(data, request['library'], request['game']) as resources:
                session = Session.from_snapshot(resources, request['snapshot'])
                pygame.display.init(); window = pygame.display.set_mode((480, 720))
                app = Desktop(session, audio=False, window=window)
                app.render()
                if app.error: raise ProjectError(app.error)
                pygame.image.save(app.canvas, output, 'preview.png')
        else: raise ProjectError('Unknown media operation')
        sys.stdout.buffer.write(output.getvalue())
    finally:
        pygame.quit()


if __name__ == '__main__':
    try: main()
    except (ValueError, OSError, ImportError) as error:
        print(str(error), file=sys.stderr); sys.exit(1)
