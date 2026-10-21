"""Shared timed word-game rules; see docs/MINIGAMES.md."""
from dataclasses import dataclass, field


MINIGAMES = frozenset(('word_game', 'word_grid', 'football'))


@dataclass
class WordGame:
    good: list[str]
    bad: list[str]
    duration_ms: int
    refresh_ms: int
    remaining_ms: int
    refresh_remaining_ms: int
    options: list[str] = field(default_factory=list)
    weights: list[int] = field(default_factory=list)
    score: int = 0
    round: int = 0
    entry_ms: int = 400
    animation_ms: int = 0
    last_delta: int = 0
    # The HD build's own pacing (`SHSUIMenu::initActionMenu` -> SHSWidgetMenu / SHSMenu), used when `hd`: a tap
    # selects its row (SHSMenu's 0.1 s selectionCallback); then `handleMenuSelection` scores it, starts the score
    # effect (1 s) and flies the labels off (`flyAwayLabels`, flyOffDuration 0.5 s, input disabled); then
    # `flyOnNewChoices` deals and flies the new labels on (flyOnDuration 0.3 s), and input returns 0.7 s later
    # (`actionMenuFinished`). `SHSUIMenu::tick` ends the game once its time is below zero with no selection pending.
    hd: bool = False
    selected: int = -1
    select_ms: int = 0
    fly_off_ms: int = 0
    fly_off_row: int = -1
    fly_on_ms: int = 0
    shown_ms: int = 0           # since the current labels started flying on
    effect_ms: int = 0
    scored: int = 0             # a score applied this tick (+1 / -1) not yet sounded; the session clears it

    HD_SELECT_MS, HD_FLY_OFF_MS, HD_FLY_ON_MS, HD_EFFECT_MS = 100, 500, 700, 1000

    def deal(self, random):
        """FUN_000af010: rejection sampling, then exactly twenty pair swaps."""
        if len(self.good) < 2 or len(self.bad) < 3:
            raise ValueError('Word game needs at least two good and three bad entries')
        first, second = random.below(len(self.good)), random.below(len(self.bad))
        third = random.below(len(self.bad))
        while third == second:
            third = random.below(len(self.bad))
        good_fourth = random.next() & 1 == 0
        pool, excluded = (self.good, (first,)) if good_fourth else (self.bad, (second, third))
        fourth = random.below(len(pool))
        while fourth in excluded:
            fourth = random.below(len(pool))
        self.options = [self.good[first], self.bad[second], self.bad[third], pool[fourth]]
        self.weights = [1, -1, -1, 1 if good_fourth else -1]
        for _ in range(20):
            a, b = random.below(4), random.below(4)
            self.options[a], self.options[b] = self.options[b], self.options[a]
            self.weights[a], self.weights[b] = self.weights[b], self.weights[a]
        self.refresh_remaining_ms = self.refresh_ms
        self.round += 1

    def pick(self, index, random):
        if type(index) is not int or not 0 <= index < 4:
            raise ValueError('Choose a word by its zero-based index (0–3)')
        if self.hd:
            # SHSMenu ignores taps while a selection is pending; handleMenuSelection while labels fly.
            if self.selected >= 0 or self.fly_off_ms or self.fly_on_ms:
                return False
            self.selected, self.select_ms = index, self.HD_SELECT_MS
            return False
        if self.entry_ms:
            return False  # Native transition input gate, FUN_000afee8.
        self.last_delta = self.weights[index]
        self.score = max(0, self.score + self.last_delta)
        self.deal(random)
        self.animation_ms = 200  # New labels slide in; native input stays live.
        return True

    def tick(self, elapsed_ms, random=None):
        if self.hd:
            return self._hd_tick(elapsed_ms, random)
        self.entry_ms = max(0, self.entry_ms - elapsed_ms)
        self.animation_ms = max(0, self.animation_ms - elapsed_ms)
        self.remaining_ms -= elapsed_ms
        self.refresh_remaining_ms -= elapsed_ms
        # FUN_000ae4f4 uses a strict negative comparison. The refresh counter
        # is stored/subtracted, but has no expiry action in this Android build.
        return self.duration_ms > 0 and self.remaining_ms < 0

    def _hd_tick(self, elapsed_ms, random):
        self.remaining_ms -= elapsed_ms
        self.refresh_remaining_ms -= elapsed_ms
        self.shown_ms = min(60_000, self.shown_ms + elapsed_ms)
        self.effect_ms = max(0, self.effect_ms - elapsed_ms)
        if self.selected >= 0:
            self.select_ms -= elapsed_ms
            if self.select_ms <= 0:
                self.last_delta = self.weights[self.selected]
                self.score = max(0, self.score + self.last_delta)
                self.scored, self.effect_ms = self.last_delta, self.HD_EFFECT_MS
                self.fly_off_row, self.selected, self.select_ms = self.selected, -1, 0
                self.fly_off_ms = self.HD_FLY_OFF_MS
        elif self.fly_off_ms:
            self.fly_off_ms = max(0, self.fly_off_ms - elapsed_ms)
            if not self.fly_off_ms:
                if random is None:
                    raise ValueError('The HD word game deals new labels and needs the random generator')
                self.deal(random)
                self.fly_off_row, self.fly_on_ms, self.shown_ms = -1, self.HD_FLY_ON_MS, 0
        elif self.fly_on_ms:
            self.fly_on_ms = max(0, self.fly_on_ms - elapsed_ms)
        return self.duration_ms > 0 and self.remaining_ms < 0 and self.selected < 0

    def validate(self):
        if (len(self.good) < 2 or len(self.bad) < 3 or self.duration_ms <= 0
                or self.duration_ms > 32767 or not -32768 <= self.refresh_ms <= 32767
                or not (-self.HD_SELECT_MS if self.hd else 0) <= self.remaining_ms <= self.duration_ms
                or not self.refresh_ms - self.duration_ms <= self.refresh_remaining_ms <= self.refresh_ms
                or len(self.options) != 4 or len(self.weights) != 4
                or sum(w == 1 for w in self.weights) not in (1, 2)
                or any(w not in (-1, 1) for w in self.weights)
                or any(s not in (self.good if w == 1 else self.bad)
                       for s, w in zip(self.options, self.weights))
                or self.round < 1 or not 0 <= self.score <= self.round - (0 if self.hd else 1)
                or not 0 <= self.entry_ms <= 400 or not 0 <= self.animation_ms <= 200
                or self.last_delta not in (-1, 0, 1)
                or not -1 <= self.selected < 4 or not 0 <= self.select_ms <= self.HD_SELECT_MS
                or not 0 <= self.fly_off_ms <= self.HD_FLY_OFF_MS or not -1 <= self.fly_off_row < 4
                or not 0 <= self.fly_on_ms <= self.HD_FLY_ON_MS or not 0 <= self.shown_ms <= 60_000
                or not 0 <= self.effect_ms <= self.HD_EFFECT_MS or self.scored not in (-1, 0, 1)
                or not self.hd and (self.selected, self.select_ms, self.fly_off_ms, self.fly_on_ms,
                                    self.effect_ms, self.scored) != (-1, 0, 0, 0, 0, 0)):
            raise ValueError('Invalid saved word game')
