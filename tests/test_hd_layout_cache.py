"""HD layout bank caching: each HdLayouts parses its bank once, however instances interleave (the frame log's re-parse)."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from exp_runtime import hd_layout


class BankCacheTests(unittest.TestCase):
    def test_interleaved_instances_each_parse_once(self):
        library = SimpleNamespace(hd_raw_resource=lambda resource_id: b'bank')
        first, second = hd_layout.HdLayouts(library), hd_layout.HdLayouts(library)
        with patch.object(hd_layout.LayoutBank, 'parse', side_effect=lambda data: object()) as parse:
            for _ in range(5):
                a, b = first.bank(), second.bank()
        self.assertEqual(parse.call_count, 2)
        self.assertIs(first.bank(), a)
        self.assertIsNot(a, b)

    def test_no_hd_bundle_is_remembered_as_none(self):
        calls = []
        library = SimpleNamespace(hd_raw_resource=lambda resource_id: calls.append(resource_id))
        layouts = hd_layout.HdLayouts(library)
        self.assertIsNone(layouts.bank())
        self.assertIsNone(layouts.bank())
        self.assertEqual(len(calls), 1)


if __name__ == '__main__':
    unittest.main()
