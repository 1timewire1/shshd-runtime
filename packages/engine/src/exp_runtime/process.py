"""Native application lifetimes shared by successive episode sessions."""
from .speaker_names import SpeakerNames


class RuntimeProcess:
    """Own live streams without module globals or cross-game contamination.

    Native episode teardown retains the random generators and font objects.
    An explicit save restore replaces their state, preserving deterministic
    continuation. Headless sessions remain isolated unless attached here.
    """
    def __init__(self):
        self.current = None

    def attach(self, session, *, restored=False):
        previous = self.current.engine if self.current is not None else None
        engine = session.engine
        if previous is not None and previous.game_key != engine.game_key:
            raise ValueError('An application process cannot mix game adapters')
        if previous is not None and not restored:
            engine.random, engine.random48 = previous.random, previous.random48
            engine.speaker_names = SpeakerNames(fonts=previous.speaker_names.fonts)
            engine.text_history = previous.text_history
            old, new = previous.scene_transition, engine.scene_transition
            if old is not None and new is not None and hasattr(old, 'random_state'):
                new.random_state = old.random_state
        self.current = session
        session.process = self
        return session
