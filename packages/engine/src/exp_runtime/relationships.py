"""NPC relationship icon selection and native portrait-child actions.

Evidence: FUN_000ab048, FUN_000a90f0, FUN_0009ce2c, FUN_0009caf4.
Asset bytes remain in the player's APK. Drawing never writes relationship state.
"""
from dataclasses import dataclass
import math

from .games import GAMES

FLASH_ASSETS = {asset: flash for game in GAMES.values() for asset, flash in game.RELATIONSHIP_FLASH.items()}
LOSS_ASSETS = {asset: loss for game in GAMES.values() for asset, loss in game.RELATIONSHIP_LOSS.items()}


def fraction(elapsed, duration):
    return min(1.0, max(0.0, elapsed / duration))


@dataclass(frozen=True)
class RelationshipChange:
    character_id: int
    asset_id: int
    count: int
    previous_asset: int
    previous_count: int

    @property
    def changed(self):
        return self.previous_count != -1 and (self.asset_id, self.count) != (self.previous_asset, self.previous_count)

    @property
    def loss(self):
        return self.asset_id >= 0 and self.changed and self.asset_id == self.previous_asset and self.count < self.previous_count

    @property
    def gain_from(self):
        shs = GAMES.get('shs')
        if (self.asset_id < 0 or not self.changed or self.loss
                or (self.character_id == 45 and shs is not None and self.asset_id in shs.RELATIONSHIP_ASSETS)):
            return None
        return self.previous_count if self.asset_id == self.previous_asset else 0

    @property
    def extra_delay_ms(self):
        if self.loss:
            return 600
        first = self.gain_from
        return 0 if first is None else 300 + 200 * (self.count - first - 1)

    @property
    def sound(self):
        # CoD's setCurrentSpeaker (00038008) and setStatusIconAnimated
        # (00043fc0) do not request relationship sounds.
        shs = GAMES.get('shs')
        if shs is not None and self.asset_id in shs.RELATIONSHIP_ASSETS:
            from .shs.relationships import sound
            return sound(self)
        return None

    def validate(self):
        if (not 0 < self.character_id <= 32767 or (self.asset_id != -1 and self.asset_id not in FLASH_ASSETS)
                or not 1 <= self.count <= 4 or not -32768 <= self.previous_asset <= 32767
                or not -1 <= self.previous_count <= 4):
            raise ValueError('Invalid relationship indicator state')


@dataclass(frozen=True)
class IndicatorPose:
    asset_id: int
    x: float
    y: float
    rotation: float
    flash_asset: int = -1
    flash_scale: float = 0.0
    flash_alpha: int = 0

    def validate(self):
        if (self.asset_id not in {*FLASH_ASSETS, *LOSS_ASSETS.values()}
                or self.flash_asset not in {-1, *FLASH_ASSETS.values()}
                or not all(math.isfinite(v) for v in (self.x, self.y, self.rotation, self.flash_scale))
                or abs(self.x) > 100 or not -100 <= self.y <= 600
                or not -720 <= self.rotation <= 360
                or not 0 <= self.flash_scale <= 2 or not 0 <= self.flash_alpha <= 200
                or self.flash_alpha and self.flash_asset == -1):
            raise ValueError('Invalid retained relationship icon')


@dataclass
class RelationshipAnimation:
    change: RelationshipChange
    delay_ms: int
    elapsed_ms: int = 0
    # Android's -1 request leaves the existing sprite children untouched.
    # Dialogue reattachment has already cancelled their actions recursively,
    # so retain the actual poses, including a partially faded ring.
    retained: list[IndicatorPose] | None = None

    @property
    def duration_ms(self):
        first = self.change.gain_from
        if first is not None:
            return self.delay_ms + 200 * (self.change.count - first - 1) + max(800, self.change.extra_delay_ms)
        return max(self.delay_ms, 2000 if self.change.loss else 0)

    def tick(self, elapsed_ms):
        self.elapsed_ms = min(self.duration_ms, self.elapsed_ms + elapsed_ms)

    def settle(self):
        self.elapsed_ms = self.duration_ms

    def poses(self):
        if self.retained is not None:
            return tuple(self.retained)
        change = self.change
        if change.asset_id < 0 or self.elapsed_ms < self.delay_ms:
            return ()
        count = change.previous_count if change.loss else change.count
        first, result = change.gain_from, []
        for index in range(count):
            asset, angle = change.asset_id, 195 + 20 * index
            drop, flash_asset, flash_scale, flash_alpha = 0.0, -1, 0.0, 0
            if index >= change.count:
                if self.elapsed_ms >= 2000:
                    continue
                asset = LOSS_ASSETS[asset]
                # Parent MoveTo(0,-500) starts after one second, independent
                # of the incoming portrait's visibility delay.
                drop = 500 * fraction(self.elapsed_ms - 1000, 1000)
            elif first is not None and index >= first:
                age = self.elapsed_ms - self.delay_ms - 200 * (index - first)
                if age < 0:
                    continue
                # RotateTo uses the shortest arc (00146a88), not a 195° spin.
                angle = (angle - 360) * fraction(age, change.extra_delay_ms)
                flash_asset = FLASH_ASSETS[asset]
                burst = fraction(age - 300, 500)
                flash_scale, flash_alpha = .5 + 1.5 * burst, int(200 * (1 - burst))
            x, y = ((61, 16), (62, 17), (62, 18), (64, 19))[index]
            radians = math.radians(angle)
            # Cocos rotates clockwise in GL coordinates. Convert to top Y.
            px = x * math.cos(radians) + y * math.sin(radians)
            py = x * math.sin(radians) - y * math.cos(radians) + drop
            result.append(IndicatorPose(asset, px, py, float(angle - 190 - 20 * index),
                                        flash_asset, flash_scale, flash_alpha))
        return tuple(result)

    HD_ARC_MS, HD_STAGGER_MS, HD_RING_MS = 300, 200, 500
    HD_LOSS_MS, HD_FALL_UNITS = 800, 458
    HD_ANGLE_STEP, HD_LOSS_END_DEGREES = 16.5, -15

    def hd_poses(self, slots):
        """HD's icon flourish (`SHSPortraitLayer setStatusIconAnimated`, `createRingEffect`), `slots` being each
        icon's resting offset from the housing's center in layout units.

        Gain: each new icon rides an arc of its slot's radius around the center for 0.3 s, from angle 0 through the
        top to `195 + 16.5 i` degrees, icons 0.2 s apart; then a ring image (3013 / 3015 / 3017) grows from half to
        full size over 0.5 s *under* the icon and is then gone: the bounds animation (0.5 s, half -> full size) is removed on
        completion and the ring layer's own bounds are empty (`createRingEffect`; an earlier reading of this had it
        stay for the whole line, which the owner's photos disproved).
        Loss: each lost icon (3014 / 3016 / 3018) rides the circle from its slot on to -15 degrees, then falls in a
        straight line, 0.8 s in all at constant speed. Icons are not rotated."""
        change = self.change
        if change.asset_id < 0 or self.elapsed_ms < self.delay_ms:
            return ()
        count = change.previous_count if change.loss else change.count
        first, result = change.gain_from, []
        for index in range(min(count, len(slots))):
            sx, sy = slots[index]
            asset, x, y = change.asset_id, sx, sy
            flash_asset, flash_scale, flash_alpha = -1, 0.0, 0
            if index >= change.count:
                t = (self.elapsed_ms - self.delay_ms) / self.HD_LOSS_MS
                if t >= 1:
                    continue
                asset = {3010: 3014, 3011: 3016, 3012: 3018}[asset]
                x, y = self._loss_point(sx, sy, slots[0][0], max(0., t))
            elif first is not None and index >= first:
                age = self.elapsed_ms - self.delay_ms - self.HD_STAGGER_MS * (index - first)
                if age < 0:
                    continue
                if age < self.HD_ARC_MS:
                    radius = math.hypot(sx, sy)
                    angle = math.radians((self.HD_ANGLE_STEP * index + 195 - 360) * age / self.HD_ARC_MS)
                    x, y = radius * math.cos(angle), radius * math.sin(angle)
                elif age - self.HD_ARC_MS < self.HD_RING_MS:
                    # The ring's bounds animation is removed on completion and the layer's own bounds are empty, so the
                    # ring is gone as soon as it has grown to full size.
                    ring = age - self.HD_ARC_MS
                    flash_asset = {3010: 3013, 3011: 3015, 3012: 3017}[asset]
                    flash_scale, flash_alpha = .5 + .5 * ring / self.HD_RING_MS, 255
            result.append(IndicatorPose(asset, x, y, 0, flash_asset, flash_scale, flash_alpha))
        return tuple(result)

    def _loss_point(self, sx, sy, fall_x, t):
        """A lost icon's place `t` (0..1) along its arc-then-fall path, at constant speed."""
        radius = math.hypot(sx, sy)
        start = math.atan2(sy, sx)
        end = math.radians(self.HD_LOSS_END_DEGREES)
        sweep = (end - start) % (2 * math.pi)            # onward through the top, as the icons arrived
        arc = radius * sweep
        ex, ey = radius * math.cos(end), radius * math.sin(end)
        line = math.hypot(fall_x - ex, self.HD_FALL_UNITS - ey)
        distance = t * (arc + line)
        if distance <= arc:
            angle = start + sweep * distance / arc
            return radius * math.cos(angle), radius * math.sin(angle)
        f = (distance - arc) / line
        return ex + (fall_x - ex) * f, ey + (self.HD_FALL_UNITS - ey) * f

    def validate(self):
        self.change.validate()
        if not 0 <= self.delay_ms <= 850 or not 0 <= self.elapsed_ms <= self.duration_ms:
            raise ValueError('Invalid relationship animation clock')
        if self.retained is not None:
            if self.change.asset_id != -1 or self.change.character_id == 45 or len(self.retained) > 4:
                raise ValueError('Invalid retained relationship request')
            for pose in self.retained:
                pose.validate()
