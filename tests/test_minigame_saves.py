"""Every translated minigame's state through the save loader at every frame, from its opening to its end (owner,
2026-11-16: Diss Practice's arm at rest held -1 in a float field, so the undo save taken as it came up wouldn't load).

The loader checks each saved field against its annotation exactly (runtime._typed_value), so a field that can hold a
whole number or a fraction must say so. Each game plays here with uneven whole-millisecond frames, as the player's are,
and the player's inputs; its state, JSON round-tripped, must come back equal at every frame. New Rules' arena and SHS's
own games are played through real episodes by the probe in this suite's place (playthrough bots), and by their own tests."""
from dataclasses import asdict
import json
import random
import unittest

from exp_runtime.brew_catch import ORBIT, CatchGame
from exp_runtime.runtime import _typed_value
from exp_runtime.shs11_games import MemoryGame, ReflexGame
from exp_runtime.x360_battle import DissBattle
from exp_runtime.x360_diss import DissPractice
from exp_runtime.x360_games import LeashGame, SlotMachine
from exp_runtime.x360_puzzle import JewelPuzzle

FRAMES = (1, 16, 17, 33, 50, 250)       # what the player's clock gives: whole ms, a 250 ms cap after a stall


class Rng:
    """Every game's randomness: `below` (the X360's, '11's, the catch game's) and `next`."""

    def __init__(self, seed):
        self.random = random.Random(seed)

    def below(self, bound):
        return self.random.randrange(bound)

    def next(self):
        return self.random.getrandbits(31)


def ticks(game, rng):
    """The game's own tick: some take the randomness, the X360 slot machine and leash don't."""
    if isinstance(game, (SlotMachine, LeashGame)):
        return lambda ms: game.tick(ms)
    return lambda ms: game.tick(ms, rng)


class MinigameSaveTests(unittest.TestCase):
    def play(self, game, act, frames=6000, seed=1):
        """`act(game, frame, choice)`: the player's inputs this frame. Until the game finishes (tick returns True)."""
        kind, rng, choice = type(game), Rng(seed), random.Random(seed + 100)
        tick = ticks(game, rng)
        for frame in range(frames):
            saved = json.loads(json.dumps(asdict(game)))
            self.assertEqual(_typed_value(saved, kind), game, f'{kind.__name__} at frame {frame}, {getattr(game, "phase", "")}')
            act(game, frame, choice)
            if tick(FRAMES[choice.randrange(len(FRAMES))]):
                return
        self.fail(f'{kind.__name__} never finished: at {getattr(game, "phase", "")}')

    def test_diss_practice(self):
        self.play(DissPractice.opened(True), lambda game, frame, choice: choice.random() < .1 and game.press())

    def test_diss_battle(self):
        rounds = [['crash', 'trash', 'chatter', 'ride', 'rat'], ['rude', 'lewd', 'crook', 'socks', 'store']]
        for tutorial in (True, False):
            with self.subTest(tutorial=tutorial):
                self.play(DissBattle.opened(rounds, bonus=2, tutorial=tutorial),
                          lambda game, frame, choice: choice.random() < .1 and game.press())

    def test_slot_machine(self):
        self.play(SlotMachine(), lambda game, frame, choice: choice.random() < .15 and game.press())

    def test_leash_game(self):
        def act(game, frame, choice):
            if choice.random() < .05:
                game.press()
            if choice.random() < .3:
                game.shake(choice.choice(('left', 'right', 'up', 'down')))
        self.play(LeashGame(swap_ms=3000), act)

    def test_jewel_puzzle(self):
        def act(game, frame, choice):
            roll = choice.random()
            if roll < .05:
                game.press()
            elif roll < .1:
                game.release()
            elif roll < .3:
                game.move(choice.choice(('up', 'down', 'left', 'right')))
            elif roll < .35:
                game.grab(choice.randrange(1, 9), choice.randrange(1, 9))
            elif roll < .4:
                game.drag(choice.randrange(1, 9), choice.randrange(1, 9))
            elif roll < .45:
                game.let_go()
        self.play(JewelPuzzle.dealt(Rng(3)), act, frames=20000)

    def test_shs11_memory(self):
        rounds = [['I wish I was an elf!', 'ELF', 20, 10, 600, 4000], ['Cats!', 'CAT', 20, 10, 600, 4000]]
        for tutorial in (True, False):
            with self.subTest(tutorial=tutorial):
                self.play(MemoryGame.opened(rounds, 60, 300, tutorial=tutorial),
                          lambda game, frame, choice: choice.random() < .2 and game.press(choice.choice((None, *range(16)))))

    def test_shs11_reflex(self):
        row = [5, 10, 20, 5, 13, 3, 8, 25, 40, 20, 15, 300, 2100]
        for tutorial in (True, False):
            with self.subTest(tutorial=tutorial):
                self.play(ReflexGame.opened([row], 60, 350, tutorial=tutorial),
                          lambda game, frame, choice: choice.random() < .2 and game.press(choice.choice((None, *range(9)))))

    def test_brew_catch(self):
        sizes = {133: (29, 26), 151: (30, 30), 152: (30, 30)}
        game = CatchGame.opened(ORBIT, 45, 350, 350, 50, 30, 0, 133, [(-2, 151, 20), (4, 152, 30)], sizes, Rng(5))
        self.play(game, lambda game, frame, choice: choice.random() < .1 and game.press())


if __name__ == '__main__':
    unittest.main()
