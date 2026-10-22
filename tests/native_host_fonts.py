"""A stand-in for the iOS host's font service (ios/EXPRuntime/NativeFonts.m) for tests that run the native drawing
backend: `register`, `glyphs` and `text`, drawn with Pillow's default face."""
import base64
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont


class FontHost:
    def __init__(self):
        self.registered = []            # the font bytes registered, in order
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        operation = request.get('operation')
        if operation == 'register':
            self.registered.append(base64.b64decode(request['data']))
            return dict(face=f'Registered{len(self.registered)}')
        face = ImageFont.load_default(size=request['size'])
        text = request.get('text', '')
        if operation == 'glyphs':
            glyphs = []
            for char in text:
                left, top, right, bottom = face.getbbox(char, anchor='ls')
                glyphs.append([left, right, -bottom, -top, round(face.getlength(char))])
            return dict(glyphs=glyphs)
        ascent, descent = face.getmetrics()
        left = max(0, request.get('left', 0))
        result = dict(width=max(1, round(face.getlength(text) + left)), height=ascent + descent, ascent=ascent,
                      descent=descent)
        if not request.get('measure'):
            image = Image.new('RGBA', (result['width'], result['height']))
            ImageDraw.Draw(image).text((left, ascent), text, font=face, fill=tuple(request['color']), anchor='ls')
            stream = BytesIO()
            image.save(stream, format='PNG')
            result['png'] = base64.b64encode(stream.getvalue()).decode('ascii')
        return result
