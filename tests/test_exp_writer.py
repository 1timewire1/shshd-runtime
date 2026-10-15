"""Native writer tests independent of the editor, engine and game assets."""
import unittest

from exp_runtime.formats import ContentError, ExpArchive, Metadata, encode_exp


class ExpWriterTests(unittest.TestCase):
    def test_metadata_and_all_resource_ids_round_trip_deterministically(self):
        meta = Metadata(65535, 0, ('New episode', 'École', 'Scuola', 'Schule', 'Escuela'))
        records = {65535: b'last', 0: b'', 1: meta.to_bytes(), 26000: bytes(range(256))}
        encoded = encode_exp(records)
        archive = ExpArchive(encoded)
        self.assertEqual(archive.metadata(), meta)
        self.assertEqual({key: archive.read(key) for key in archive.entries}, records)
        self.assertEqual(encoded, encode_exp(dict(reversed(list(records.items())))))

    def test_invalid_ids_sizes_and_metadata_are_rejected(self):
        for records in ({}, {-1: b''}, {65536: b''}, {True: b''}, {'1': b''}, {1: 'not bytes'}):
            with self.subTest(records=records), self.assertRaises(ContentError):
                encode_exp(records)
        for meta in (Metadata(-1, 0, ('x',) * 5), Metadata(True, 0, ('x',) * 5),
                     Metadata(0, 0, ('x',)), Metadata(0, 0, ('é' * 32768,) * 5)):
            with self.assertRaises(ContentError):
                meta.to_bytes()
