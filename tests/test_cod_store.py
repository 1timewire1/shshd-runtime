"""Cause of Death 1.4.7's store listing (mtxprods): what is kept, how it is imported, and the episode info card."""
from io import BytesIO
import json
import os
import plistlib
import struct
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from exp_runtime.cod.store import (Store, VOLUME_ONE_DESCRIPTION, file_stem, price_label, read_contents,
                                   read_store)
from exp_runtime.content import ContentError, ContentLibrary, import_game
from exp_runtime.staged_import import _member_path
from test_content import archive, metadata
from test_games import make_cod_ipa
from test_vm import program

UID = plistlib.UID


def contents_bin(name, category, files):
    def string(text):
        raw = text.encode('utf-8')
        return struct.pack('>H', len(raw)) + raw
    data = b'DownloadContents' + struct.pack('>H', 4) + string(name) + struct.pack('>iH', 9, 26)
    data += b''.join(string(category) for _ in range(5)) + struct.pack('>H', len(files))
    for filename, pack, episode, title in files:
        data += string(filename) + struct.pack('>HH', pack, episode) + b''.join(string(title) for _ in range(5))
    return data


def mtxprods(products):
    """An authored NSKeyedArchiver store listing: a user record, then `products` (sell id -> fields), then ids."""
    objects = ['$null']

    def add(value):
        objects.append(value)
        return UID(len(objects) - 1)

    def cls(name):
        return add({'$classname': name, '$classes': [name, 'NSObject']})

    def dictionary(table):
        return add({'NS.keys': [add(k) for k in table], 'NS.objects': list(table.values()),
                    '$class': cls('NSMutableDictionary')})

    user = add({'$class': cls('EAMTX_UserInfo'), 'hwid': add('device-secret'), 'devToken': add('push-secret')})
    table = {}
    for sell, fields in products.items():
        pack = BytesIO()
        with ZipFile(pack, 'w') as package:
            package.writestr('pack.info', 'version: 1.0.0\nlanguage: en\n')
            package.writestr('contents.bin', contents_bin(*fields.pop('contents')))
        record = {'$class': cls('EAMTX_MTXProduct'),
                  'binPack': add({'NS.data': pack.getvalue(), '$class': cls('NSMutableData')}),
                  'releaseDate': add({'NS.time': fields.pop('date', 300000000.0), '$class': cls('NSDate')}),
                  'granted': add('1'), 'currency': add('$'), 'sellId': add(sell)}
        record.update({key: add(value) for key, value in fields.items()})
        table[sell] = add(record)
    root = add({'NS.objects': [user, dictionary(table), dictionary({'new': add({'NS.objects': [],
                                                                               '$class': cls('NSMutableArray')})})],
                '$class': cls('NSMutableArray')})
    return plistlib.dumps({'$archiver': 'NSKeyedArchiver', '$version': 100000, '$top': {'root': root},
                           '$objects': objects}, fmt=plistlib.FMT_BINARY)


PRODUCTS = {
    '1': dict(title='A Case', desc='The On Demand text.', itemPrice='0.990000', freeItem='0',
              contents=('A Case', 'SIDE STORIES', [('Case.exp', 20000, 1, 'Side Stories: A Case')])),
    '2': dict(title='A Case', desc='The Now Airing text.', itemPrice='0.000000', freeItem='1', date=200000000.0,
              contents=('A Case NOW AIRING', 'SIDE STORIES', [('Case_NA.exp', 20000, 1, 'Side Stories: A Case')])),
    '3': dict(title='Bundle', desc='Two cases.', itemPrice='1.990000', freeItem='0',
              contents=('Bundle', 'SIDE STORIES', [('Case.exp', 20000, 1, 'A'), ('Other.exp', 20000, 2, 'B')])),
    '4': dict(title='Special', desc='\n\nOnly ever free.', itemPrice='0.000000', freeItem='1',
              contents=('Special', 'Now Airing Special', [('Special.exp', 1001, 1, 'Now Airing Special')])),
}


def products():
    return {sell: dict(fields) for sell, fields in PRODUCTS.items()}


class StoreListingTests(unittest.TestCase):
    def test_only_the_products_are_kept_never_the_user_record(self):
        store = read_store(mtxprods(products()))
        kept = json.dumps(store)
        for secret in ('device-secret', 'push-secret', 'hwid', 'devToken', 'granted', 'EAMTX_UserInfo'):
            self.assertNotIn(secret, kept)
        self.assertEqual(sorted(store['products']), ['1', '2', '3', '4'])
        product = store['products']['1']
        self.assertEqual((product['desc'], product['itemPrice'], product['releaseDate']),
                         ('The On Demand text.', '0.990000', 300000000.0))
        self.assertEqual(product['contents']['files'][0]['file'], 'Case.exp')
        with ZipFile(BytesIO(__import__('base64').b64decode(product['binPack']))) as package:   # byte for byte
            self.assertIn('contents.bin', package.namelist())

    def test_contents_must_parse_to_the_last_byte(self):
        data = contents_bin('A', 'B', [('A.exp', 1, 2, 'T')])
        self.assertEqual(read_contents(data)['files'][0]['episode'], 2)
        for bad in (data + b'\0', data[:-1], b'X' + data[1:]):
            with self.assertRaises(ContentError):
                read_contents(bad)
        with self.assertRaises(ContentError):
            read_store(b'not a plist')

    def test_an_episode_takes_its_on_demand_product_else_its_only_one(self):
        store = Store(read_store(mtxprods(products())))
        paid = store.product({'name': 'Case.exp'})
        self.assertEqual((paid['desc'], price_label(paid)), ('The On Demand text.', '$0.99'))
        self.assertEqual(store.product({'name': 'case_na.exp'})['sellId'], '1')        # the variant suffix folds
        special = store.product({'name': 'x.exp', 'aliases': ['Special.exp']})
        self.assertEqual(price_label(special), 'Free')
        self.assertIsNone(store.product({'name': 'Other.exp'}))           # only ever in a bundle of several files
        self.assertEqual(file_stem('Volume_13_Interlude_Airing.exp'), 'volume_13_interlude')


class StoreImportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        make_cod_ipa(self.root / 'cod.ipa', archive({1: metadata('Volume One'), 25001: program(0x33).to_bytes()}),
                     free=True)
        self.episodes = self.root / 'cod_episodes'
        self.episodes.mkdir()
        (self.episodes / 'Case.exp').write_bytes(archive({1: metadata('Side Stories: A Case'),
                                                         25001: program(0x33).to_bytes()}))
        (self.episodes / 'Special.exp').write_bytes(archive({1: metadata('Now Airing Special'),
                                                            25001: program(0x33).to_bytes()}))

    def test_import_keeps_the_listing_and_add_episodes_can_supply_it_later(self):
        (self.episodes / 'mtxprods').write_bytes(mtxprods(products()))
        manifest = import_game(self.root / 'cod.ipa', [self.episodes], self.root / 'with', game='cod')
        self.assertTrue((self.root / 'with' / manifest['store']['file']).is_file())
        with ContentLibrary(self.root / 'with') as library:
            self.assertEqual(len(library.store_listing()['products']), 4)
        (self.episodes / 'mtxprods').unlink()
        import_game(self.root / 'cod.ipa', [self.episodes], self.root / 'without', game='cod')
        with ContentLibrary(self.root / 'without') as library:
            self.assertIsNone(library.store_listing())
            (self.root / 'mtxprods').write_bytes(mtxprods(products()))
            self.assertEqual(library.add_episodes([self.root / 'mtxprods']), 0)     # no episodes, just the listing
            self.assertEqual(len(library.store_listing()['products']), 4)
        with ContentLibrary(self.root / 'without') as reopened:
            self.assertIsNotNone(reopened.store_listing())

    def test_a_bulk_archive_carries_the_listing(self):
        self.assertEqual(_member_path('cod_episodes/mtxprods'), 'cod_episodes/mtxprods')
        self.assertEqual(_member_path('Games/MTXPRODS'), 'Games/MTXPRODS')

    def test_the_info_card_needs_the_listing(self):
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        from exp_runtime.episode_picker import PickerModel
        import_game(self.root / 'cod.ipa', [self.episodes], self.root / 'bare', game='cod')
        (self.episodes / 'mtxprods').write_bytes(mtxprods(products()))
        import_game(self.root / 'cod.ipa', [self.episodes], self.root / 'store', game='cod')
        with ContentLibrary(self.root / 'bare') as library:
            model = PickerModel(library)
            self.assertFalse(any(model.has_info(r) for r in model.records))
        with ContentLibrary(self.root / 'store') as library:
            model = PickerModel(library)
            by_name = {r['name']: r for r in model.records}
            info = model.info(by_name['Case.exp'])
            self.assertEqual((info.description, info.price), ('The On Demand text.', '$0.99'))
            self.assertEqual(model.info(by_name['Special.exp']).description, 'Only ever free.')
            builtin = next(r for r in model.records if r.get('builtin') == 'volume-one')
            self.assertEqual((model.info(builtin).description, model.info(builtin).price),
                             (VOLUME_ONE_DESCRIPTION, 'Free'))


if __name__ == '__main__':
    unittest.main()
