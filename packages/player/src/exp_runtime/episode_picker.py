"""The HD picker's data: rows of episodes, their previews, and saved-game screenshots.

Rows come from episode_index.py; this module binds them to a library, its release variants and its images.
"""
from dataclasses import dataclass
from io import BytesIO
import logging
import threading

import pygame

from . import episode_thumbnails
from .content import ContentError, is_bundled
from .hd_scale import S
from .episode_dates import RELEASE_DATES, REDUNDANT_BUNDLES, VOTE_PACKAGES
from .games import GAMES, game_id
from .episode_index import (HD, PickerRow, STANDARD, build_chronological_rows, build_rows, category_labels,
                            duplicates, episode_label, format_airdate, resolve_variants)

TILE_PIXELS = (216 * S, 290 * S)  # the 216 x 290 point tile at the menus' scale (hd_scale)


@dataclass(frozen=True)
class EpisodeInfo:
    """The episode info card (this fork): the picker's own title and airdate, the store's description and price."""
    title: str
    description: str
    airdate: str | None
    price: str | None


class PickerModel:
    def __init__(self, library, *, mega_label='Mega Packs', novel_label='Special SHS Novel Content',
                chronological=False, title_language='en'):
        self.library = library
        self.title_language = title_language
        self.mega_label = mega_label
        self.chronological = chronological
        self.prefer = HD if library.hd_ipa is not None else STANDARD
        records = library.episodes
        self.variants = resolve_variants(records, library.catalog)
        hidden = duplicates(records, self.prefer, bundled=is_bundled)
        self.records = [r for r in records if r['id'] not in hidden]
        self.cod = self.store = None
        if getattr(library, 'game_id', None) == 'cod':
            # Cause of Death's own categories and dates in the same picker (cod/episodes.py).
            from .cod import episodes as cod
            self.cod = cod
            try:
                listing = library.store_listing()
            except (ContentError, OSError, ValueError) as error:
                logging.warning('Store listing unavailable: %s', error)
                listing = None
            if listing is not None:
                # 1.4.7's store listing, when imported: each episode's description and price (cod/store.py).
                from .cod.store import Store
                self.store = Store(listing)
            self.rows = (cod.build_airing_rows(self.records) if chronological
                         else cod.build_rows(self.records, library.catalog, bundled=is_bundled))
            self._categories = cod.category_labels(self.records, library.catalog, bundled=is_bundled)
        elif chronological:
            self.rows = build_chronological_rows(self.records, RELEASE_DATES, redundant_bundles=REDUNDANT_BUNDLES,
                                                 vote_packages=VOTE_PACKAGES)
            self._categories = category_labels(self.records, self.variants, library.catalog, mega_label=mega_label,
                                               novel_label=novel_label, bundled=is_bundled)
        else:
            self.rows = build_rows(self.records, self.variants, library.catalog, mega_label=mega_label,
                                   novel_label=novel_label, bundled=is_bundled)
        self.by_id = {r['id']: r for r in self.records}
        self.position = {r['id']: (row, column) for row, entry in enumerate(self.rows)
                         for column, r in enumerate(entry.episodes)}
        self._previews = {}
        self._preview_lock = threading.Lock()
        self._wanted = {}               # {record id: record} for the background thread, the newest asked for first
        self._decoded = {}              # {record id: an image it finished, not yet in `_previews`}
        self._decoding = None           # the record id it has in hand; None once a forget_preview outdates that
        self._decoder = None
        self._has_info = {}
        # The standard-edition marker only says something when HD episodes sit beside them.
        self.mixed = self.prefer == HD and any(self.variants[r['id']] == HD for r in self.records)

    def mark(self, record):
        """The tile's or row's tag, or None: an episode translated from another SHS game's (the game profile's
        LEGACY_GAMES badge, "NR"), else the standard-edition "SD" (is_standard)."""
        legacy = getattr(GAMES.get(game_id(self.library)), 'LEGACY_GAMES', {}).get(record.get('legacy'))
        if legacy is not None:
            return legacy['badge']
        return 'SD' if self.is_standard(record) else None

    def mark_color(self, record):
        """A legacy game's own colour for its tag (LEGACY_GAMES), else None."""
        legacy = getattr(GAMES.get(game_id(self.library)), 'LEGACY_GAMES', {}).get(record.get('legacy'))
        return None if legacy is None else legacy['color']

    def is_standard(self, record):
        """Whether the tile gets the standard-edition marker."""
        # Episodes bundled in the APK (Football Star ...) play with the HD bundle's art and minigames, so they are
        # not marked whichever release their script came from.
        if not (self.mixed and self.variants.get(record['id']) == STANDARD and not is_bundled(record)):
            return False
        if self.library.hd_art_mode == 'off':
            return True
        # With HD art substitution on, an episode whose own coverage cache (tools/build_hd_coverage.py) says every
        # one of its pictures already has an HD twin plays with nothing left looking lower-resolution, so the
        # marker would only be noise; one still missing some keeps it. An unmeasured episode keeps the marker too
        # (this player's own addition; an unmeasured cache must not silently claim full coverage). The cache's own
        # "total" is only what one sample walk found (see build_hd_coverage.py), so this is a lower-bound claim,
        # not a guarantee against a branch the walk never reached.
        coverage = self.library.twin_store().coverage(record['id'])
        return not (coverage is not None and coverage[0] > 0 and coverage[1] == coverage[0])

    def label(self, record):
        if self.cod is not None:
            return self.cod.label(record, bundled=is_bundled)
        return episode_label(record, self.title_language)

    def subtitle(self, record):
        """The list views' second line under a title: category and airdate for Now Airing (its rows aren't
        grouped by category, so each one names its own), or just the airdate for Episodes On Demand (its own
        header already names the category). The date itself is external research with no native source --
        see `episode_dates.py` -- and is left out for a title that research hasn't dated (none currently)."""
        # A translated episode shares its smartphone twin's title, not its airdate (shshd-runtime).
        date = None if record.get('legacy') else (self.cod.RELEASE_DATES if self.cod else RELEASE_DATES).get(
            record['titles'][0])
        airdate = f'Airdate: {format_airdate(date)}' if date else None
        if not self.chronological:
            return airdate
        category = self._categories.get(record['id'], '').upper()
        if category and airdate:
            return f'{category} - {airdate}'
        return category or airdate

    def info(self, record):
        """The episode's info card, or None: only with an imported store listing (CoD's mtxprods), from the episode's
        own store product (the On Demand copy before the Now Airing one; a Volume bundle's own set product). Volume
        One, the base game, was never sold: its card is the App Store listing's text, free (cod/store.py)."""
        if self.store is None:
            return None
        from .cod.store import VOLUME_ONE_DESCRIPTION, price_label
        if record.get('builtin') == 'volume-one':
            description, price = VOLUME_ONE_DESCRIPTION, 'Free'
        else:
            product = self.store.product(record)
            if product is None:
                return None
            description, price = (product.get('desc') or '').strip(), price_label(product)
        date = self.cod.RELEASE_DATES.get(record['titles'][0])
        return EpisodeInfo(self.label(record), description, f'Airdate: {format_airdate(date)}' if date else None,
                           price)

    def has_info(self, record):
        if self.store is None:
            return False
        if record['id'] not in self._has_info:
            self._has_info[record['id']] = self.info(record) is not None
        return self._has_info[record['id']]

    def preview(self, record):
        """The episode's preview as a 432 x 580 surface: the app's own image, else the generated title card, else
        the app's placeholder, else a flat card."""
        cached = self._previews.get(record['id'])
        if cached is not None:
            return cached
        return self._keep_preview(record, self._decode_preview(record))

    def preview_soon(self, record):
        """preview(), without the wait: None until the background thread has it. A phone took 34 ms a tile, on the
        drawing thread a freeze of 200 ms at each new row."""
        cached = self._previews.get(record['id'])
        if cached is not None:
            return cached
        with self._preview_lock:
            image = self._decoded.pop(record['id'], False)
        if image is not False:
            return self._keep_preview(record, image)
        self.want_preview(record)
        return None

    def want_preview(self, record):
        """Ask the background thread for a preview, ahead of those asked for earlier."""
        record_id = record['id']
        if record_id in self._previews:
            return
        with self._preview_lock:
            if record_id in self._decoded or record_id == self._decoding:
                return
            self._wanted.pop(record_id, None)
            self._wanted[record_id] = record
            if self._decoder is None:           # it ends when it runs out, so a picker left behind holds no thread
                self._decoder = threading.Thread(target=self._decode_wanted, name='episode-previews', daemon=True)
                self._decoder.start()

    def _decode_wanted(self):
        while True:
            with self._preview_lock:
                if not self._wanted:
                    self._decoder = None
                    return
                record_id, record = self._wanted.popitem()
                self._decoding = record_id
            try:
                image = self._decode_preview(record)
            except Exception as error:          # a library let go under it, say: the flat card
                logging.warning('Episode preview cannot be read: %s', error)
                image = None
            with self._preview_lock:
                if self._decoding == record_id:
                    self._decoded[record_id] = image
                self._decoding = None

    def _decode_preview(self, record):
        """The preview at the tile's size, unconverted, or None. Takes no display state: the background thread runs it."""
        library, image = self.library, None
        for load in (lambda: episode_thumbnails.bundled_preview(library, record),
                     lambda: self._read(episode_thumbnails.thumbnail_path(library, record)),
                     lambda: episode_thumbnails.missing_preview(library)):
            try:
                data = load()
                image = pygame.image.load(BytesIO(data)) if data else None
            except (pygame.error, OSError):
                image = None
            if image is not None:
                break
        if image is not None and image.get_size() != TILE_PIXELS:
            image = pygame.transform.smoothscale(image, TILE_PIXELS)
        return image

    def _keep_preview(self, record, image):
        if image is None:
            image = pygame.Surface(TILE_PIXELS).convert()
            image.fill((70, 78, 100))
        else:
            image = image.convert()
        self._previews[record['id']] = image
        return image

    @staticmethod
    def _read(path):
        return path.read_bytes() if path.is_file() else None

    def forget_preview(self, record_id):
        self._previews.pop(record_id, None)
        with self._preview_lock:
            self._decoded.pop(record_id, None)
            self._wanted.pop(record_id, None)
            if self._decoding == record_id:
                self._decoding = None
