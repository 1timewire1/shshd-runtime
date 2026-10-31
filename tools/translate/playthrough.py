"""Play an `.exp` headlessly in the production Session and record what the player sees, to compare a translation with
its smartphone twin.

    python tools/translate/playthrough.py EPISODE.exp [--answers 0,1,...] [--name Matt] [--seed 1] [--out FILE.json]

Every choice takes the next answer (then 0), text input gets --name, a portrait picker confirms its first look; title
cards, messages and the loading screen are acknowledged after their reading time. New Rules' minigame arena (with
the addon's library) is played by a bot that presses OK every few frames and turns down tutorials. The record lists dialogue lines
(speaker, text, character, expression), choices (title, text, options), title cards, messages and the episode exit.
"""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
import sys

from exp_runtime.content import EpisodeResources, digest
from exp_runtime.decode.bytecode import decode_program
from exp_runtime.exp import ExpArchive
from exp_runtime.runtime import Session
from exp_runtime.vm import VMError

LINKED_SCRIPT = EpisodeResources.LINKED_SCRIPT


def session(data, game='shs', addons=(), arena=True):
    """`addons`: the archives (ExpArchive) of the addons the episode declares, whose resources it also has, and whose
    linked script (New Rules' minigame library) the episode runs beside. `arena`: the player's arena switch."""
    archive = ExpArchive(data)
    programs = archive.programs()

    def linked_program():
        for addon in addons:
            if LINKED_SCRIPT in addon.entries:
                program = decode_program(addon.read(LINKED_SCRIPT))
                return program if program.previous_flag else None
        return None
    resources = SimpleNamespace(library=SimpleNamespace(game_id=game, directory=Path('.')), record={'titles': ['']},
                                identity=dict(profile='translate', episode_sha256=digest(data)),
                                program=programs.__getitem__, linked_program=linked_program,
                                exists=lambda key: key in archive.entries or any(key in a.entries for a in addons))
    s = Session(resources, ephemeral=True)
    s.nr_arena = arena
    return s


def play(data, answers=(), name='Matt', limit=5000, seed=1, addons=(), arena=True):
    """The record; a VM error ends it with an `error` event."""
    s, record = session(data, addons=addons, arena=arena), []
    s.engine.random.state = seed                # the native clock seed, fixed so two runs (and two versions) agree
    try:
        steps(s, list(answers), name, limit, record)
    except VMError as error:
        record.append(dict(kind='error', message=str(error)))
    return record


def steps(s, answers, name, limit, record):
    action = s.advance()
    for _ in range(limit):
        while s.transitioning:
            action = s.tick(s.engine.scene_transition.duration_ms)
        if action is None or s.pending is None:
            break
        kind, details = action.name, action.details
        if kind == 'episode_exit':
            record.append(dict(kind='exit'))
            break
        if kind == 'dialogue':
            record.append(dict(kind='line', speaker=details.get('speaker'), text=details.get('text'),
                               character=details.get('character_id'), expression=details.get('expression'),
                               presentation=details.get('presentation_mode')))
            if not s.engine.dialogue_animation.complete:
                s.answer(); s.tick(2000)
            action = s.answer()
        elif kind == 'choice':
            record.append(dict(kind='choice', title=details.get('title'), text=details.get('text'),
                               options=details.get('options')))
            if not s.choice_ready:
                s.tick(250)
            value = answers.pop(0) if answers else 0
            enabled = [i for i, on in enumerate(details['enabled']) if on]
            action = s.answer(value if value in enabled else enabled[0])
        elif kind == 'text_input':
            record.append(dict(kind='input', title=details.get('title'), prompt=details.get('prompt')))
            action = s.answer(name)
        elif kind == 'character_picker':
            record.append(dict(kind='picker'))
            action = s.answer(None)
        elif kind in ('presentation', 'message_panel', 'survey_confirmation', 'loading', 'download_poll'):
            if kind == 'presentation':
                record.append(dict(kind='title', title=details.get('title'), subtitle=details.get('subtitle')))
            elif kind == 'message_panel':
                panel = s.engine.message_panel
                record.append(dict(kind='message', title=panel.title, text=panel.text))
            action = s.tick(4000)
            if s.pending is not None and s.pending.name == kind and kind != 'loading':
                action = s.answer()
        elif kind in ARENA:
            action = arena_game(s, record)
        elif kind in ('word_game', 'football', 'word_grid'):
            record.append(dict(kind=kind))
            for _ in range(1000):
                if s.pending is None or s.pending.name != kind:
                    break
                action = s.tick(1000)
                if s.pending is not None and s.pending.name == 'football':
                    action = s.answer(None)
        else:
            record.append(dict(kind='stop', name=kind, details={k: v for k, v in details.items() if k != 'raw'}))
            break
        if action is None:
            action = s.pending


ARENA = ('arena_frame', 'arena_menu', 'arena_info')
ARENA_FRAME_MS = 33
ARENA_OK_EVERY = 6                      # frames between the bot's OK presses
ARENA_FRAMES = 20000                    # about 11 minutes of play, more than any game runs


def arena_game(s, record):
    """One stretch of New Rules' minigame arena: frames until the story has the screen again. Its menus (a tutorial's
    offer) take "no" where there is one, its info boxes are acknowledged, and the record notes what was shown and the
    result the library leaves in B."""
    event = dict(kind='arena', menus=[], info=[], frames=0)
    record.append(event)
    action = s.pending
    while action is not None and action.name in ARENA and event['frames'] < ARENA_FRAMES:
        if action.name == 'arena_menu':
            options = action.details['options']
            event['menus'].append(dict(title=action.details['title'], options=options))
            action = s.answer(options.index('no') if 'no' in options else 0)
        elif action.name == 'arena_info':
            event['info'].append(action.details['text'])
            action = s.answer()
        else:
            if s.engine.nr_arena is not None and event['frames'] % ARENA_OK_EVERY == 0:
                s.arena_press(-5)
            action = s.tick(ARENA_FRAME_MS)
            event['frames'] += 1
        action = action if action is not None else s.pending
    event['b'] = s.vm.b
    return action


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('episode', type=Path)
    parser.add_argument('--answers', default='')
    parser.add_argument('--name', default='Matt')
    parser.add_argument('--seed', type=int, default=1, help='the random generator state at the start')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    record = play(args.episode.read_bytes(), [int(a) for a in args.answers.split(',') if a], args.name,
                  seed=args.seed)
    if args.out:
        args.out.write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding='utf-8')
    for item in record:
        print(json.dumps(item, ensure_ascii=False)[:160])
    print(len(record), 'events', file=sys.stderr)
