"""Verified Android setString order for the shared story panels.

The renderer reads each label's saved incoming byte. Assigning text, including
the same text again, advances the native global; drawing/measurement does not.
CSFont and external title atlases do not use this bitmap-font variable.
"""
from .choice import BODY_FONT, ChoiceLayout
from .fonts import TextStyle, layout_label, layout_text
from .menu_assets import MenuStrings
from .text_input import NAME_FONT


class StoryLabels:
    def __init__(self, session):
        self.session = session
        self.resources = session.resources
        self.layout = self.resources.dialogue_layout()
        self.history = session.engine.text_history

    def assign(self, key, name, text, style, width=2**31):
        font = self.layout.font(name)
        self.history.update(key, font, text, layout_text(font, text, width, style), markers=style.markers)

    def footer(self, index):
        text = MenuStrings.load(self.resources)[index] if index is not None else ''
        if text != self.history.footer:
            font = self.layout.font('ArialMT14')
            self.history.update('footer', font, text,
                                layout_label(font, text, 0, 0, TextStyle(14, 8), 0x0a))
            self.history.footer = text  # 0007d4c8 skips identical assignments.

    def choice(self, details):
        engine = self.session.engine
        game = engine.word_game
        if game is not None:
            # 000b033c creates the score before constructing the option rows.
            self.word_score()
            details = dict(details, options=game.options, enabled=[True] * 4, minigame=True)
        character = details['character_id']
        variants = engine.character_art_variants.get(character, ())
        ChoiceLayout(self.resources).prepare(
            details, engine.speaker_names, self.history,
            theme=engine.numbers.get(engine.number_key(character, 651), 0),
            has_portrait=character >= 0 and bool(variants) and variants[0] > 0)
        self.footer(40 if game is not None or details['timeout_ms'] > 0 else 38)

    def word_score(self):
        game = self.session.engine.word_game
        font = self.layout.font(BODY_FONT)
        for key, text in (('word_score', str(game.score)), ('word_delta', f'{game.last_delta:+d}')):
            if key == 'word_delta' and not game.last_delta:
                continue
            # 000d5914/000d5e18 initialize, configure and then assign each new
            # score label. The centered 18x15 region has no word wrapping.
            self.assign(key, BODY_FONT, text, TextStyle(14))
            self.history.update(key, font, text, layout_label(font, text, 18, 15, TextStyle(14), 0x0a))

    def word_round(self, previous_options):
        self.word_score()
        # 000afee8 updates the score first. 000af32c then reassigns all four
        # outgoing labels before assigning the four freshly dealt strings.
        for options in (previous_options, self.session.engine.word_game.options):
            for index, text in enumerate(options):
                self.assign(f'choice_{index}', BODY_FONT, text, TextStyle(12, 1),
                            self.layout.bank.layouts[65].width - 16)

    def picker(self):
        # 000d2558 uses its own PajamaHip26 object, not the dialogue name bank.
        self.assign('picker_title', 'PajamaHip26', self.session.pending.details['text'],
                    TextStyle(16, -16), 300)
        self.footer(37)

    def badge(self):
        badge = self.session.engine.scene_badge
        if badge is not None:
            # Both creation and replacement allocate a label initialized with
            # "SHS" before the final caption (0007b97c). Removal draws no text.
            self.assign('scene_badge', BODY_FONT, 'SHS', TextStyle(14))
            self.assign('scene_badge', BODY_FONT, badge.text, TextStyle(14, 1), 110)

    def message(self, *, initial=False, previous_caption=None):
        panel = self.session.engine.message_panel
        if initial:
            # 000abd0c initializes both newly allocated labels with "test"
            # before their final setString. The measurement font is separate.
            self.assign('message_title', 'ArialRoundedMTBold20', 'test', TextStyle(10, 7))
            self.assign('message_title', 'ArialRoundedMTBold20', panel.title, TextStyle(10, 7))
            self.assign('message_body', 'ArialRoundedMTBold16', 'test', TextStyle(10, 3))
            self.assign('message_body', 'ArialRoundedMTBold16', panel.text, TextStyle(10, 3),
                        self.layout.bank.layouts[24].width - 25)
        strings = MenuStrings.load(self.resources)
        caption = strings[29] if panel.ready else f'{strings[30]} ({panel.countdown})'
        # 000acc28 assigns once on attachment; 000acb18 only on a change.
        if initial or previous_caption != (panel.ready, panel.countdown):
            self.assign('message_continue', 'TrebuchetMS_Bold14', caption, TextStyle(16, 5))
        if not initial:
            self.footer(36 if panel.ready else 39)

    def entry(self, *, initial=False):
        details = self.session.pending.details
        if initial:
            self.footer(None)
            self.assign('input_title', 'ArialRoundedMTBold30', details['title'], TextStyle(30, -30))
            # The subsequent anchor rebuild uses ordinary BMFont kerning and
            # does not touch the game's global byte (00165c14).
            self.assign('input_prompt', 'ArialRoundedMTBold16', details['prompt'], TextStyle(16, -16))
        # 000d3ae8 assigns the draft on every active tick, even when unchanged.
        self.assign('input_name', NAME_FONT, details.get('draft', details['default']), TextStyle(26, -26))

    def loading(self):
        strings = MenuStrings.load(self.resources)
        self.assign('loading_title', 'ArialRoundedMTBold20', strings[31], TextStyle(20), 320)
        self.assign('loading_body', 'ArialRoundedMTBold16', strings[35], TextStyle(15), 300)


def story_labels(session):
    if (session.bitmap_history is not None and hasattr(session.resources, 'dialogue_layout')
            and hasattr(session.resources, 'read_ui_resource')
            and all(session.resources.exists(role) for role in (13, 14))):
        return StoryLabels(session)
    return None


def prepare_labels(session, action):
    if action.name not in ('choice', 'word_game', 'character_picker', 'message_panel',
                           'survey_confirmation', 'text_input', 'loading', 'dialogue', 'presentation',
                           'set_scene_badge'):
        return
    labels = story_labels(session)
    if labels is None:
        return
    if action.name in ('choice', 'word_game'):
        labels.choice(action.details)
    elif action.name == 'character_picker':
        labels.picker()
    elif action.name == 'set_scene_badge':
        labels.badge()
    elif action.name in ('message_panel', 'survey_confirmation'):
        labels.message(initial=True)
    elif action.name == 'text_input':
        labels.entry(initial=True)
    elif action.name == 'loading':
        labels.loading()
    elif action.name in ('dialogue', 'presentation'):
        labels.footer(36)
