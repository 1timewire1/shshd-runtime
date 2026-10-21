"""An optional per-frame timing log, for finding where a real window's frames go (issue #2's follow-up).

Off unless the environment variable SHSHD_FRAME_LOG names a file. Each line is one frame of the application loop, as
CSV: when it ended (s since start), the loop's own frame interval and the wall time since the last frame (ms), the
time in the frame's render; within it, the present (fitting the canvas and its layers to the window), the backdrop
(the background and the art beside the frame), the side panels and the display flip; then the tick and the events
(ms), and where the app was (screen, menu stage, pending story action). Drawing is the render less the four parts.
Nothing is written when the variable is unset, and timing costs nothing then.
"""
from contextlib import contextmanager
import os
import time

TIMED = ('render', 'present', 'backdrop', 'panels', 'flip', 'tick', 'events')
COLUMNS = ('t_s', 'interval_ms', 'wall_ms', *(name + '_ms' for name in TIMED), 'screen', 'stage', 'pending')


class FrameLog:
    def __init__(self, path):
        self.file = open(path, 'w', encoding='utf-8', newline='\n')
        self.file.write(','.join(COLUMNS) + '\n')
        self.start = self.last = time.perf_counter()
        self.sections = {}
        self.frames = 0

    @contextmanager
    def section(self, name):
        began = time.perf_counter()
        try:
            yield
        finally:
            self.sections[name] = self.sections.get(name, 0.0) + time.perf_counter() - began

    def frame(self, interval_ms, screen='', stage='', pending=''):
        now = time.perf_counter()
        timed = ','.join(f'{self.sections.get(name, 0.0) * 1000:.2f}' for name in TIMED)
        self.file.write(f'{now - self.start:.3f},{interval_ms},{(now - self.last) * 1000:.2f},{timed},'
                        f'{screen},{stage},{pending}\n')
        self.last, self.sections = now, {}
        self.frames += 1
        if self.frames % 60 == 0:
            self.file.flush()

    def close(self):
        self.file.close()


LOG = FrameLog(os.environ['SHSHD_FRAME_LOG']) if os.environ.get('SHSHD_FRAME_LOG') else None


@contextmanager
def _nothing():
    yield


def section(name):
    """Time a part of the current frame (a no-op without the log)."""
    return LOG.section(name) if LOG is not None else _nothing()
