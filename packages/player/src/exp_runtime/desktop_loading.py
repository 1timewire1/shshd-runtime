"""Service 91's original loading panels, strings, fonts, and five-frame art."""
from functools import lru_cache

from . import graphics as pygame

from .fonts import TextStyle
from .hd_scale import S as HD_SCALE
from .menu import MenuStrings
from .ui_assets import Rect, read_ui


class LoadingRenderer:
    def __init__(self, resources, text_renderer, artwork):
        self.resources, self.text, self.art = resources, text_renderer, artwork
        # SRCALPHA: the background is composited separately by Desktop, at
        # real window resolution -- see desktop_dialogue.py's DialogueRenderer.
        self.canvas = pygame.Surface((320, 480), pygame.SRCALPHA).convert_alpha()
        self.pending_background = None
        self.pending_background_origin = (160, 180)

    @lru_cache(maxsize=1)
    def panel(self):
        layer = pygame.Surface((320, 480), pygame.SRCALPHA).convert_alpha()
        bank = self.resources.dialogue_layout().bank
        # FUN_0008d43c: top panel at GL (0,160), bottom at (-20,133).
        # A zero height argument preserves layout 22's native height of 60.
        for index, root in ((50, Rect(0, 170, 320, 150)), (22, Rect(-20, 287, 350, 60))):
            for node_id, (node, rect) in enumerate(bank.walk(index, root), 1):
                # Layout 22 node 13 (the timer label) and its subtree are hidden.
                if index == 22 and 13 <= node_id <= 17:
                    continue
                if node.kind == 1 and node.flags & 16 and rect.width > 0 and rect.height > 0:
                    slot, frame = node.payload
                    image = self.art.frame({0: 126, 2: 204}[slot], frame)
                    layer.blit(pygame.transform.scale(image, (rect.width, rect.height)), (rect.x, rect.y))
        strings = MenuStrings.load(self.resources.library)
        title = self.text.layout('ArialRoundedMTBold20', strings[31], 320, TextStyle(20, 0, (41, 104, 221)))
        message = self.text.layout('ArialRoundedMTBold16', strings[35], 300, TextStyle(15, 0, (41, 104, 221)))
        self.text.draw_layout(layer, 'ArialRoundedMTBold20', title, 160 - title.width / 2, 170 + title.height)
        self.text.draw_layout(layer, 'ArialRoundedMTBold16', message, 160 - message.width / 2, 245)
        return layer

    def draw(self, target, session):
        self.pending_background = self.art.image(session.engine.panel.background_id)
        self.pending_background_origin = self.art.background_origin(self.pending_background, session.engine)
        self.draw_panel(session.engine.loading.animation_frame(
            ios=getattr(self.resources.library, 'kind', 'apk') == 'ipa'))
        target.blit(pygame.transform.smoothscale(self.canvas, target.get_size()), (0, 0))
        return []  # Completion comes from the active timer, never a click.

    def draw_panel(self, frame):
        """The panels with pack 126's runner `frame` (23-27) on the transparent 320 x 480 canvas (also the menus'
        episode loading screen: application_hd.HdShell.load_episode)."""
        self.canvas.fill((0, 0, 0, 0))
        self.canvas.blit(self.panel(), (0, 0))
        icon = self.art.frame(126, frame)
        self.canvas.blit(icon, icon.get_rect(center=(155, 317)))
        return self.canvas


class HdLoadingRenderer:
    """HD's loading overlay in the whole 768 x 1024 frame (photographed on the iPad).

    A white band (243/255 opaque) between two blue rules spans the frame's width: rules at y 402-408 and
    626-631, "Loading" and "Please wait..." in bold blue sans centered on x 384 (ink 447-483 and 531-551), and
    the runner wheel straddling the lower rule -- the choice timer's wheel (gray rim, white ring, light-gray
    disc), the frame's blue border bulging around it -- with resource 155's runner frames 28-32 (500 ms each)
    in the disc. Drawn at the HD menus' scale (hd_scale: 2x, or the frame's own on Android): the menus' episode
    loading screen puts it in their layer as it is (a 2x band in Android's 1x layer was twice the screen's size).
    """
    S = HD_SCALE
    FRAME = (768, 1024)
    hd_layer = True
    edge_bar = 'bar'
    footer_text = ''
    BLUE = (41, 104, 221)
    RULE = TEXT = BLUE                  # the rules and the border bulging around the wheel; "Loading", "Please wait..."
    TOP_RULE, BOTTOM_RULE, RULE_THICKNESS = 402, 626, 6
    TITLE = dict(width=150, ink_top=447, ink_bottom=476)     # "Loading": cap top and baseline
    MESSAGE = dict(width=188, ink_top=531, ink_bottom=546)   # "Please wait...": cap top and baseline
    WHEEL_CENTER, WHEEL_RADIUS = (384, 621), 59

    def __init__(self, resources, art):
        self.resources, self.art = resources, art
        self.canvas = pygame.Surface((self.FRAME[0] * self.S, self.FRAME[1] * self.S), pygame.SRCALPHA).convert_alpha()
        self.pending_background = None
        self.pending_background_origin = (160, 180)

    def available(self):
        try:
            return self.art.hd_chrome() and bool(pygame.font.match_font('arial', bold=True))
        except (AttributeError, ValueError):
            return False

    @lru_cache(maxsize=8)
    def font_for(self, text, width):
        """Arial Bold at the size whose `text` is `width` frame px wide."""
        path = pygame.font.match_font('arial', bold=True)
        size = 40 * self.S
        measured = pygame.font.Font(path, size).size(text)[0] / self.S
        return pygame.font.Font(path, max(8, round(size * width / measured)))

    def line(self, text, spec):
        font = self.font_for(text, spec['width'])
        surface = font.render(text, True, self.TEXT)
        # Place by the capital top: the font's ascent, less the cap height, is the gap above capitals.
        cap = font.render('H', True, (0, 0, 0)).get_bounding_rect()
        x = (self.FRAME[0] * self.S - surface.get_width()) // 2
        self.canvas.blit(surface, (x, spec['ink_top'] * self.S - cap.y))

    @lru_cache(maxsize=1)
    def strings(self):
        hd = MenuStrings.parse(self.resources.library.hd_raw_resource(15))
        return hd[28], hd[32], hd[33]

    def runner(self, index):
        native = self.art.frame_native(155, 28 + index)
        return pygame.transform.smoothscale(native, (native.get_width() * self.S, native.get_height() * self.S))

    def draw(self, target, session):
        self.pending_background = self.art.image(session.engine.panel.background_id)
        # SHSEngine::initLoadingBar (HD 00022fec) gives each runner frame 0.07 s (0x23020), as both iPhone games do
        # (exp-runtime v0.6.0, loading.LoadingScreen.animation_frame); Android's is 500 ms.
        loading = session.engine.loading
        self.draw_band(loading.animation_frame(ios=True) if hasattr(loading, 'animation_frame') else loading.frame)
        return [(pygame.Rect(-32, 422, 92, 58), ('menu',))]

    def draw_band(self, frame):
        """The band with runner `frame` (23-27) on the transparent canvas, at S (also the menus' episode loading screen:
        application_hd.HdShell.load_episode)."""
        S, canvas = self.S, self.canvas
        canvas.fill((0, 0, 0, 0))
        width = self.FRAME[0] * S
        top, bottom, thick = self.TOP_RULE * S, self.BOTTOM_RULE * S, self.RULE_THICKNESS * S
        pygame.draw.rect(canvas, (255, 255, 255, 243), (0, top, width, bottom - top + thick))
        pygame.draw.rect(canvas, self.RULE, (0, top, width, thick))
        pygame.draw.rect(canvas, self.RULE, (0, bottom, width, thick))
        title, message, self.footer_text = self.strings()
        self.line(title, self.TITLE)
        self.line(message, self.MESSAGE)
        cx, cy = self.WHEEL_CENTER[0] * S, self.WHEEL_CENTER[1] * S
        r = self.WHEEL_RADIUS * S
        # Below the lower rule the blue border bulges around the wheel; above it the wheel has a gray rim.
        clip = canvas.get_clip()
        canvas.set_clip(pygame.Rect(0, bottom - S, width, canvas.get_height()))
        pygame.draw.circle(canvas, self.RULE, (cx, cy), round(r * 1.1))
        canvas.set_clip(pygame.Rect(0, 0, width, bottom - S))
        pygame.draw.circle(canvas, (177, 177, 177), (cx, cy), r)
        canvas.set_clip(clip)
        pygame.draw.circle(canvas, (255, 255, 255), (cx, cy), round(r * 0.965))
        pygame.draw.circle(canvas, (224, 224, 224), (cx, cy), round(r * 0.81))
        runner = self.runner((frame - 23) % 5)
        canvas.blit(runner, runner.get_rect(center=(cx, cy)))
        return canvas


class CodLoadingBand(HdLoadingRenderer):
    """Cause of Death has no HD release: the menus' episode loading screen (application_hd.HdShell.load_episode)
    draws SHS HD's band in CoD's dress (owner, 2026-10-22), not its iPhone panels stretched to the HD frame. The rules
    take the iPhone panel's dark grey (layout 50's border, sampled 79 / 81 / 81), the text its strings 31 / 35 in black
    (owner), and the runner is CoD's pack 126 frames 23-27 (with the SHS HD art source SHS HD's poses turned grey,
    cod/hd_art.py) at twice its iPhone points, SHS HD's size."""
    RULE, TEXT = (79, 81, 81), (0, 0, 0)

    def available(self):
        try:
            return bool(pygame.font.match_font('arial', bold=True))
        except (AttributeError, ValueError):
            return False

    @lru_cache(maxsize=1)
    def strings(self):
        strings = MenuStrings.load(self.resources.library)
        return strings[31], strings[35], ''

    def runner(self, index):
        if not getattr(self.resources, 'hd_ready', lambda: True)():
            # CoD's HD frames are still being derived (CodShell.warm_hd_art): its own iPhone runner meanwhile, rather
            # than deriving them here and holding up the frame.
            frame = self.art._android_pack(126).images[23 + index]
            image = pygame.image.frombytes(frame.pixels, (frame.width, frame.height), frame.mode).convert_alpha()
            return pygame.transform.smoothscale(image, (frame.width * 2 * self.S, frame.height * 2 * self.S))
        width, height = self.art.logical_size(126, 23 + index)
        return pygame.transform.smoothscale(self.art.frame_native(126, 23 + index),
                                            (round(width * 2 * self.S), round(height * 2 * self.S)))
