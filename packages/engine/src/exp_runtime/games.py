"""Installed game adapters; each owns its asset and host-service contracts."""
from importlib import import_module
from importlib.util import find_spec

from .exp import ContentError


class GameUnavailableError(ContentError):
    """The requested game adapter has not been installed."""


class GameRegistry(dict):
    def __missing__(self, key):
        if key in ('shs', 'cod'):
            raise GameUnavailableError(
                f'{key.upper()} support is not installed. Install "exp-runtime[{key}]".')
        raise ContentError(f'Unknown game: {key!r}')


GAMES = GameRegistry()
for _key in ('shs', 'cod'):
    # Test the package itself, so a missing dependency *inside* an installed
    # adapter is reported instead of silently hiding a broken installation.
    if find_spec(f'exp_runtime.{_key}') is not None:
        _profile = import_module(f'exp_runtime.{_key}.profile')
        GAMES[_profile.KEY] = _profile
SHS_ANDROID = 'shs-android-1.0.9'
SHS_IOS = 'shs-ios-assets-v1'
COD_IOS = 'cod-ios-assets-v1'
COD_IOS_FREE = 'cod-ios-free-assets-v1'
COD_IOS_FREE_LOCALIZED = 'cod-ios-free-localized-assets-v1'
PROFILES = {SHS_ANDROID: ('shs', 'apk'), SHS_IOS: ('shs', 'ipa'), COD_IOS: ('cod', 'ipa'),
            COD_IOS_FREE: ('cod', 'ipa'), COD_IOS_FREE_LOCALIZED: ('cod', 'ipa')}


def game_id(resources):
    library = getattr(resources, 'library', resources)
    return getattr(library, 'game_id', 'shs')


def has_translated_minigames(profile, record, presentation=None):
    """Whether an episode's record is one the "Use Translated Mini-Games" switch changes (profile TRANSLATED_MINIGAMES:
    pack -> its episodes, or None for all of them), or an episode made in the Creator that asks for them (its
    presentation record's `minigames`)."""
    packs = getattr(profile, 'TRANSLATED_MINIGAMES', {})
    pack = record.get('pack_id')
    if pack in packs and (packs[pack] is None or record.get('episode_id') in packs[pack]):
        return True
    return bool((presentation or {}).get('minigames'))
