"""Drive every real HD episode through as much automated content as
possible, recording which background/portrait assets actually get used and
whether they resolve to genuine HD-density art or a shared standard-density
one.

This exists to answer one question empirically, across the real 195-episode
HD library rather than the handful of episodes hand-tested during
development: do the HD resolution/portrait fixes (see legacy/findings.md,
the "HD visual fidelity" sections) actually engage for real content at
scale, or were they only ever exercised by the specific episodes picked for
manual spot-checking?

Needs the desktop extra (pygame) for image decoding, unlike audit_runtime.py
which stays pygame-free; this tool is inherently about visual/rendering
asset resolution, not just VM-level correctness.
"""
import argparse
from collections import Counter
from io import BytesIO
import json
from pathlib import Path
import tempfile

import pygame

from exp_runtime.content import ContentError, ContentLibrary, import_game
from exp_runtime.runtime import Session
from exp_runtime.ui_assets import ImagePack, UIAssetError
from exp_runtime.vm import VMError


# DialogueRenderer's Android reference portrait mask (resource 268) is
# 128x150; a portrait exceeding it on either axis is the oversized-HD-mask
# path this session's portrait fix specifically targets. The background
# convention's Android reference width is 480 (real backgrounds ship at
# 1.5x game-logical density even on Android); anything wider is real
# per-episode HD density, not an artifact of the crop math.
ANDROID_MASK_SIZE = (128, 150)
ANDROID_BACKGROUND_WIDTH = 480
MAX_STEPS = 4000
DECODE_ERRORS = (ContentError, UIAssetError, pygame.error, IndexError)


def asset_size(resources, asset_id):
    """Mirrors Desktop._image's own format detection, so this measures
    exactly what the real renderer would decode -- not a separate guess."""
    if asset_id < 0:
        return None
    data = resources.read_asset(asset_id)
    if data.startswith((b'\x89PNG', b'\xff\xd8')):
        return pygame.image.load(BytesIO(data)).get_size()
    frame = ImagePack.parse(data).images[0]
    return frame.width, frame.height


def _record(store, resources, asset_id):
    if asset_id is None or asset_id < 0 or asset_id in store:
        return
    try:
        store[asset_id] = asset_size(resources, asset_id)
    except DECODE_ERRORS as error:
        store[asset_id] = f'decode error: {type(error).__name__}: {error}'


def _cycling(recent, max_period=8):
    """True once `recent` ends with the same short sequence repeated three
    times in a row -- e.g. a failed timed-choice/QTE looping back through
    "What do you want to do? -> Replay from checkpoint" forever. Confirmed
    real: four HD episodes hit the VM's genuine 1024-word stack cap this
    way, after 800+ automatic repeats of a choice a real player would only
    ever attempt a handful of times (see legacy/findings.md). Not a
    shs-runtime bug -- an artifact of this tool's own "always pick the
    first enabled option" strategy, which this detects and stops instead
    of running an unbounded, unrealistic loop to a real crash.
    """
    for period in range(2, max_period + 1):
        if len(recent) >= period * 3:
            window = recent[-period * 3:]
            if window[:period] == window[period:2 * period] == window[2 * period:]:
                return True
    return False


def drive_episode(resources, *, before_start=None):
    """before_start(session), if given, runs before the very first advance()
    -- Desktop.__init__ itself calls advance() as its last construction
    step, so any test-only session seeding (see audit_hd_football.py) must
    happen here, not after a Session/Desktop object already exists."""
    session = Session(resources)
    if before_start is not None:
        before_start(session)
    backgrounds, portraits = {}, {}
    recent_choices = []
    stop_reason, steps = 'step_budget', MAX_STEPS
    for step in range(MAX_STEPS):
        try:
            if session.pending is None:
                session.advance()
            action = session.pending
            if action is None:
                stop_reason, steps = 'no_pending', step
                break
            name = action.name

            if name == 'presentation':
                background_id = action.details.get('asset_id', -1)
            elif name == 'word_grid':
                # word_grid carries its own background_id in the action's
                # own details (set from script args at dispatch time, see
                # engine.py) -- a completely separate field from every other
                # screen's shared session.engine.panel.background_id.
                background_id = action.details.get('background_id', -1)
            else:
                background_id = session.engine.panel.background_id
            _record(backgrounds, resources, background_id)
            if name == 'dialogue':
                portrait = session.engine.dialogue_animation.portrait
                _record(portraits, resources, portrait.asset_id if portrait else None)
            elif name == 'character_picker':
                picker = session.engine.character_picker
                for character in picker.characters:
                    variants = session.engine.character_art_variants.get(character, [-1])
                    _record(portraits, resources, variants[0])

            if name == 'dialogue':
                if not session.engine.dialogue_animation.complete:
                    session.answer()
                    session.tick(3000)
                session.answer()
            elif name == 'presentation':
                session.tick(5000)
                if session.pending and session.pending.name == 'presentation':
                    session.answer()
            elif name == 'message_panel':
                session.tick(6000)
                if session.pending and session.pending.name == 'message_panel':
                    session.answer()
            elif name == 'loading':
                session.tick(3500)  # LoadingScreen self-clears past 3000ms.
            elif name == 'download_poll':
                session.tick(1000)  # the failed poll download returns after a fixed second
            elif name == 'choice':
                recent_choices.append(action.details.get('text'))
                if _cycling(recent_choices[-24:]):
                    stop_reason, steps = 'stopped_at:repeated_choice_loop', step
                    break
                enabled = action.details['enabled']
                index = next((i for i, ok in enumerate(enabled) if ok), None)
                if index is None:
                    stop_reason, steps = 'choice_with_no_enabled_options', step
                    break
                session.answer(index)
            elif name == 'character_picker':
                session.answer(0)
                session.answer(None)
            elif name == 'text_input':
                session.answer('Test')
            elif name == 'vm_pause':
                session.answer()
            elif name in ('finished', 'episode_exit'):
                stop_reason, steps = name, step
                break
            else:
                # word_game, word_grid, football, unhandled_yield: real
                # interactive minigames or a genuine engine gap -- not
                # generically drivable, but everything up to here (usually
                # most of the episode) is already captured above.
                stop_reason, steps = f'stopped_at:{name}', step
                break
        except (VMError, ContentError, ValueError) as error:
            stop_reason, steps = f'{type(error).__name__}: {error}', step
            break
    return dict(backgrounds=backgrounds, portraits=portraits, stop_reason=stop_reason, steps=steps)


def classify(sizes, *, reference_width=None, reference_size=None):
    hd = standard = errors = 0
    for value in sizes.values():
        if isinstance(value, str):
            errors += 1
        elif reference_width is not None:
            hd += value[0] > reference_width
            standard += value[0] <= reference_width
        else:
            is_hd = value[0] > reference_size[0] or value[1] > reference_size[1]
            hd += is_hd
            standard += not is_hd
    return dict(hd=hd, standard=standard, decode_errors=errors)


def audit(directory, episode_ids=None):
    """episode_ids restricts the audit to that subset (by sha256); None
    audits every episode in the library."""
    results = []
    with ContentLibrary(directory) as library:
        for record in library.episodes:
            if episode_ids is not None and record['sha256'] not in episode_ids:
                continue
            entry = dict(id=record['id'], name=record['name'])
            try:
                resources = library.open_episode(record['id'])
                outcome = drive_episode(resources)
                entry.update(outcome)
                entry['backgrounds_by_density'] = classify(outcome['backgrounds'], reference_width=ANDROID_BACKGROUND_WIDTH)
                entry['portraits_by_density'] = classify(outcome['portraits'], reference_size=ANDROID_MASK_SIZE)
            except Exception as error:
                entry['stop_reason'] = f'{type(error).__name__}: {error}'
                entry['backgrounds'] = entry['portraits'] = {}
                entry['backgrounds_by_density'] = entry['portraits_by_density'] = dict(hd=0, standard=0, decode_errors=0)
            results.append(entry)
    return results


def summarize(results):
    stop_reasons = Counter()
    episodes_with_hd_background = episodes_with_hd_portrait = 0
    total_hd_backgrounds = total_hd_portraits = total_decode_errors = 0
    error_types = ('VMError', 'ContentError', 'ValueError', 'RuntimeError',
                  'KeyError', 'AttributeError', 'TypeError', 'IndexError')
    for entry in results:
        bucket = entry['stop_reason'].split(':')[0].strip()
        stop_reasons['error' if bucket in error_types else bucket] += 1
        bg, pf = entry['backgrounds_by_density'], entry['portraits_by_density']
        episodes_with_hd_background += bg['hd'] > 0
        episodes_with_hd_portrait += pf['hd'] > 0
        total_hd_backgrounds += bg['hd']
        total_hd_portraits += pf['hd']
        total_decode_errors += bg['decode_errors'] + pf['decode_errors']
    return dict(episodes=len(results), stop_reasons=dict(stop_reasons),
               episodes_with_at_least_one_hd_background=episodes_with_hd_background,
               episodes_with_at_least_one_hd_portrait=episodes_with_hd_portrait,
               total_unique_hd_backgrounds=total_hd_backgrounds,
               total_unique_hd_portraits=total_hd_portraits,
               total_decode_errors=total_decode_errors)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--library', type=Path)
    source.add_argument('--apk', type=Path)
    parser.add_argument('--episodes', type=Path, nargs='+', default=[],
                        help='HD .exp files or directories (only used with --apk).')
    parser.add_argument('--hd-ipa', type=Path, default=None,
                        help='Optional HD (iPad) ipa, for real HD-native shared assets (only used with --apk).')
    parser.add_argument('--out', type=Path, help='Write full per-episode JSON here.')
    args = parser.parse_args()
    pygame.display.init()
    if args.library:
        results = audit(args.library)
    else:
        with tempfile.TemporaryDirectory(prefix='shs-runtime-hd-audit-') as temporary:
            directory = Path(temporary) / 'library'
            manifest = import_game(args.apk, args.episodes, directory, hd_ipa_path=args.hd_ipa)
            # Restrict the summary to the externally-supplied HD episodes --
            # not the Android APK's own bundled standard episodes or the
            # built-in Football Star, which aren't what this tool is
            # checking and would dilute the HD-density statistics.
            hd_ids = {e['sha256'] for e in manifest['episodes']
                     if 'apk_member' not in e and e.get('builtin') != 'football-star'}
            results = audit(directory, episode_ids=hd_ids)
    summary = summarize(results)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if args.out:
        args.out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f'Full per-episode detail written to {args.out}')
    return bool(summary['total_decode_errors']) or 'error' in summary['stop_reasons']


if __name__ == '__main__':
    raise SystemExit(main())
