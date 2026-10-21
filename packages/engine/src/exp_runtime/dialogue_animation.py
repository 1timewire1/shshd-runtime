"""Saved dialogue presentation clocks, independent of the display.

Native evidence and the 30 Hz letter-scheduler policy are documented in
docs/UI_FIDELITY.md. Portrait/name tweens use elapsed time; drawing is pure.
"""
from dataclasses import dataclass, field, replace
from math import degrees

from .portrait_effects import ExpressionDecorations
from .relationships import IndicatorPose, RelationshipAnimation, RelationshipChange


LETTER_HZ = 30
PORTRAIT_MS = 300
NAME_FADE_MS = 300
CONTINUE_MS = 250
BOX_TRAVEL_MS = 120
BOX_OPEN_MS = 200
EXPRESSION_MS = 1000
EXPRESSION_END_MS = 3150


@dataclass(frozen=True)
class DialoguePortrait:
    character_id: int
    asset_id: int
    mode: int
    theme: int
    expression: int = 0         # the line's own expression (HD's emotion effects key on it)

    @classmethod
    def from_details(cls, details, variants):
        character = details['visible_character_id']
        if details['presentation_mode'] not in (1, 2) or character < 0:
            return None
        art = variants[character]
        expression = details['expression']
        return cls(character, art[expression % len(art)], details['presentation_mode'], details['theme'], expression)

    def validate(self):
        if self.character_id < 0 or self.asset_id < 0 or self.mode not in (1, 2):
            raise ValueError('Invalid dialogue portrait')


def progress(elapsed, duration):
    return min(1.0, max(0.0, elapsed / duration))


@dataclass
class ExpressionTransition:
    """The two reusable portrait layers, independent of the current line."""
    previous: DialoguePortrait
    portrait: DialoguePortrait
    expression: int
    elapsed_ms: int = 0

    @property
    def alphas(self):
        # Both iOS changeExpression methods install independent fill-both
        # tracks: new art at +400..600 ms, old art at +600..1400 ms.
        return (round(255 * (1 - progress(self.elapsed_ms - 600, 800))),
                round(255 * progress(self.elapsed_ms - 400, 200)))

    def tick(self, elapsed_ms):
        self.elapsed_ms = min(EXPRESSION_END_MS - EXPRESSION_MS, self.elapsed_ms + elapsed_ms)

    def settle(self):
        # removeAllAnimations exposes model opacity: new=1, old=0.
        self.elapsed_ms = EXPRESSION_END_MS - EXPRESSION_MS

    def validate(self):
        self.previous.validate()
        self.portrait.validate()
        if (not 0 <= self.expression <= 32767
                or not 0 <= self.elapsed_ms <= EXPRESSION_END_MS - EXPRESSION_MS
                or (self.previous.character_id, self.previous.mode, self.previous.theme) !=
                   (self.portrait.character_id, self.portrait.mode, self.portrait.theme)):
            raise ValueError('Invalid expression transition')


@dataclass
class DialogueHistory:
    """Hidden native portrait position and the separate last-expression bytes."""
    anchor_mode: int = 0
    expressions: dict[int, int] = field(default_factory=dict)
    indicators: list[IndicatorPose] = field(default_factory=list)

    def remember(self, motion):
        # FUN_000a7e64 removes/re-adds the one active portrait with cleanup=1.
        # It does not exchange its status children with either outgoing copy.
        if motion is not None and motion.relationship is not None:
            self.indicators = list(motion.relationship.poses())

    def validate(self):
        if self.anchor_mode not in (0, 1, 2) or any(
                not 0 <= character <= 32767 or not -128 <= expression <= 127
                for character, expression in self.expressions.items()):
            raise ValueError('Invalid dialogue portrait history')
        if len(self.indicators) > 4:
            raise ValueError('Invalid retained relationship icons')
        for pose in self.indicators:
            pose.validate()


@dataclass
class DialogueAnimation:
    text_length: int
    portrait: DialoguePortrait | None = None
    previous: DialoguePortrait | None = None
    changed: bool = True
    page_turn: bool = False
    elapsed_ms: int = 0
    revealed: int = 0
    complete: bool = False
    finish_requested: bool = False
    finish_step: int = 0
    wobble_direction: int = 0
    relationship: RelationshipAnimation | None = None
    # Since the dialogue appeared, uncapped (presentation_ms stops at EXPRESSION_END_MS): HD's emotion effects and
    # notice letters run past it. Page turns do not restart it.
    age_ms: int = 0
    continue_ms: int = 0
    box_grow: bool = False
    native_lifecycle: bool = True
    anchor_mode: int = 0
    initial_portrait: DialoguePortrait | None = None
    initial_expression: int = 0
    expression: int = 0
    presentation_ms: int = 0
    visuals_finished: bool = False
    housing_clipped: bool = False
    expression_effects: bool = True
    expression_transition: ExpressionTransition | None = None
    expression_decorations: ExpressionDecorations = field(default_factory=ExpressionDecorations)

    @classmethod
    def start(cls, details, variants, previous=None, history=None, *, retain_suppressed=False, length=None):
        """`length`: the source indices the reveal runs over (Session._typed_length), by default the whole remaining
        text, as Android's cursor scans it."""
        if history is not None:
            history.remember(previous)
        portrait = DialoguePortrait.from_details(details, variants)
        old = previous.displayed_portrait if previous else None
        changed = previous is None or ((old.character_id if old else -1) !=
                                       (portrait.character_id if portrait else -1))
        motion = cls(len(details['text']) - details['page_start'] if length is None else length, portrait,
                   old if changed else None, changed,
                   wobble_direction=(20 if details['presentation_mode'] == 2 else -20)
                   if details.get('box_wobble', False) else 0)
        motion.box_grow = bool(changed and not motion.wobble_direction)
        motion.anchor_mode = portrait.mode if portrait else history.anchor_mode if history else (
            previous.anchor_mode if previous else 0)
        motion.expression = details['expression']
        motion.initial_expression = details.get('initial_expression', details['expression'])
        motion.initial_portrait = DialoguePortrait.from_details(
            dict(details, expression=motion.initial_expression), variants)
        if (portrait is not None and previous is not None and not changed and portrait.mode == previous.portrait.mode):
            # setSpeaker redraws the current layer but only cancels its
            # tracks when the character or side changes. A short next line
            # must not snap to the cached expression or restart the old fade.
            track = previous.expression_transition
            if track is not None:
                motion.expression_transition = replace(track, portrait=motion.initial_portrait,
                    previous=replace(track.previous, theme=portrait.theme))
            motion.expression_decorations = replace(previous.expression_decorations)
        motion.housing_clipped = not motion.box_grow and not motion.wobble_direction
        if history is not None and portrait is not None:
            history.anchor_mode = portrait.mode
            history.expressions[portrait.character_id] = motion.initial_expression
        if details.get('relationship') is not None:
            change = RelationshipChange(**details['relationship'])
            change.validate()
            motion.relationship = RelationshipAnimation(change, motion.portrait_delay_ms + PORTRAIT_MS if changed else 0)
            if retain_suppressed and change.asset_id == -1 and change.character_id != 45:
                motion.relationship.retained = list(history.indicators) if history else []
        if history is not None and portrait is not None:
            # Player portraits request (0,0), explicitly clearing the slots.
            history.indicators = list(motion.relationship.poses()) if motion.relationship else []
        return motion

    @property
    def portrait_delay_ms(self):
        # FUN_000aaa40 waits for the outgoing portrait only on the same side.
        same_side = self.previous and self.portrait and self.previous.mode == self.portrait.mode
        return 250 + (PORTRAIT_MS if same_side else 0)

    @property
    def name_delay_ms(self):
        duration = PORTRAIT_MS if self.changed and self.portrait else 0
        same_side = self.previous and self.portrait and self.previous.mode == self.portrait.mode
        return 250 + (PORTRAIT_MS if same_side else 0) + duration + 120 + self.relationship_delay_ms

    @property
    def relationship_delay_ms(self):
        return self.relationship.change.extra_delay_ms if self.relationship and not self.page_turn else 0

    @property
    def text_delay_ms(self):
        if self.page_turn:
            return 350  # FUN_000a9868, next substring.
        delay = self.name_delay_ms - (120 if self.wobble_direction else 0) if self.changed else 250 + self.relationship_delay_ms
        return delay + (400 if self.native_lifecycle and self.wobble_direction else 0)

    @property
    def shake_start_ms(self):
        # GameModel::shakeDialog: hold opacity at zero for the old 100ms
        # fade interval plus 600ms when the speaker changes.
        return 100 + (600 if self.changed else 0)

    @property
    def box_alpha(self):
        return 0 if (self.native_lifecycle and self.wobble_direction and not self.visuals_finished
                     and self.elapsed_ms < self.shake_start_ms) else 255

    @property
    def housing_clip_ms(self):
        return self.shake_start_ms + 250 if self.wobble_direction else self.name_delay_ms + BOX_OPEN_MS

    @property
    def box_scale(self):
        if not self.native_lifecycle or not self.wobble_direction or self.visuals_finished:
            return 1.0
        return .5 + .5 * progress(self.elapsed_ms - self.shake_start_ms, 125)

    @property
    def box_rotation(self):
        if self.visuals_finished:
            return 0.0
        if self.native_lifecycle:
            if not self.wobble_direction:
                return 0.0
            t = progress(self.elapsed_ms - self.shake_start_ms, 250)
            angle = -.25 if self.wobble_direction == 20 else .25
            return degrees(angle * (1 - 2 * t) if t < .75 else -angle / 2 * (1 - t) / .25)
        # FUN_0007c9e8: rotate to the opposite 20-degree angle in 70ms,
        # delay 2ms (right) / 5ms (other), then rotate to zero in 70ms.
        t, angle = self.elapsed_ms, self.wobble_direction
        pause = 2 if angle == 20 else 5
        if t < 70:
            return angle * (1 - 2 * t / 70)
        return -angle * (1 - progress(t - 70 - pause, 70))

    def box_rect(self, box, portrait):
        """Native iOS bubble keyframes; layout and text regions stay final-sized.

        setupAnimationsForTextLayer: 1x1 at the portrait, travel to a
        full-width 20px strip in 120ms, then grow to final height in 200ms.
        The nine border pieces keep their own dimensions throughout.
        """
        if not self.box_grow or self.page_turn or self.visuals_finished:
            return box
        from .ui_assets import Rect
        elapsed = self.elapsed_ms - (self.name_delay_ms - BOX_TRAVEL_MS)
        if elapsed < BOX_TRAVEL_MS:
            x, y = portrait.center if portrait is not None else (0, 0)
            if portrait is not None:
                y -= 5  # Same shared logical origin as the portrait group.
            t = progress(elapsed, BOX_TRAVEL_MS)
            return Rect(round(x + (box.x - x) * t), round(y + (box.y - y) * t),
                        max(1, round(1 + (box.width - 1) * t)), round(1 + 19 * t))
        t = progress(elapsed - BOX_TRAVEL_MS, BOX_OPEN_MS)
        return Rect(box.x, box.y, box.width, round(20 + (box.height - 20) * t))

    @property
    def duration_ms(self):
        return max(self.name_delay_ms + NAME_FADE_MS,
                   self.shake_start_ms + 250 if self.native_lifecycle and self.wobble_direction else 0,
                   self.text_delay_ms + ((self.text_length + 2) * 1000 + LETTER_HZ - 1) // LETTER_HZ)

    @property
    def portrait_scale(self):
        return progress(self.elapsed_ms - self.portrait_delay_ms, PORTRAIT_MS) if self.changed else 1.0

    @property
    def previous_scale(self):
        return 1.0 - progress(self.elapsed_ms, PORTRAIT_MS)

    @property
    def name_alpha(self):
        if self.visuals_finished:
            return 255
        return int(255 * progress(self.elapsed_ms - self.name_delay_ms, NAME_FADE_MS)) if self.changed else 255

    @property
    def displayed_portrait(self):
        # The native cache changes at the tick boundary, before the art fades.
        return self.portrait if self.presentation_ms >= EXPRESSION_MS else self.initial_portrait

    @property
    def expression_alphas(self):
        if self.expression_transition is not None:
            return self.expression_transition.alphas
        if self.initial_portrait == self.portrait or not self.native_lifecycle:
            return 0, 255
        return 255, 0

    @property
    def expression_portraits(self):
        track = self.expression_transition
        return (track.previous, track.portrait) if track else (self.initial_portrait, self.portrait)

    @property
    def continue_scale(self):
        return progress(self.continue_ms, CONTINUE_MS) if self.complete else 0.0

    def _callbacks(self, elapsed_ms):
        # The native 3 ms selector reveals ONE source index per scheduler
        # update, discarding excess dt. Use its configured 30 fps cadence for
        # letters while allowing smooth portrait motion at any display rate.
        first = max(1, (self.text_delay_ms * LETTER_HZ + 999) // 1000)
        return max(0, elapsed_ms * LETTER_HZ // 1000 - first + 1)

    def tick(self, elapsed_ms, *, ui=True):
        self.age_ms += elapsed_ms           # this fork's HD renderer clock (letters, portrait housing)
        before = self.presentation_ms
        self.expression_decorations.tick(elapsed_ms)
        if ui or self.presentation_ms >= EXPRESSION_MS:
            # The UI tick triggers changeExpression once. Its installed CA
            # tracks then run independently, including under an outgoing fade.
            self.presentation_ms = min(EXPRESSION_END_MS, self.presentation_ms + elapsed_ms)
        if (self.native_lifecycle and self.portrait is not None
                and self.initial_expression != self.expression
                and before < EXPRESSION_MS <= self.presentation_ms):
            self.expression_transition = ExpressionTransition(
                self.initial_portrait, self.portrait, self.expression,
                self.presentation_ms - EXPRESSION_MS)
            if self.expression_effects:
                self.expression_decorations.change(self.expression, self.presentation_ms - EXPRESSION_MS)
        elif self.expression_transition is not None:
            self.expression_transition.tick(elapsed_ms)
        if (self.native_lifecycle and (self.box_grow or self.wobble_direction)
                and not self.page_turn and not self.visuals_finished and
                self.elapsed_ms + elapsed_ms >= self.housing_clip_ms):
            self.housing_clipped = True
        if self.relationship:
            self.relationship.tick(elapsed_ms)
        end = self.elapsed_ms + elapsed_ms
        old = self._callbacks(self.elapsed_ms)
        self.elapsed_ms = min(self.duration_ms, self.elapsed_ms + elapsed_ms)
        due = self._callbacks(self.elapsed_ms) - old
        if self.complete:
            self.continue_ms = min(CONTINUE_MS, self.continue_ms + elapsed_ms)
            return
        if due <= 0:
            return
        needed = self.text_length + 1 - old
        if self.finish_requested:
            # Native input sets a flag. The next selector visits one index,
            # then a following callback unhides the whole label and completes.
            needed = 1 if self.revealed == self.text_length else 2 - self.finish_step
            if due >= needed:
                self.revealed, self.complete = self.text_length, True
                self.finish_step = 0
            else:
                self.revealed = min(self.text_length, self.revealed + 1)
                self.finish_step = 1
        else:
            self.complete = self.revealed + due > self.text_length
            self.revealed = min(self.text_length, self.revealed + due)
        if self.complete:
            # iOS expandContinue waits for the end of typing, then expands
            # vertically for 250 ms. Account for completion within this tick.
            first = max(1, (self.text_delay_ms * LETTER_HZ + 999) // 1000)
            finished = ((first - 1 + old + needed) * 1000 + LETTER_HZ - 1) // LETTER_HZ
            self.continue_ms = min(CONTINUE_MS, max(0, end - finished))

    def finish(self):
        self.finish_requested = True
        # touchesBegan stops the bubble and title, but leaves portrait and
        # expression tracks running. Its SHSUIDialog::stopAnimation (CoD
        # 0003b124, SHS HD 0004440c) clips the housing against the settled
        # bubble at once, so a tap during the grow does not leave the ring
        # whole over the box.
        if self.native_lifecycle:
            self.visuals_finished = True
            self.housing_clipped = True

    def next_page(self, length):
        self.wobble_direction = 0
        self.box_grow = False
        self.text_length = length
        self.previous = None
        self.changed, self.page_turn = False, True
        self.elapsed_ms = self.revealed = self.finish_step = 0
        self.continue_ms = 0
        self.complete = self.finish_requested = False
        self.visuals_finished = False

    def stop_layers(self):
        """CoD 0000f2ec: remove layer tracks before revealing the new UI.

        The UI's delayed changeExpression tick remains separate; cancelling
        Core Animation does not execute that future script-visible update.
        """
        self.elapsed_ms = self.duration_ms
        self.age_ms = max(self.age_ms, 60000)
        self.revealed, self.complete = self.text_length, True
        self.continue_ms = CONTINUE_MS
        self.housing_clipped = self.native_lifecycle
        if self.relationship:
            self.relationship.settle()
        if self.expression_transition:
            self.expression_transition.settle()
        self.expression_decorations.settle()

    def settle(self):
        """Old saves showed all text; migrate without replaying the entrance."""
        self.stop_layers()
        self.presentation_ms = EXPRESSION_END_MS
        if self.native_lifecycle and self.portrait and self.initial_expression != self.expression:
            self.expression_transition = ExpressionTransition(
                self.initial_portrait, self.portrait, self.expression,
                EXPRESSION_END_MS - EXPRESSION_MS)

    def validate(self):
        for portrait in (self.portrait, self.previous, self.initial_portrait):
            if portrait:
                portrait.validate()
        track = self.expression_transition
        self.expression_decorations.validate()
        requested = self.presentation_ms >= EXPRESSION_MS and self.initial_expression != self.expression
        if track is not None:
            track.validate()
            if (not self.native_lifecycle or self.portrait is None
                    or track.portrait != (self.portrait if requested else self.initial_portrait)
                    or requested and track.expression != self.expression):
                raise ValueError('Expression transition does not match its portrait')
        elif self.native_lifecycle and self.portrait is not None and requested:
            raise ValueError('Missing expression transition')
        if self.relationship:
            self.relationship.validate()
            if self.portrait is None or self.relationship.change.character_id != self.portrait.character_id:
                raise ValueError('Relationship indicators do not match the portrait')
        callbacks = self._callbacks(self.elapsed_ms)
        if (type(self.box_grow) is not bool or type(self.expression_effects) is not bool
                or (self.box_grow and (not self.changed or self.wobble_direction))
                or self.anchor_mode not in (0, 1, 2)
                or not 0 <= self.presentation_ms <= EXPRESSION_END_MS
                or not -128 <= self.initial_expression <= 32767
                or not 0 <= self.expression <= 32767
                or (self.visuals_finished and not self.finish_requested)
                or (self.native_lifecycle and self.housing_clipped and not self.page_turn and not self.visuals_finished
                    and (self.box_grow or self.wobble_direction) and self.elapsed_ms < self.housing_clip_ms)
                or ((self.initial_portrait is None) != (self.portrait is None))
                or (self.portrait is not None and (
                    self.anchor_mode != self.portrait.mode
                    or (self.initial_portrait.character_id, self.initial_portrait.mode, self.initial_portrait.theme) !=
                       (self.portrait.character_id, self.portrait.mode, self.portrait.theme)))
                or self.wobble_direction not in (-20, 0, 20)
                or self.text_length < 0 or not 0 <= self.elapsed_ms <= self.duration_ms
                or not 0 <= self.continue_ms <= CONTINUE_MS
                or (not self.complete and self.continue_ms)
                or not 0 <= self.revealed <= self.text_length
                or self.finish_step not in (0, 1)
                or (self.finish_step and not self.finish_requested)
                or (self.complete and self.finish_step)
                or (self.complete and self.revealed != self.text_length)
                or (not self.changed and self.previous is not None)
                or (self.page_turn and self.changed)
                or (callbacks == 0 and (self.revealed or self.complete))
                or (not self.finish_requested and
                    (self.revealed != min(self.text_length, callbacks)
                     or self.complete != (callbacks > self.text_length)))):
            raise ValueError('Invalid dialogue animation state')
