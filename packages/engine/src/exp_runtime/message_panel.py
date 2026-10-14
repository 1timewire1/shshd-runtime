"""Service 33's raw-text message panel and native acknowledgement gate."""
from dataclasses import dataclass

from .vm import VMError


@dataclass
class MessagePanel:
    title: str
    text: str
    argument: int
    elapsed_ms: int = 0

    @property
    def ready(self):
        return self.elapsed_ms == 1000

    @property
    def countdown(self):
        # FUN_000aca28 uses +900, rather than rounding up with +999.
        return (1000 - self.elapsed_ms + 900) // 1000

    def tick(self, elapsed_ms):
        self.elapsed_ms = min(1000, self.elapsed_ms + elapsed_ms)

    def validate(self):
        if (type(self.argument) is not int or not -32768 <= self.argument <= 32767
                or type(self.elapsed_ms) is not int or not 0 <= self.elapsed_ms <= 1000):
            raise VMError('Invalid message-panel argument or clock')
        for value in (self.title, self.text):
            if not isinstance(value, str) or '\0' in value:
                raise VMError('Invalid message-panel text')
            try:
                value.encode('latin-1')
            except UnicodeEncodeError:
                raise VMError('Message-panel text must be Latin-1') from None
