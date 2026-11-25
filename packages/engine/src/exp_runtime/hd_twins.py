"""Higher-density art for standard episodes, taken from the HD release of the same stories (prototype).

A standard episode's own art (resource ids from 26000 up) is the Android release's 1x drawings. The HD release of the same story
ships that art again, at 2x -- backgrounds as the same picture, character portraits redrawn -- under the same resource ids, because
the two releases run near-identical scripts. This module keeps a *twin store*: the standard asset's content fingerprint ->
the HD asset's bytes, gathered once from every standard/HD pair in the library (`build`), so that a standard episode whose own HD
release is not installed (or does not exist) still gets the HD version of any picture it shares with an episode that has one.

Modes (`ContentLibrary.hd_art_mode`, the `SHS_HD_ART` environment variable, or `hd_art` in player.json):
  'off'   -- nothing is substituted;
  'twins' -- a picture with an HD twin is served as the twin;
  'fill'  -- as 'twins', and every other picture of a standard episode is scaled to twice its size so the whole episode is drawn at
             the HD layout's density (the default: `content.py`'s own fallback and `menu.py`'s player-state default both use it).

Nothing here is bundled: the store is a file in the player's own library, made from the player's own episode files.
"""
from dataclasses import dataclass
import hashlib
import io
import json
import logging
import math
import struct
from pathlib import Path

from PIL import Image

DIRECTORY = 'hd_twins'
INDEX, PACK = 'index.json', 'pack.bin'
COVERAGE = 'coverage.json'      # how much of a standard episode's own art has an HD twin (tools/build_hd_coverage.py)
SOURCE = 'source.json'          # which shipped twin map last built the store (`build_from_map`)
EFFECTS = 'effects.json'        # tools/write_hd_twins.py: {standard: [HD fingerprint, effect]} of recreated pictures
PORTRAITS = 'portraits.json'    # tools/write_hd_twins.py: SD Portraits' tables, for export_hd_twin_map.py
MODES = ('off', 'twins', 'fill')
LOCAL_ART = 26000               # resource ids from here are the episode's own; below are the app's shared bank
RATIO = (1.6, 2.6)              # an HD twin is about twice the standard picture in each direction (HD pads its sprite sheets)
FLAT_CORRELATION_FLOOR = 0.3    # below this a same-shaped "twin" is unrelated content or a corrupt capture, not a match
BACKGROUND_RECOVERY_FLOOR = 0.9  # above this, an id-mismatched background pair is trusted as the same photo renumbered


def fingerprint(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()[:20]


def image_size(data: bytes):
    """(width, height) of a PNG or JPEG, or None."""
    if data[:8] == b'\x89PNG\r\n\x1a\n' and len(data) >= 24:
        return struct.unpack('>II', data[16:24])
    if data[:2] == b'\xff\xd8':
        position = 2
        while position + 9 < len(data):
            if data[position] != 0xff:
                position += 1
                continue
            marker = data[position + 1]
            if marker in (0xc0, 0xc1, 0xc2):
                height, width = struct.unpack('>HH', data[position + 5:position + 9])
                return width, height
            position += 2 + struct.unpack('>H', data[position + 2:position + 4])[0]
    return None


def is_twin(standard: bytes, hd: bytes) -> bool:
    """Whether `hd` can be the HD release of the picture `standard`: both images, about twice the size each way.
    Silent about *content* -- a picture's kind (a background must correlate; a redrawn portrait need not) is only
    known to the caller, which checks it separately; see `is_flat_capture`."""
    small, large = image_size(standard), image_size(hd)
    if not small or not large or min(small) < 8:
        return False
    return all(RATIO[0] <= big / little <= RATIO[1] for big, little in zip(large, small))


def is_upgraded(standard: bytes, hd: bytes) -> bool:
    """Whether `hd` is a real, meaningful upscale of `standard` in both directions -- looser than `is_twin`'s
    proportional 1.6-2.6x band, for a portrait whose identity is already confirmed some other way (a shared
    character name): a genuine HD redraw does not always keep the standard picture's aspect ratio (found in
    68_spring_Break's own "Angie", 128x128 -> 168x256 -- only the height comes close to doubling)."""
    small, large = image_size(standard), image_size(hd)
    if not small or not large or min(small) < 8:
        return False
    return all(1.2 <= big / little <= 4.0 for big, little in zip(large, small))


def is_flat_capture(standard: bytes, hd: bytes) -> bool:
    """True when `hd` is meant to be the very same photo as `standard` (a background) but does not correlate with
    it at all -- a 12_3_Howards_Last_Day HD background extracts as 960x1440 solid black, a truncated-JPEG artifact
    of the reference dump, not a real picture, and would otherwise pass every size check `is_twin` makes."""
    return correlation(standard, hd) < FLAT_CORRELATION_FLOOR


def correlation(data_a: bytes, data_b: bytes) -> float:
    """Pearson correlation of two pictures' color, alpha composited onto gray and shrunk to 24x24 first -- cheap
    and dependency-free, just discriminating enough to catch a picture unrelated to (or a flat wash next to) the
    other, not to judge a redrawn portrait."""
    def vector(data):
        with Image.open(io.BytesIO(data)) as source:
            image = source.convert('RGBA')
            flat = Image.new('RGB', image.size, (128, 128, 128))
            flat.paste(image, (0, 0), image)
            small = flat.resize((24, 24), Image.BILINEAR)
            return [float(value) for pixel in small.getdata() for value in pixel]
    try:
        a, b = vector(data_a), vector(data_b)
    except (OSError, ValueError):
        return 0.0
    mean_a, mean_b = sum(a) / len(a), sum(b) / len(b)
    centered_a = [v - mean_a for v in a]
    centered_b = [v - mean_b for v in b]
    denominator = math.sqrt(sum(x * x for x in centered_a) * sum(y * y for y in centered_b))
    if denominator <= 1e-6:
        # A flat wash has no variance to correlate against, so a real Pearson correlation is undefined -- but "the
        # same flat color both times" (a fade-to-black/white transition frame, seen in 10_1_300s_A_Crowd's and
        # 1_1_Magic_School's own #26055/#26001) is still a real match; a flat side next to a varied or
        # differently-colored one (a corrupt capture, see 12_3_Howards_Last_Day's black #26116) is not.
        return 1.0 if abs(mean_a - mean_b) < 8 else 0.0
    return sum(x * y for x, y in zip(centered_a, centered_b)) / denominator


def is_hd_size(size) -> bool:
    """Whether a picture is already HD: a background 700 or more wide (HD's are 768 / 960, the standard release's 320
    to 480), or a portrait 256 tall (HD redraws are 148 to 256 wide; standard portraits are at most 150 tall). Some
    standard files carry HD pictures: Set_12's pool (#26083) is 12_5_Swim_Team_Trip's own 960 x 1440 #26096."""
    if not size:
        return False
    width, height = size
    return width >= 700 or (width < 300 and height >= 256)


def upscale(data: bytes) -> bytes:
    """The picture at twice its size (Lanczos), as PNG; the original bytes when it cannot be read."""
    try:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as image:
            image = image.convert('RGBA')
            image = image.resize((image.width * 2, image.height * 2), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            image.save(out, 'PNG')
            return out.getvalue()
    except (ImportError, OSError, ValueError) as error:
        logging.debug('Cannot scale a picture: %s', error)
        return data


class TwinStore:
    """The library's twin store: `index.json` ({fingerprint: [offset, length, standard size, hd size]}) beside `pack.bin`."""

    def __init__(self, directory: Path):
        self.directory = Path(directory) / DIRECTORY
        self._index = None
        self._filled = {}
        self._coverage = None

    @property
    def index(self):
        if self._index is None:
            try:
                self._index = json.loads((self.directory / INDEX).read_text(encoding='utf-8'))
            except (OSError, ValueError):
                self._index = {}
        return self._index

    def __len__(self):
        return len(self.index)

    def twin(self, data: bytes):
        return self.twin_by_key(fingerprint(data))

    def twin_by_key(self, key: str):
        entry = self.index.get(key)
        if entry is None:
            return None
        try:
            with (self.directory / PACK).open('rb') as stream:
                stream.seek(entry[0])
                found = stream.read(entry[1])
        except OSError:
            return None
        return found if len(found) == entry[1] else None

    def art(self, data: bytes, mode: str) -> bytes:
        """What to serve for an episode-local picture of a standard episode."""
        if mode == 'off' or image_size(data) is None:
            return data
        found = self.twin(data)
        if found is not None:
            return found
        if mode != 'fill':
            return data
        return self.fill(data)

    def fill(self, data: bytes) -> bytes:
        """A standard picture at twice its size, so it is drawn at the HD layout's density (`art`'s 'fill' without the
        twin: SD Portraits keeps a standard episode's own portrait)."""
        if is_hd_size(image_size(data)):
            return data                             # an HD picture in a standard file is not doubled again
        key = fingerprint(data)
        if key not in self._filled:
            if len(self._filled) > 256:
                self._filled.clear()
            self._filled[key] = upscale(data)
        return self._filled[key]

    def write(self, entries: dict) -> None:
        """Replace the store with `entries` ({fingerprint: (standard bytes, hd bytes)})."""
        self.directory.mkdir(parents=True, exist_ok=True)
        index, offset = {}, 0
        with (self.directory / PACK).open('wb') as stream:
            for key, (standard, hd) in entries.items():
                stream.write(hd)
                index[key] = [offset, len(hd), list(image_size(standard)), list(image_size(hd))]
                offset += len(hd)
        (self.directory / INDEX).write_text(json.dumps(index, separators=(',', ':')), encoding='utf-8')
        self._index = index

    def add(self, entries: dict, replace=(), remove=()) -> int:
        """Add `entries` ({fingerprint: (standard bytes, hd bytes)}) to the store, keeping what it holds; returns how many
        were new or changed. A fingerprint in `replace` takes its new picture even if the store holds one, and one in
        `remove` is dropped (both hand-confirmed corrections; the old bytes stay unreferenced in the pack until the next
        `write`). (`write` replaces the whole store and needs every standard picture again.)"""
        self.directory.mkdir(parents=True, exist_ok=True)
        index = dict(self.index)
        pack = self.directory / PACK
        offset = pack.stat().st_size if pack.exists() else 0
        added = 0
        for key in remove:
            if index.pop(key, None) is not None:
                added += 1
        with pack.open('ab') as stream:
            for key, (standard, hd) in entries.items():
                if key in index and key not in replace:
                    continue
                if key in index and self.twin(standard) == hd:
                    continue
                stream.write(hd)
                index[key] = [offset, len(hd), list(image_size(standard)), list(image_size(hd))]
                offset += len(hd)
                added += 1
        (self.directory / INDEX).write_text(json.dumps(index, separators=(',', ':')), encoding='utf-8')
        self._index = index
        return added

    def source(self) -> dict:
        """What last built the store from a shipped twin map (`build_from_map`): {'map': version}, or {}."""
        try:
            data = json.loads((self.directory / SOURCE).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def mark_source(self, version: str) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / SOURCE).write_text(json.dumps({'map': version}), encoding='utf-8')

    def clear(self) -> None:
        """Empty the store's pictures (`build_from_map` before a new map's rebuild); the coverage cache stays."""
        for name in (INDEX, PACK, SOURCE, EFFECTS, PORTRAITS):
            try:
                (self.directory / name).unlink()
            except FileNotFoundError:
                pass
        self._index = {}
        self._filled = {}

    def add_pictures(self, pictures: dict) -> int:
        """Add `pictures` ({standard fingerprint: (standard size, hd bytes)}) that the store does not hold yet: the
        shipped twin map's form, which names the standard picture by fingerprint and size only. Returns how many."""
        self.directory.mkdir(parents=True, exist_ok=True)
        index = dict(self.index)
        pack = self.directory / PACK
        offset = pack.stat().st_size if pack.exists() else 0
        added = 0
        with pack.open('ab') as stream:
            for key, (size, hd) in pictures.items():
                if key in index:
                    continue
                stream.write(hd)
                index[key] = [offset, len(hd), list(size), list(image_size(hd))]
                offset += len(hd)
                added += 1
        (self.directory / INDEX).write_text(json.dumps(index, separators=(',', ':')), encoding='utf-8')
        self._index = index
        return added

    def coverage(self, record_id: str):
        """(total, matched) local pictures for a standard episode, from the coverage cache
        (tools/build_hd_coverage.py), or None if that episode has never been measured."""
        if self._coverage is None:
            try:
                self._coverage = json.loads((self.directory / COVERAGE).read_text(encoding='utf-8'))
            except (OSError, ValueError):
                self._coverage = {}
        entry = self._coverage.get(record_id)
        return (entry['total'], entry['matched']) if entry else None

    def write_coverage(self, entries: dict) -> None:
        """Replace the coverage cache with `entries` ({record id: {'total': n, 'matched': m}})."""
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / COVERAGE).write_text(json.dumps(entries, separators=(',', ':')), encoding='utf-8')
        self._coverage = entries


SD_DIRECTORY = 'sd_portraits'   # SD Portraits (owner, 2026-11-25): the standard originals HD portraits go back to
TABLES = 'tables.json'
SD_ADDON = 'shssd'              # the SD add-on (tools/build_sd_addon.py): the originals a typical HD install lacks
SD_MODES = ('off', 'all', 'redesigns')


class SdPortraits:
    """The library's SD Portraits store: the standard originals of HD portraits, by their own fingerprint (`index.json`
    beside `pack.bin`, as the twin store), and the shipped map's tables (`tables.json`): which original each HD
    portrait goes back to (`sd_of`, with an HD episode's own where its story says otherwise, `sd_of_episode`), which
    pairs are redesigns (`redesigned`) and which shared-bank ids are portraits (`bank_portraits`). Built with the
    twin store from the player's own standard episodes and the SD add-on (`build_from_map`)."""

    def __init__(self, directory: Path):
        self.pictures = TwinStore(directory)
        self.pictures.directory = Path(directory) / SD_DIRECTORY
        self._tables = None
        self._scaled = {}

    @property
    def tables(self):
        if self._tables is None:
            try:
                data = json.loads((self.pictures.directory / TABLES).read_text(encoding='utf-8'))
            except (OSError, ValueError):
                data = {}
            self._tables = dict(sd_of=data.get('sd_of', {}), sd_of_episode=data.get('sd_of_episode', {}),
                                redesigned=set(data.get('redesigned', ())),
                                bank_portraits=set(data.get('bank_portraits', ())))
        return self._tables

    def write_tables(self, twin_map):
        self.pictures.directory.mkdir(parents=True, exist_ok=True)
        data = dict(sd_of=getattr(twin_map, 'SD_OF', {}), sd_of_episode=getattr(twin_map, 'SD_OF_EPISODE', {}),
                    redesigned=sorted(getattr(twin_map, 'REDESIGNED', ())),
                    bank_portraits=sorted(getattr(twin_map, 'BANK_PORTRAITS', ())))
        (self.pictures.directory / TABLES).write_text(json.dumps(data, separators=(',', ':')), encoding='utf-8')
        self._tables = None

    def candidates(self, record_id, hd_key):
        """The originals an HD episode's picture `hd_key` may go back to, best first: the episode's own (where its
        story's standard release shows a different one: alone when it is a different look) then the map's."""
        own = self.tables['sd_of_episode'].get(record_id, {}).get(hd_key)
        shared = list(self.tables['sd_of'].get(hd_key, ()))
        if own is None:
            return shared
        key, strict = own
        return [key] if strict else [key, *shared]

    def original(self, record_id, hd_key):
        """(the original's bytes, whether its pair is a redesign) for an HD episode's portrait, or None."""
        for key in self.candidates(record_id, hd_key):
            data = self.pictures.twin_by_key(key)
            if data is not None:
                return data, key in self.tables['redesigned']
        return None

    def wanted(self):
        keys = {key for keys in self.tables['sd_of'].values() for key in keys}
        keys.update(key for episode in self.tables['sd_of_episode'].values() for key, _ in episode.values())
        return keys

    def scaled(self, data):
        """The original at twice its size (the HD layout's density, as `fill` draws a standard picture)."""
        key = fingerprint(data)
        if key not in self._scaled:
            if len(self._scaled) > 256:
                self._scaled.clear()
            self._scaled[key] = upscale(data)
        return self._scaled[key]

    def source(self):
        try:
            data = json.loads((self.pictures.directory / SOURCE).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def mark_source(self, version, addon):
        self.pictures.directory.mkdir(parents=True, exist_ok=True)
        (self.pictures.directory / SOURCE).write_text(json.dumps({'map': version, 'addon': addon}), encoding='utf-8')


def sd_addon_revision(library):
    """The imported SD add-on's revision, or None."""
    try:
        found = library.addon(SD_ADDON) if hasattr(library, 'addon') else None
    except Exception:
        found = None
    return None if found is None else found[0].get('revision')


def sd_portraits_due(library, twin_map):
    """Whether the SD Portraits store is from another map version or another SD add-on than the library has."""
    if not hasattr(twin_map, 'SD_OF'):
        return False
    source = library.sd_portraits_store().source()
    return source.get('map') != twin_map.VERSION or source.get('addon') != sd_addon_revision(library)


# ---------------------------------------------------------------------------------------------------------------- building

def collect_art(resources, steps=1500, seconds=60, start_script=25001):
    """What a standard or HD episode registers and shows, by playing it through the explorer for a while:
    ({character: [portrait ids]}, {background ids shown}, {character: name}).

    600 steps/25 seconds missed a background this walk only reaches well into a long scene (confirmed real content:
    6_4_This_Friday_Night's own #26028, found only once the budget was raised, correlating 0.9999 with its HD
    twin). Raised for a better chance at that without a story pair taking too much longer -- most stories finish
    on their own well under either budget; this only matters for the few that do not."""
    import time
    from .runtime import Session
    from .tree_explorer import Explorer, Playthrough
    session = Session(resources, start_script=start_script, ephemeral=True)
    session.advance()
    explorer, playthrough = Explorer(resources, ephemeral=True), Playthrough(1)
    variants, backgrounds = {}, set()
    started = time.time()
    for _ in range(steps):
        if time.time() - started > seconds or session.pending is None or session.pending.name in ('finished', 'episode_exit'):
            break
        engine = session.engine
        for character, ids in engine.character_art_variants.items():
            variants[character] = list(ids)
        backgrounds.add(engine.panel.background_id)
        try:
            explorer.act(session, playthrough)
        except Exception:               # an unsupported screen ends the sample, not the build
            break
    return variants, backgrounds, dict(session.engine.character_names)


def names_compatible(a, b):
    """Whether two script-set names could be the same character under a different amount of the same title, not
    two different names that merely share a prefix -- one release uses a short, generic name and the other its
    fuller form for the same person at the same numeric id (found in 75_Anger_Management's own "Coach"/"Coach
    Kessler", and 19_flex_games' own "Judge"/"Judge Tigh")."""
    if a == b:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    return longer.startswith(shorter + ' ')


@dataclass
class ArtMatch:
    """One picture the two releases register at the same place in the story (the same character's expression slot, or the
    same background id), with a real HD twin found for it."""
    std_id: int
    hd_id: int
    std_bytes: bytes
    hd_bytes: bytes
    kind: str                   # 'portrait' | 'background'
    character: int | None       # the entity id, for a portrait; None for a background
    std_name: str | None = None  # the two releases' own names for this character, script-set (`set_character_name`);
    hd_name: str | None = None   # None for a background, or a portrait whose name the sample walk never saw


@dataclass
class UnpairedArt:
    """A local picture one release shows that the pairing could not match to the other: either the other release has
    nothing registered at that slot, or what it has there failed the twin size check."""
    id: int
    data: bytes
    kind: str
    character: int | None
    name: str | None = None


def pair_art_detailed(standard, hd):
    """Every local (id >= LOCAL_ART) picture the two releases register identically, matched or not.

    Returns (matches: [ArtMatch], unpaired_standard: [UnpairedArt], unpaired_hd: [UnpairedArt])."""
    std_variants, std_backgrounds, std_names = collect_art(standard)
    hd_variants, hd_backgrounds, hd_names = collect_art(hd)
    matches, unpaired_std, unpaired_hd = [], [], []
    consumed_hd = set()   # HD character ids already spoken for, by id or by name, so nothing is claimed twice

    def local(resource_id):
        return resource_id >= LOCAL_ART

    def add_unpaired(bucket, resources, resource_id, kind, character, name):
        if not local(resource_id):
            return
        try:
            data = resources.raw_asset(resource_id)
        except Exception:
            return
        bucket.append(UnpairedArt(resource_id, data, kind, character, name))

    def try_match(std_id, hd_id, kind, character, std_name, hd_name):
        if not local(std_id) or not local(hd_id):
            return
        try:
            std_bytes, hd_bytes = standard.raw_asset(std_id), hd.raw_asset(hd_id)
        except Exception:
            return
        # A portrait's identity is already confirmed independently (a shared numeric id and/or name) by the time
        # try_match is called, so it can afford `is_upgraded`'s looser, identity-blind size check; a background,
        # matched on nothing but its id or its own content, still needs `is_twin`'s tighter proportional band.
        sized = is_upgraded(std_bytes, hd_bytes) if kind == 'portrait' else is_twin(std_bytes, hd_bytes)
        if sized and not (kind == 'background' and is_flat_capture(std_bytes, hd_bytes)):
            matches.append(ArtMatch(std_id, hd_id, std_bytes, hd_bytes, kind, character, std_name, hd_name))
        else:
            unpaired_std.append(UnpairedArt(std_id, std_bytes, kind, character, std_name))
            unpaired_hd.append(UnpairedArt(hd_id, hd_bytes, kind, character, hd_name))

    resolved_std = set()

    # Pass 1: every character both releases number the same, and do not disagree by name, lines up directly -- the
    # safe majority case, which must claim its HD ids before pass 2's name-based guessing gets a chance to (guessing
    # first, in whatever order a dict happens to iterate, could hand a same-numbered id away from the character it
    # would otherwise have lined up with directly, then "recover" that character from a worse, coincidental name
    # match elsewhere). A shared numeric id is only trusted when the two releases also agree on the character's own
    # name (when either side never showed a name, there is nothing to disagree with, so id alone still stands): the
    # same id can name two different people between releases (found in 9_4_This_is_Spartan -- HD folds one of the
    # standard release's three "Colt" ids away, shifting every id from "Jeeves" on down by one).
    for character, listed in std_variants.items():
        other = hd_variants.get(character)
        name, hd_name = std_names.get(character), hd_names.get(character)
        agrees = name is None or hd_name is None or names_compatible(name, hd_name)
        if other and len(other) == len(listed) and agrees:
            for std_id, hd_id in zip(listed, other):
                try_match(std_id, hd_id, 'portrait', character, name, hd_name)
            resolved_std.add(character)
            consumed_hd.add(character)

    # Pass 2a: for everything pass 1 left over, decide every name-based recovery before dumping anything as
    # unpaired -- deciding and dumping in the same step would let one leftover character's own (rejected) `other`
    # get dumped to unpaired before a later character in the same pass recovers that exact HD id by name, leaving
    # it double-booked (both a match and a false "unpaired" entry). A name with no single, unambiguous candidate
    # (none, or several -- e.g. the standard release's spare "Colt" once its other two ids have already claimed
    # HD's only two) is left for pass 2b to report as unpaired, not guessed at.
    hd_by_name = {}
    for hd_character in hd_variants:
        if hd_character not in consumed_hd:
            hd_by_name.setdefault(hd_names.get(hd_character), []).append(hd_character)

    recovered = {}   # standard character -> the HD character its name (not its number) recovered
    for character, listed in std_variants.items():
        if character in resolved_std:
            continue
        name = std_names.get(character)
        candidates = [c for c in hd_by_name.get(name, ()) if len(hd_variants[c]) == len(listed)] if name else []
        if len(candidates) == 1:
            hd_character = candidates[0]
            recovered[character] = hd_character
            consumed_hd.add(hd_character)
            hd_by_name[name].remove(hd_character)

    # Pass 2b: apply every recovery, then account for whatever no recovery claimed -- a leftover character's own
    # same-numbered `other`, if it has one, is only truly unpaired once pass 2a has had its say on every character
    # (it may itself have just been claimed above, by a *different* standard character's name).
    for character, listed in std_variants.items():
        if character in resolved_std:
            continue
        name, other = std_names.get(character), hd_variants.get(character)
        if character in recovered:
            hd_character = recovered[character]
            for std_id, hd_id in zip(listed, hd_variants[hd_character]):
                try_match(std_id, hd_id, 'portrait', character, name, hd_names.get(hd_character))
        else:
            for std_id in listed:
                add_unpaired(unpaired_std, standard, std_id, 'portrait', character, name)
        if other and character not in consumed_hd:
            for hd_id in other:
                add_unpaired(unpaired_hd, hd, hd_id, 'portrait', character, hd_names.get(character))
            consumed_hd.add(character)

    # An HD character whose numeric id never appears in std_variants at all (e.g. HD's own "Jeeves", sitting at a
    # different id than the standard release's) was invisible to the loop above, which only ever looked HD ids up
    # by a standard character's own id.
    for hd_character, hd_ids in hd_variants.items():
        if hd_character in consumed_hd or hd_character in std_variants:
            continue
        for hd_id in hd_ids:
            add_unpaired(unpaired_hd, hd, hd_id, 'portrait', hd_character, hd_names.get(hd_character))

    def background_ok(std_bytes, hd_bytes):
        # `is_upgraded`, not `is_twin`: a background pairing is never accepted on size alone (every call site here
        # also checks `is_flat_capture`'s own correlation floor, direct or the stricter recovery one), so it can
        # afford the same looser, non-proportional size band a name-confirmed portrait gets -- a real HD background
        # does not always keep the standard release's aspect ratio either (5_6_Perfect_Paige's own #26060,
        # 480x720 -> 768x1024: the height falls just short of `is_twin`'s 1.6x floor).
        return is_upgraded(std_bytes, hd_bytes) and not is_flat_capture(std_bytes, hd_bytes)

    std_bytes_by_id, hd_bytes_by_id = {}, {}
    for bid in std_backgrounds:
        if local(bid):
            try:
                std_bytes_by_id[bid] = standard.raw_asset(bid)
            except Exception:
                pass
    for bid in hd_backgrounds:
        if local(bid):
            try:
                hd_bytes_by_id[bid] = hd.raw_asset(bid)
            except Exception:
                pass

    # Direct same-id pairing first -- the common, safe case. A same-id pair that fails the content check (an id
    # reused for a different photo between releases, found in MTX_The_Storm_Part_1's own #26021) is left in both
    # dicts, not dumped as unpaired yet: its real HD counterpart may still turn up under a different id below.
    for bid in sorted(std_backgrounds & hd_backgrounds):
        std_bytes, hd_bytes = std_bytes_by_id.get(bid), hd_bytes_by_id.get(bid)
        if std_bytes is not None and hd_bytes is not None and background_ok(std_bytes, hd_bytes):
            matches.append(ArtMatch(bid, bid, std_bytes, hd_bytes, 'background', None))
            del std_bytes_by_id[bid], hd_bytes_by_id[bid]

    # A background has no name to fall back on, but it is a real photo: unlike a portrait, a strong pixel
    # correlation is itself direct evidence of the same picture, whether its id was renumbered between releases
    # (found in 5_6_Perfect_Paige's own #26112/#26057) or simply reused for something else on one side. Recovered
    # only when exactly one candidate clears the floor; more than one (or none) is left unpaired, not guessed at.
    # The floor sits well above a merely similar-looking photo, not just a corrupt one: two different establishing
    # shots of the same set (found in 4_8_Sectionals and 5_3_Paigeagainstthemachine) can still correlate around
    # 0.7-0.8, which would otherwise make every genuine match in that episode look ambiguous.
    claimed_hd = set()
    for std_id in sorted(std_bytes_by_id):
        std_bytes = std_bytes_by_id[std_id]
        candidates = [(hd_id, hd_bytes) for hd_id, hd_bytes in hd_bytes_by_id.items()
                     if hd_id not in claimed_hd and background_ok(std_bytes, hd_bytes)
                     and correlation(std_bytes, hd_bytes) >= BACKGROUND_RECOVERY_FLOOR]
        if len(candidates) == 1:
            hd_id, hd_bytes = candidates[0]
            matches.append(ArtMatch(std_id, hd_id, std_bytes, hd_bytes, 'background', None))
            claimed_hd.add(hd_id)
        else:
            add_unpaired(unpaired_std, standard, std_id, 'background', None, None)
    for hd_id, hd_bytes in hd_bytes_by_id.items():
        if hd_id not in claimed_hd:
            add_unpaired(unpaired_hd, hd, hd_id, 'background', None, None)
    return matches, unpaired_std, unpaired_hd


def pair_art(standard, hd):
    """{standard bytes fingerprint: (standard bytes, hd bytes)} for the local art the two releases of a story register
    identically: each portrait variant of each character, and each background both show."""
    matches, _, _ = pair_art_detailed(standard, hd)
    found = {}
    for match in matches:
        found.setdefault(fingerprint(match.std_bytes), (match.std_bytes, match.hd_bytes))
    return found


def best_by_source_count(matches):
    """{standard bytes fingerprint: (standard bytes, hd bytes)} across every story pair's own `pair_art_detailed`
    matches, keeping only the HD picture the most story pairs agree on for a given standard picture.

    A picture's *bytes* are not a promise of one identity: the same SD art can be reused, under a different
    identity, by more than one story, each with its own correctly redrawn HD counterpart -- found in
    11_0_April_Fools, whose own "Monkey" costume shares its SD bytes with several other episodes' "Amanda" (a
    bunny costume). Picking whichever story happens to be processed first (`pair_art`'s own contract, and how a
    plain per-pair dict update would behave across a whole library) would show that one lucky story's redraw
    everywhere else the same SD bytes appear; picking by source count instead favors the reading most of the
    library's own stories settle on."""
    grouped = {}
    for match in matches:
        variants = grouped.setdefault(fingerprint(match.std_bytes), {})
        count, _ = variants.get(fingerprint(match.hd_bytes), (0, match))
        variants[fingerprint(match.hd_bytes)] = (count + 1, match)
    found = {}
    for std_fp, variants in grouped.items():
        _, best = max(variants.values(), key=lambda item: item[0])
        found[std_fp] = (best.std_bytes, best.hd_bytes)
    return found


# ---------------------------------------------------------------------------------------------------- the shipped twin map

def coverage_counts(library, resources, ids):
    """(total, matched) for a standard episode's counted pictures `ids` (tools/build_hd_coverage.py chooses them): a
    picture is matched when the HD app bundle replaces it by id (shared bank, ids below LOCAL_ART), when the twin store
    holds it, or when it is already HD-sized in the standard file (Set_12's pool)."""
    store = library.twin_store()
    total = matched = 0
    for resource_id in ids:
        if resource_id < 0 or not resources.exists(resource_id):
            continue
        total += 1
        if resource_id < LOCAL_ART and library.hd_asset(resource_id) is not None:
            matched += 1
            continue
        data = resources.raw_asset(resource_id)
        if store.twin(data) is not None or is_hd_size(image_size(data)):
            matched += 1
    return total, matched


def build_from_map(library, twin_map, progress=None) -> bool:
    """Build (or update) the library's twin store and coverage cache from a shipped twin map (this fork; SHS's is
    `shs/hd_twin_map.py`, exported by tools/export_hd_twin_map.py from the owner's reviewed library).

    The map names pictures by fingerprint only -- no art ships with the app. Each HD picture is found in the
    player's own episodes, and copied into the store under its standard twin's fingerprint; a picture the player's
    files cannot supply is left out, and coverage is counted from what was actually built, so a standard episode loses
    its SD mark only when it really plays entirely in HD. Returns False when the store already came from this map.
    `progress(done, total)` reports the episodes searched. Runs off the UI thread (the app's preview job).

    A new map version rebuilds the store from nothing, so a pair the new map drops or moves (the 2026-11 art audit's
    corrections) leaves every player's store too, not only the owner's. An entry may carry a fifth field, an effect
    (`hd_effects`): the HD picture recreated to match the standard one (the noir scenes' greyscale, a mirrored copy),
    fitted from the player's own copy of that standard picture; without it the entry is left out."""
    from .hd_effects import apply as apply_effect
    store = library.twin_store()
    sd_store = library.sd_portraits_store() if hasattr(library, 'sd_portraits_store') else None
    twins_due = store.source().get('map') != twin_map.VERSION
    sd_due = sd_store is not None and sd_portraits_due(library, twin_map)
    if not twins_due and not sd_due:
        return False
    wanted, standards = {}, set()                       # hd fingerprint -> [(standard, size, effect)]; effect sources
    if twins_due:
        store.clear()
        for standard, entry in twin_map.TWINS.items():
            hd, width, height = entry[:3]
            effect = tuple(entry[3]) if len(entry) > 3 and entry[3] else None
            wanted.setdefault(hd, []).append((standard, (width, height), effect))
            if effect:
                standards.add(standard)
    originals = set()                                   # SD Portraits: the standard originals of HD portraits
    if sd_due:
        sd_store.pictures.clear()
        sd_store.write_tables(twin_map)
        originals = sd_store.wanted()
    # HD episodes first: in the owner's library every HD picture the map names is in one. The SD add-on last.
    records = sorted(library.episodes, key=lambda record: record.get('variant') != 'hd')
    found, held, kept = set(), {}, set()                # held: the bytes an effect needs, standard and HD

    def archives():
        for record in records:
            try:
                yield record.get('name'), library.open_episode(record['id']).archive
            except Exception as error:                  # one unreadable episode must not stop the rest
                logging.warning('HD art: skipped %s: %s', record.get('name'), error)
        if originals:
            found_addon = library.addon(SD_ADDON) if hasattr(library, 'addon') else None
            if found_addon is not None:
                yield SD_ADDON, found_addon[1]

    total = len(records) + bool(originals)
    for done, (name, archive) in enumerate(archives()):
        if progress is not None:
            progress(min(done, total - 1), total)
        if len(found) == len(wanted) and standards <= set(held) and originals <= kept:
            break
        pictures, sd_pictures = {}, {}
        for resource_id in archive.entries:
            if resource_id < LOCAL_ART:
                continue
            try:
                data = archive.read(resource_id)
            except Exception:
                continue
            key = fingerprint(data)
            if key in standards:
                held.setdefault(key, data)
            if key in originals and key not in kept:
                kept.add(key)
                sd_pictures[key] = (image_size(data) or (0, 0), data)
            if key in wanted and key not in found:
                found.add(key)
                for standard, size, effect in wanted[key]:
                    if effect:
                        held.setdefault(key, data)
                    else:
                        pictures[standard] = (size, data)
        if pictures:
            store.add_pictures(pictures)
        if sd_pictures:
            sd_store.pictures.add_pictures(sd_pictures)
    if originals - kept:
        # An original a story's standard release shows from the shared bank (by id, BANK_PORTRAITS): Android's own
        # copy, which every library's APK holds.
        sd_pictures = {}
        for resource_id in sorted(sd_store.tables['bank_portraits']):
            try:
                data = library.android_asset(resource_id)
            except Exception:
                continue
            key = fingerprint(data)
            if key in originals and key not in kept:
                kept.add(key)
                sd_pictures[key] = (image_size(data) or (0, 0), data)
        if sd_pictures:
            sd_store.pictures.add_pictures(sd_pictures)
    if twins_due:
        pictures = {}
        for hd, entries in wanted.items():
            for standard, size, effect in entries:
                if not effect or hd not in held or standard not in held:
                    continue                            # this player lacks one of the two pictures: nothing shows it
                try:
                    pictures[standard] = (size, apply_effect(held[standard], held[hd], effect))
                except (OSError, ValueError) as error:
                    logging.warning('HD art: %s not recreated: %s', standard, error)
        if pictures:
            store.add_pictures(pictures)
        store.coverage('')                              # loads the cache: other episodes' entries are kept
        coverage = dict(store._coverage or {})
        ids_by_record = {record['id']: record for record in library.episodes}
        for record_id, ids in twin_map.COVERAGE.items():
            if record_id not in ids_by_record:
                continue
            try:
                total, matched = coverage_counts(library, library.open_episode(record_id), ids)
            except Exception as error:
                logging.warning('HD art: no coverage for %s: %s', ids_by_record[record_id].get('name'), error)
                continue
            coverage[record_id] = {'total': total, 'matched': matched}
        store.write_coverage(coverage)
        store.mark_source(twin_map.VERSION)
        logging.info('HD art: %d of %d HD pictures found; %d episodes measured', len(found), len(wanted), len(coverage))
    if sd_due:
        sd_store.mark_source(twin_map.VERSION, sd_addon_revision(library))
        logging.info('SD Portraits: %d of %d originals found', len(kept), len(originals))
    return True
