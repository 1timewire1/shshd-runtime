"""The optional frame-time log (frame_log.py, SHSHD_FRAME_LOG)."""
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from exp_runtime import frame_log


class FrameLogTests(unittest.TestCase):
    def test_each_frame_is_one_csv_line_of_its_timed_parts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'frames.csv'
            log = frame_log.FrameLog(path)
            with log.section('render'):
                with log.section('present'):
                    time.sleep(.002)
            log.frame(16, 'game', 'main', 'dialogue')
            log.frame(17)                                   # a frame with nothing timed
            log.close()
            header, first, second = path.read_text(encoding='utf-8').splitlines()
        self.assertEqual(header.split(','), list(frame_log.COLUMNS))
        row = dict(zip(frame_log.COLUMNS, first.split(',')))
        self.assertEqual((row['interval_ms'], row['screen'], row['stage'], row['pending']), ('16', 'game', 'main', 'dialogue'))
        self.assertGreaterEqual(float(row['render_ms']), float(row['present_ms']))
        self.assertGreater(float(row['present_ms']), 1)
        self.assertEqual(float(dict(zip(frame_log.COLUMNS, second.split(',')))['render_ms']), 0)   # sections reset

    def test_without_the_variable_sections_do_nothing(self):
        with patch.object(frame_log, 'LOG', None):
            with frame_log.section('render'):
                pass                                        # no log, no error


if __name__ == '__main__':
    unittest.main()
