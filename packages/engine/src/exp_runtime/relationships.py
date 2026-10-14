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
        if (self.asset_id < 0 or not self.changed or self.loss
                or (self.character_id == 45 and self.asset_id in GAMES['shs'].RELATIONSHIP_ASSETS)):
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
        # CoD has no verified mapping to SHS's feedback sound IDs.
        if self.asset_id in GAMES['shs'].RELATIONSHIP_ASSETS:
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


@dataclass
class RelationshipAnimation:
    change: RelationshipChange
    delay_ms: int
    elapsed_ms: int = 0

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
            result.append(IndicatorPose(asset, px, py, angle - 190 - 20 * index,
                                        flash_asset, flash_scale, flash_alpha))
        return tuple(result)

    def validate(self):
        self.change.validate()
        if not 0 <= self.delay_ms <= 850 or not 0 <= self.elapsed_ms <= self.duration_ms:
            raise ValueError('Invalid relationship animation clock')
