"""Cause of Death 1.4.7's store listing (`Documents/mtxprods`), for the episode info card (this fork).

The free edition caches EA's MTX store catalogue in its Documents folder: an NSKeyedArchiver plist whose root array
holds an `EAMTX_UserInfo` record, a dictionary of `EAMTX_MTXProduct` records keyed by sell id, and two id lists. It is
downloaded from EA's server at run time, not shipped in the IPA, so only a player with a device backup has one.

* **The user record** carries device and account identifiers, a push token and analytics events. It is personal data
  and is never read past finding the products: `read_store` keeps the products only.
* **A product** has `title`, `desc` (store copy, English), `releaseDate` (NSDate, the store upload), `itemPrice`,
  `currency`, `localCurrency`, `freeItem` (the Now Airing copies are free), `version`, `packSize`, `sellId`,
  `prodIdentifier`, constant `consumable` / `downloadable` / `category` / `itemNew`, `granted` (owned on that device;
  dropped as the player's own) and `binPack`, a ZIP of `pack.info` and `contents.bin`.
* **`contents.bin`** (read here to the last byte): `DownloadContents`, u16 4, the internal name, an i32 and a u16 of
  unknown use, five categories, then u16 files, each a filename, u16 pack, u16 episode and five titles. Strings are
  u16-length UTF-8. All five language slots hold English in every product of the owner's 1.4.7 (267).

What is kept is every product field but `granted`, `binPack` byte for byte (base64), and its parsed contents, so a
later feature (splitting the Volume bundles into chapters) can use the chapters' own entries. legacy/findings.md has
the coverage (73 of the owner's 74 episodes; 184 of docs/COD_RELEASE_DATES.md's 186 rows).
"""
import base64
from io import BytesIO
import json
import plistlib
import re
import struct
from zipfile import BadZipFile, ZipFile

from ..exp import ContentError

STORE_FORMAT = 'cod-mtxprods-products'
STORE_VERSION = 1
MAX_STORE_BYTES = 16 * 1024 * 1024
MAX_PRODUCTS = 5000
DROPPED_FIELDS = ('$class', 'granted')
# Volume One is the base game, never a store product. Its description is the App Store listing's, supplied by the
# owner (2026-10-15), and shown only when a store listing was imported, like every other description; price free.
VOLUME_ONE_DESCRIPTION = (
    'In Volume One, play as Detective Mal Fallon and Special Agent Natara Williams on the trail of a terrifying killer '
    'known as "The Maskmaker." Gather evidence, ask hard questions, and make smart decisions... or else. From the '
    'shocking opening, the storyline grips you and doesn\'t let go. Chapter by chapter the plot unfolds. It\'s a '
    'virtual page turner! But remember, how the case ends depends on the choices YOU make. You\'ll find out who did '
    'it...  or you might be done in yourself. Play again and again to see all the twists and turns the investigation '
    'can take.')
VARIANT_SUFFIX = re.compile(r'(_now_airing_only|_na|_od|_airing)$')


def file_stem(filename):
    """A store or library filename without `.exp` and the store's Now Airing / On Demand suffixes, casefolded."""
    stem = str(filename).rsplit('/', 1)[-1].casefold().removesuffix('.exp')
    return VARIANT_SUFFIX.sub('', stem)


class _Reader:
    def __init__(self, data):
        self.data, self.position = data, 0

    def take(self, count):
        end = self.position + count
        if end > len(self.data):
            raise ContentError('Truncated store product contents')
        value, self.position = self.data[self.position:end], end
        return value

    def u16(self):
        return struct.unpack('>H', self.take(2))[0]

    def i32(self):
        return struct.unpack('>i', self.take(4))[0]

    def string(self):
        raw = self.take(self.u16())
        try:
            return raw.decode('utf-8')
        except UnicodeDecodeError:
            return raw.decode('latin-1')


def read_contents(data):
    """A product's `contents.bin` -> {name, unknown, categories, files: [{file, pack, episode, titles}]}."""
    reader = _Reader(data)
    if reader.take(16) != b'DownloadContents' or reader.u16() != 4:
        raise ContentError('Unsupported store product contents')
    name = reader.string()
    unknown = [reader.i32(), reader.u16()]
    categories = [reader.string() for _ in range(5)]
    files = []
    for _ in range(reader.u16()):
        filename = reader.string()
        pack, episode = reader.u16(), reader.u16()
        files.append(dict(file=filename, pack=pack, episode=episode, titles=[reader.string() for _ in range(5)]))
    if reader.position != len(data):
        raise ContentError('Unsupported trailing store product data')
    return dict(name=name, unknown=unknown, categories=categories, files=files)


def _resolve(objects, value, depth=0):
    if depth > 32:
        raise ContentError('Store listing nests too deeply')
    if isinstance(value, plistlib.UID):
        if value.data >= len(objects):
            raise ContentError('Invalid store listing reference')
        return _resolve(objects, objects[value.data], depth + 1)
    if isinstance(value, dict) and '$class' in value:
        cls = _resolve(objects, value['$class'], depth + 1)
        name = cls.get('$classname') if isinstance(cls, dict) else None
        if 'NS.keys' in value:
            return {_resolve(objects, k, depth + 1): _resolve(objects, v, depth + 1)
                    for k, v in zip(value['NS.keys'], value['NS.objects'])}
        if 'NS.objects' in value:
            return [_resolve(objects, v, depth + 1) for v in value['NS.objects']]
        for key in ('NS.string', 'NS.time', 'NS.data'):
            if key in value:
                return value[key]
        return {'$class': name, **{k: v for k, v in value.items() if k != '$class'}}
    if value == '$null':
        return None
    return value


def read_store(data):
    """`mtxprods` bytes -> the kept store listing (JSON-ready): products only, never the user record."""
    if len(data) > MAX_STORE_BYTES:
        raise ContentError('The store listing (mtxprods) is too large')
    try:
        archive = plistlib.loads(data)
        objects = archive['$objects']
        top = objects[archive['$top']['root'].data]
        entries = top['NS.objects']
    except (plistlib.InvalidFileException, ValueError, KeyError, TypeError, AttributeError, IndexError) as error:
        raise ContentError('Not a Cause of Death store listing (mtxprods)') from error
    products = {}
    for entry in entries:
        resolved = objects[entry.data] if isinstance(entry, plistlib.UID) and entry.data < len(objects) else None
        if not (isinstance(resolved, dict) and 'NS.keys' in resolved):
            continue                       # the user record and the id lists
        table = _resolve(objects, entry)
        for sell, product in table.items():
            if not (isinstance(product, dict) and product.get('$class') == 'EAMTX_MTXProduct'):
                continue
            # Resolve the product's own fields (its dict above kept them as references).
            fields = {k: _resolve(objects, v) for k, v in product.items() if k not in DROPPED_FIELDS}
            pack = fields.pop('binPack', None)
            if not isinstance(pack, bytes):
                raise ContentError(f'Store product {sell} has no contents')
            try:
                with ZipFile(BytesIO(pack)) as package:
                    contents = read_contents(package.read('contents.bin'))
            except (BadZipFile, KeyError) as error:
                raise ContentError(f'Store product {sell} has unreadable contents') from error
            products[str(sell)] = dict(fields, binPack=base64.b64encode(pack).decode('ascii'), contents=contents)
            if len(products) > MAX_PRODUCTS:
                raise ContentError('The store listing (mtxprods) has too many products')
    if not products:
        raise ContentError('The store listing (mtxprods) holds no products')
    return dict(format=STORE_FORMAT, version=STORE_VERSION, products=products)


def store_bytes(store):
    """The kept listing as stable JSON bytes (hashed and stored in the library's content folder)."""
    return (json.dumps(store, indent=1, ensure_ascii=False, sort_keys=True) + '\n').encode('utf-8')


class Store:
    """The kept listing, indexed for the info card: one store product per episode file."""

    def __init__(self, data):
        if not (isinstance(data, dict) and data.get('format') == STORE_FORMAT and data.get('version') == STORE_VERSION
                and isinstance(data.get('products'), dict)):
            raise ContentError('Unsupported stored store listing')
        self.products = data['products']
        self.by_stem = {}
        for product in self.products.values():
            files = product['contents']['files']
            if len(files) == 1:            # combos and bundles of several files describe a set, not an episode
                self.by_stem.setdefault(file_stem(files[0]['file']), []).append(product)

    @staticmethod
    def _preference(product):
        # The On Demand (paid) copy first, then text without the store's lost characters, then the earliest.
        return (product.get('freeItem') == '1', '�' in product.get('desc', ''), product.get('releaseDate') or 0)

    def product(self, record):
        """The store product for a library episode (by its filename or an alias), or None."""
        for name in (record.get('name', ''), *record.get('aliases', [])):
            matches = self.by_stem.get(file_stem(name))
            if matches:
                return min(matches, key=self._preference)
        return None


def price_label(product):
    """'Free' or the store's own price, e.g. '$0.99'."""
    try:
        amount = float(product.get('itemPrice') or 0)
    except ValueError:
        return None
    return 'Free' if amount == 0 else f"{product.get('currency') or '$'}{amount:.2f}"
