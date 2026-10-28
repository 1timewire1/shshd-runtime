"""Play an episode through again and again, taking different choices and mini-game outcomes each time, so the
Decision Tree fills in with every scene the story can reach (and each scene's warp save is written).

A playthrough starts from the beginning like a player's and answers every screen headlessly. At each decision --
a choice (letting a timed one run out counts as an alternative), the character picker, the football game, the word game and the grid game -- it takes the alternative
tried least often at that place in the story (ties are broken by a seeded random draw). The tree file and the
per-scene saves land in the library, exactly as when the game is played by hand.

Mini-games are decided rather than played, except the word game, which is played (picking right or wrong words):
football finishes as a win, a tie or a loss, the grid game as a pass or a fail. Their scripts see the same result
values as after a real game.
"""
from dataclasses import dataclass, field
import random

from .content import ContentLibrary
from .engine import POLL_WAIT_MS
from .runtime import Session

MAX_ACTIONS = 30_000            # a playthrough that answers more screens than this is stuck
FOOTBALL_OUTCOMES = {'win': (14, 7), 'tie': (7, 7), 'loss': (7, 14)}
WORD_GAME_PICKS = 12


@dataclass
class Playthrough:
    number: int
    decisions: list = field(default_factory=list)     # (place, kind, alternative)
    new_nodes: int = 0
    new_alternatives: int = 0
    screens: int = 0
    finished: bool = False
    error: str = ''


class Explorer:
    def __init__(self, resources, *, seed=0, ephemeral=False):
        self.resources = resources
        self.random = random.Random(seed)
        self.ephemeral = ephemeral
        self.taken = {}                 # place -> {alternative: times taken}
        self.offered = {}               # place -> every alternative seen there
        self.kinds = {}

    # -- decisions -------------------------------------------------------------------------------------------

    @staticmethod
    def place(session):
        current = session.engine.dt_view.current
        return (current.serial if current is not None else 0, session.scene, session.pending.request.pc)

    def alternatives(self, session):
        action = session.pending
        if action.name == 'choice':
            # Letting a timed choice run out is a decision of its own: CoD's SS12 has a lone "Shoot!" whose only
            # way forward is holding fire until the timer ends.
            timeout = ['timeout'] if action.details['timeout_ms'] else []
            return [index for index, enabled in enumerate(action.details['enabled']) if enabled] + timeout
        if action.name == 'character_picker':
            return list(range(len(session.engine.character_picker.characters)))
        if action.name == 'football':
            return list(FOOTBALL_OUTCOMES)
        if action.name == 'word_game':
            return ['good', 'none']
        if action.name == 'word_grid':
            return ['pass', 'fail']
        return None

    def decide(self, session, playthrough):
        alternatives = self.alternatives(session)
        if alternatives is None:
            return None
        place = self.place(session)
        counts = self.taken.setdefault(place, {})
        self.kinds[place] = session.pending.name
        self.offered.setdefault(place, set()).update(alternatives)
        fewest = min(counts.get(alternative, 0) for alternative in alternatives)
        choice = self.random.choice([a for a in alternatives if counts.get(a, 0) == fewest])
        if choice not in counts:
            playthrough.new_alternatives += 1
        counts[choice] = counts.get(choice, 0) + 1
        playthrough.decisions.append((place, session.pending.name, choice))
        return choice

    # -- answering screens -----------------------------------------------------------------------------------

    def act(self, session, playthrough):
        """Answer the pending screen once."""
        action = session.pending
        name = action.name
        if name == 'dialogue':
            if not session.engine.dialogue_animation.complete:
                session.answer()                     # the first tap finishes the reveal
                session.tick(2000)
            session.answer()
        elif name == 'vm_pause':
            session.answer()
        elif name == 'presentation':
            session.tick(4000)
            session.answer()
        elif name == 'message_panel':
            session.tick(5000)
            session.answer()
        elif name == 'loading':
            session.tick(3001)
        elif name == 'download_poll':
            session.tick(POLL_WAIT_MS)
        elif name == 'text_input':
            session.answer('Player')
        elif name == 'choice':
            if not getattr(session, 'choice_ready', True):
                # The menu ignores taps for its first 250 ms (Session.choice_ready, exp-runtime v0.6.0).
                session.tick(250 - session.engine.choice_ms)
                if session.pending is not action:
                    return
            decision = self.decide(session, playthrough)
            if decision == 'timeout':
                session.tick(action.details['timeout_ms'] + 1)
            else:
                session.answer(decision)
        elif name == 'character_picker':
            session.answer(self.decide(session, playthrough))
            session.answer(None)
        elif name == 'football':
            home, away = FOOTBALL_OUTCOMES[self.decide(session, playthrough)]
            session.engine.football_scores = [home, away]
            self.finish(session, 'football', home - away)
        elif name == 'word_grid':
            self.finish(session, 'word_grid', int(self.decide(session, playthrough) == 'pass'))
        elif name == 'word_game':
            self.play_word_game(session, self.decide(session, playthrough) == 'good')
        else:
            raise RuntimeError(f'Cannot answer the {name} screen')

    @staticmethod
    def finish(session, kind, result):
        """The end of a mini-game (`Session.tick`'s finishing branch) with the given result."""
        session.vm.resume(result)
        session.pending = None
        setattr(session.engine, kind, None)
        session.advance()

    @staticmethod
    def play_word_game(session, well):
        game = session.engine.word_game
        if game.hd:
            # The iOS action menu (SHS HD, CoD) runs in phases a tick at a time and ignores taps while labels fly, so
            # it is played frame by frame, tapping only while input is open.
            picks = 0
            while session.pending is not None and session.pending.name == 'word_game':
                game = session.engine.word_game
                if well and picks < WORD_GAME_PICKS and game.selected < 0 and not (game.fly_off_ms or game.fly_on_ms):
                    session.answer(game.weights.index(1))
                    picks += 1
                session.tick(20)
            return
        session.tick(game.entry_ms)
        for _ in range(WORD_GAME_PICKS if well else 0):
            game = session.engine.word_game
            index = game.weights.index(1)
            session.answer(index)
        game = session.engine.word_game
        session.tick(max(game.remaining_ms, 0) + 1)

    # -- playthroughs ----------------------------------------------------------------------------------------

    @staticmethod
    def ended(session):
        return session.episode_exited or session.pending.name == 'finished'

    def play(self, number, start_script=25001):
        session = Session(self.resources, start_script=start_script, ephemeral=self.ephemeral)
        session.durable = False
        session.advance()
        view = session.engine.dt_view
        before = len(list(view.nodes()))
        playthrough = Playthrough(number)
        try:
            while not self.ended(session) and playthrough.screens < MAX_ACTIONS:
                self.act(session, playthrough)
                playthrough.screens += 1
            playthrough.finished = self.ended(session)
        except Exception as error:                       # the tree so far is kept; the run is reported
            playthrough.error = f'{type(error).__name__}: {error}'
        playthrough.new_nodes = len(list(view.nodes())) - before
        self.view = view
        return playthrough

    def unexplored(self):
        """Places where some alternative has still not been taken."""
        return {place: sorted(alternatives - set(self.taken.get(place, ())), key=str)
                for place, alternatives in self.offered.items() if alternatives - set(self.taken.get(place, ()))}

    def explore(self, runs=60, patience=6, report=None, start_script=25001):
        """Play up to `runs` times, stopping early after `patience` runs in a row that add no scene and no untried
        alternative while nothing is left untried. Returns the playthroughs."""
        results, quiet = [], 0
        for number in range(1, runs + 1):
            playthrough = self.play(number, start_script)
            results.append(playthrough)
            if report:
                report(playthrough, self)
            if playthrough.error:
                break
            quiet = 0 if playthrough.new_nodes or playthrough.new_alternatives else quiet + 1
            if quiet >= patience and not self.unexplored():
                break
        return results


def explore_library(directory, episode=None, *, runs=60, seed=0, reset=False, report=None):
    """Explore the built-in episode (or the one with this id) of a library; returns (explorer, playthroughs)."""
    with ContentLibrary(directory) as library:
        library.ensure_builtin_episodes()
        record = next(e for e in library.episodes if (e['id'] == episode if episode else e.get('builtin')))
        resources = library.open_episode(record['id'])
        if reset:
            tree, saves = Session.tree_files(resources)
            tree.unlink(missing_ok=True)
            for path in saves.glob('*.json.gz'):
                path.unlink()
        explorer = Explorer(resources, seed=seed)
        return explorer, explorer.explore(runs, report=report)
