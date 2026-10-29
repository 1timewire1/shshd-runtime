"""Apple's "CgBI" PNG variant, read through Pillow.

Xcode's pngcrush rewrites the PNG files it ships into a private variant: an
extra leading `CgBI` chunk, a raw (headerless) deflate stream in the image
data, blue/green/red channel order and premultiplied alpha. Some HD resources
(the side panels' backdrop, resource 10) are such files inside the app bundle.
Pillow rejects them, so the stream is wrapped back into an ordinary zlib
stream, the private chunk dropped, and the channels put in order.
"""
from io import BytesIO
import struct
import zlib

from PIL import Image, ImageMath


class CgBIError(ValueError):
    pass


def _chunk(kind: bytes, body: bytes) -> bytes:
    return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))


def to_standard_png(data: bytes) -> tuple[bytes, bool]:
    """(an ordinary PNG, whether `data` was CgBI). Ordinary PNGs pass through."""
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise CgBIError('Not a PNG file')
    position, chunks, image, cgbi = 8, [], b'', False
    while position + 8 <= len(data):
        length, = struct.unpack('>I', data[position:position + 4])
        kind, body = data[position + 4:position + 8], data[position + 8:position + 8 + length]
        if len(body) != length:
            raise CgBIError('Truncated PNG chunk')
        position += 12 + length
        if kind == b'CgBI':
            cgbi = True
        elif kind == b'IDAT':
            image += body
        elif kind != b'IEND':
            chunks.append((kind, body))
    if not cgbi:
        return data, False
    try:
        raw = zlib.decompress(image, -15)
    except zlib.error as error:
        raise CgBIError(f'Invalid CgBI image data: {error}') from error
    out = bytearray(b'\x89PNG\r\n\x1a\n')
    for kind, body in chunks:
        out += _chunk(kind, body)
    out += _chunk(b'IDAT', zlib.compress(raw))
    out += _chunk(b'IEND', b'')
    return bytes(out), True


def decode(data: bytes) -> Image.Image:
    """The image as ordinary RGB or RGBA (alpha straight, not premultiplied)."""
    png, swapped = to_standard_png(data)
    try:
        image = Image.open(BytesIO(png))
        image.load()
    except (OSError, ValueError) as error:
        raise CgBIError(f'Cannot decode PNG: {error}') from error
    if not swapped:
        return image
    if image.mode not in ('RGB', 'RGBA'):
        raise CgBIError(f'Unsupported CgBI color mode {image.mode}')
    channels = list(image.split())
    channels[0], channels[2] = channels[2], channels[0]
    if image.mode == 'RGBA':
        # Un-premultiplied as min(255, value * 255 // alpha), a pixel with alpha 0 or 255 left as it is: in Pillow's
        # integer image maths (a byte loop in Python took ~100 ms a portrait on a phone, each new face).
        alpha = channels[3].convert('I')

        def straight(v):
            value, a = v['value'], v['alpha']
            divided = v['min'](value * 255 / v['max'](a, 1), 255)
            return (a == 0) * value + (a == 255) * value + (a != 0) * (a != 255) * divided

        channels[:3] = [ImageMath.lambda_eval(straight, value=plane.convert('I'), alpha=alpha).convert('L')
                        for plane in channels[:3]]
    return Image.merge(image.mode, channels)
