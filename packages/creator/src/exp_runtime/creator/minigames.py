"""Encode authored minigame tables using the recovered SHS native ABI."""
from exp_runtime.brew_services import ANGLED, BREW_CATCH, ORBIT, SIDEWAYS
from exp_runtime.shs11_services import SHS11_MEMORY, SHS11_REFLEX

from .model import ProjectError

MEMORY_FIELDS = ('bonus', 'points', 'letter_ms', 'limit_ms')
REFLEX_FIELDS = ('least_right', 'gauge', 'bonus', 'points', 'right', 'wrong', 'skull', 'one_bar', 'two_bars', 'three_bars',
                 'skulls', 'flash_ms', 'hold_ms')


def integer(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise ProjectError(f'{name} must be an integer from {low} to {high}')
    return value


def words(values, name, minimum=1):
    if (not isinstance(values, list) or not minimum <= len(values) <= 256
            or any(not isinstance(v, str) or not v or '|' in v or '\0' in v for v in values)):
        raise ProjectError(f'{name} needs {minimum}–256 nonempty strings without pipes or NULs')
    return values


def validate_shs11(kind, p):
    """shs11_games.py's rounds, as a story's table holds them (ENGINE_ABI.md 5.4)."""
    name = 'Memory' if kind == 'shs11_memory' else 'Reflex'
    integer(p['seconds'], 1, 3276, f'{name} seconds')
    integer(p['target'], 1, 32767, f'{name} target')
    rounds = p['rounds']
    if not isinstance(rounds, list) or not 1 <= len(rounds) <= 256 or any(not isinstance(r, dict) for r in rounds):
        raise ProjectError(f'{name} needs 1–256 rounds')
    fields = MEMORY_FIELDS if kind == 'shs11_memory' else REFLEX_FIELDS
    for i, r in enumerate(rounds, 1):
        expected = set(fields) | ({'cue', 'word'} if kind == 'shs11_memory' else set())
        if set(r) != expected:
            raise ProjectError(f'{name} round {i} needs exactly {sorted(expected)}')
        for field in fields:
            integer(r[field], 0, 32767, f'{name} round {i} {field}')
        if kind == 'shs11_memory':
            word = r['word']
            if not isinstance(r['cue'], str) or not r['cue'] or '\0' in r['cue']:
                raise ProjectError(f'Memory round {i} needs a cue')
            if not isinstance(word, str) or not 1 <= len(word) <= 9 or not word.isascii() or not word.isalpha() or not word.isupper():
                raise ProjectError(f'Memory round {i}: the word is 1 to 9 capital letters, for its nine tiles')
            if r['limit_ms'] < 1:
                raise ProjectError(f'Memory round {i} needs a time limit')
        else:
            if sum(r[odds] for odds in ('one_bar', 'two_bars', 'three_bars', 'skulls')) > 100:
                raise ProjectError(f'Reflex round {i}: its four odds are out of 100')
            if r['gauge'] < 1 or r['hold_ms'] < 1:
                raise ProjectError(f'Reflex round {i} needs a gauge and a hold time')


CATCH_KINDS = {'angled': ANGLED, 'sideways': SIDEWAYS, 'orbit': ORBIT}
CATCH_ADDON, CATCH_SPEC = 'shsbrew', 26998       # the add-on's catch art and its spec (desktop_brew_catch)
CATCH_MOST = 20                                  # brew_catch.MAX_ITEMS


def brew_catch_sizes(library):
    """{picture: (width, height)} of every catch picture the library's BREW add-on draws, {} without one."""
    import json
    found = library.addon(CATCH_ADDON) if library is not None and hasattr(library, 'addon') else None
    if found is None or CATCH_SPEC not in found[1].entries:
        return {}
    pictures = json.loads(found[1].read(CATCH_SPEC)).get('catch', {}).get('pictures', {})
    return {int(picture): (entry[1], entry[2]) for picture, entry in pictures.items()}


def validate_catch(p):
    """The catch game's settings (brew_catch.CatchGame.opened), apart from the pictures' sizes (catch_sizes)."""
    if p['kind'] not in CATCH_KINDS:
        raise ProjectError('The catch game\'s kind is angled, sideways or orbit')
    integer(p['target'], 1, 32767, 'Catch target')
    integer(p['interval_ms'], 1, 32767, 'Catch interval')
    integer(p['speed'], 1, 32767, 'Catch speed')
    integer(p['spread'], 0, 32767, 'Catch spread')
    integer(p['chance'], 0, 100, 'Catch chance')
    integer(p['angle'], 0, 89, 'Catch angle')
    integer(p['player'], 0, 32767, 'Catch player picture')
    items = p['items']
    if not isinstance(items, list) or not 1 <= len(items) <= CATCH_MOST or any(not isinstance(i, dict) for i in items):
        raise ProjectError(f'The catch game needs 1–{CATCH_MOST} kinds of item')
    for n, item in enumerate(items, 1):
        if set(item) != {'value', 'picture', 'count'}:
            raise ProjectError(f'Catch item {n} needs exactly value, picture and count')
        integer(item['value'], -32768, 32767, f'Catch item {n} value')
        integer(item['picture'], 0, 32767, f'Catch item {n} picture')
        integer(item['count'], 0, 32767, f'Catch item {n} count')
    if not any(item['count'] for item in items):
        raise ProjectError('The catch game needs at least one item to come')
    if not isinstance(p['sizes'], dict):
        raise ProjectError('Catch sizes are {picture: [width, height]}')


def catch_sizes(p, library_sizes):
    """[(picture, width, height)] for the player and each item: the node's own sizes, else the add-on's."""
    own = {}
    for picture, size in p['sizes'].items():
        if (not isinstance(size, list) or len(size) != 2 or any(type(v) is not int or not 1 <= v <= 240 for v in size)):
            raise ProjectError('A catch picture\'s size is [width, height], 1 to 240 each')
        own[int(picture)] = tuple(size)
    result = []
    for picture in dict.fromkeys([p['player'], *(item['picture'] for item in p['items'])]):
        size = own.get(picture, library_sizes.get(picture))
        if size is None:
            raise ProjectError(f'The catch game shows picture {picture}, which the shsbrew add-on doesn\'t draw: choose the '
                               'library holding it, or another picture')
        result.append((picture, *size))
    return result


def catch_cuts(p, branches):
    """The scores where the story after the game parts (the skip prompt's stretches, ENGINE_ABI.md 5.5): from `branches`, the
    (operator, value) of each branch on its result, each stretch starting where a comparison changes; and the target."""
    starts = {p['target']}
    for operator, value in branches:
        if type(value) is not int:
            continue
        starts.update({'<': (value,), '>=': (value,), '<=': (value + 1,), '>': (value + 1,)}.get(operator, (value, value + 1)))
    return sorted(s for s in starts if 0 < s <= p['target'])


def emit_catch(asm, p, sizes, cuts):
    kind = CATCH_KINDS[p['kind']]
    spread, chance, angle = ((p['spread'], 0, 0) if kind == ORBIT else (0, p['chance'], p['angle']) if kind == ANGLED
                             else (0, p['chance'], 0))
    items = [len(p['items'])] + [word for item in p['items'] for word in (item['value'], item['picture'], item['count'])]
    asm.call(BREW_CATCH, kind, p['target'], p['interval_ms'], p['speed'], spread, chance, angle, p['player'], asm.table(items),
             asm.table([word for size in sizes for word in size]), len(sizes), asm.table([len(cuts), *cuts]))


def validate(kind, p):
    if kind == 'brew_catch':
        validate_catch(p)
    elif kind in ('shs11_memory', 'shs11_reflex'):
        validate_shs11(kind, p)
    elif kind == 'word_game':
        words(p['good'], 'Positive words', 2); words(p['bad'], 'Negative words', 3)
        integer(p['duration_ms'], 1, 32767, 'Word-game duration')
        integer(p['refresh_ms'], 0, 32767, 'Word-game refresh')
    elif kind == 'football':
        if not isinstance(p['plans'], list) or len(p['plans']) != 6:
            raise ProjectError('Football needs six interleaved offense/defense play tables')
        for i, plan in enumerate(p['plans']):
            if not isinstance(plan, list) or not 1 <= len(plan) <= 10:
                raise ProjectError('Each football table needs 1–10 plays')
            ordinary = False
            for row in plan:
                if not isinstance(row, list) or len(row) != 4:
                    raise ProjectError('Play rows are [code, yards, variation, weight]')
                for value in row: integer(value, -32768, 32767, 'Football play value')
                code, yards, variation, weight = row
                allowed = {-1, -2, -3, -4, -5, -6} if i % 2 else {1, 2, 3, 4, 5, 6, 7}
                if code not in allowed or variation < 0 or weight < 0:
                    raise ProjectError('Invalid football play code, variation or weight')
                ordinary |= weight > 0 and code in ({-1, -2, -3, -4, -5} if i % 2 else {1, 2, 3, 4, 5})
            if not ordinary or sum(row[3] for row in plan) > 32767:
                raise ProjectError('Football tables need a positive ordinary outcome and bounded total weight')
        if len(p['instructions']) != 6:
            raise ProjectError('Football needs six instruction strings')
        words(p['instructions'], 'Football instructions', 6)
        for key in ('first_seconds', 'second_seconds'):
            integer(p[key], 0, 32767, key)
        if not (p['first_seconds'] or p['second_seconds']):
            raise ProjectError('At least one football half must have positive duration')
        for key in ('home_team', 'away_team'): integer(p[key], 1, 9, key)
        for key in ('home_position', 'away_position'): integer(p[key], 1, 99, key)
        for key in ('home_score', 'away_score'): integer(p[key], 0, 32767, key)
    elif kind == 'grid':
        integer(p['seconds'], 1, 32767, 'Grid duration')
        integer(p['target'], 1, 32767, 'Grid target')
        integer(p['round_ms'], 1, 32767, 'Grid board duration')
        integer(p['bonus_ms'], 0, 32767, 'Grid time bonus')
        if not isinstance(p['problems'], list) or not 1 <= len(p['problems']) <= 256:
            raise ProjectError('Grid needs 1–256 problems')
        if not isinstance(p['tutorials'], list) or len(p['tutorials']) > 256:
            raise ProjectError('Grid supports at most 256 tutorial records')
        if not isinstance(p['symbols'], list) or len(p['symbols']) > 256:
            raise ProjectError('Grid supports at most 256 picture symbols')
        symbols = set()
        for row in p['symbols']:
            if not isinstance(row, list) or len(row) != 2 or not isinstance(row[0], str) or len(row[0]) != 1:
                raise ProjectError('Picture symbols are [single Latin-1 character, image ID]')
            integer(ord(row[0]), 1, 255, 'Picture symbol')
            integer(row[1], 0, 32767, 'Picture image ID')
            if row[0] in symbols: raise ProjectError('Picture symbols must be unique')
            symbols.add(row[0])
        for tutorial, records in ((False, p['problems']), (True, p['tutorials'])):
            for record in records:
                if not isinstance(record, dict): raise ProjectError('Grid records must be objects')
                width = integer(record.get('width'), 1, 5, 'Grid width')
                height = integer(record.get('height'), 1, 5, 'Grid height')
                allowed = ({'title', 'body', 'position', 'tap_to_advance', 'hide_board', 'width', 'height',
                            'heading', 'prompt', 'words', 'highlight', 'fixed_board', 'show_hints', 'animate',
                            'timed', 'failure_next', 'success_next', 'minimum_starts'} if tutorial else
                           {'width', 'height', 'heading', 'prompt', 'words', 'alphabet', 'highlight',
                            'advance_after_one', 'minimum_starts', 'id'})
                if set(record) - allowed: raise ProjectError('Unknown grid record fields')
                for key in ('title', 'body', 'heading', 'prompt', 'alphabet', 'fixed_board'):
                    if key in record and (not isinstance(record[key], str) or '\0' in record[key]):
                        raise ProjectError(f'Grid {key} must be text without NULs')
                for key in ('tap_to_advance', 'hide_board', 'highlight', 'show_hints', 'animate', 'timed', 'advance_after_one'):
                    if key in record and type(record[key]) is not bool:
                        raise ProjectError(f'Grid {key} must be true or false')
                for key in ('position', 'id'):
                    if key in record: integer(record[key], -32768, 32767, f'Grid {key}')
                targets = record.get('words', [])
                if not isinstance(targets, list): raise ProjectError('Grid words must be a list')
                if targets: words(targets, 'Grid target words')
                if not targets and not (tutorial and record.get('tap_to_advance') and not record.get('timed')):
                    raise ProjectError('Playable grids require target words')
                if any(len(w) > width * height for w in targets):
                    raise ProjectError('Grid targets cannot exceed the number of cells')
                integer(record.get('minimum_starts', 1), 1, width * height, 'Minimum starting cells')
                if tutorial:
                    fixed = record.get('fixed_board', '')
                    if len(fixed.split('\n')) != height or any(len(row) != width for row in fixed.split('\n')):
                        raise ProjectError('Tutorial board needs fixed-width rows separated by a single newline')
                    for key in ('failure_next', 'success_next'):
                        value = record.get(key, -2)
                        if not (value == -2 or (key == 'failure_next' and value == -1 and not record.get('timed'))
                                or type(value) is int and 0 <= value < len(records)):
                            raise ProjectError('Tutorial branches must identify a tutorial or -2 (finish)')
                else:
                    alphabet = record.get('alphabet', '')
                    if not alphabet or width * height < 2 or any(c not in alphabet for word in targets for c in word):
                        raise ProjectError('Grid alphabet and dimensions must be able to form the targets')


def emit(asm, kind, p, text, character):
    """Return the result in the native R register; caller stores it explicitly."""
    if kind in ('shs11_memory', 'shs11_reflex'):
        table = []
        for i, r in enumerate(p['rounds']):
            if kind == 'shs11_memory':
                table += [text(f'rounds.{i}.cue', r['cue']), text(f'rounds.{i}.word', r['word'])]
                table += [r[field] for field in MEMORY_FIELDS]
            else:
                table += [r[field] for field in REFLEX_FIELDS]
        asm.call(SHS11_MEMORY if kind == 'shs11_memory' else SHS11_REFLEX, p['seconds'], p['target'], len(p['rounds']),
                 asm.table(table), character() or -1)
    elif kind == 'word_game':
        asm.call(71, -1, text('text'), asm.text('|'.join(text(f'good.{i}', v, raw=True) for i, v in enumerate(p['good']))),
                 asm.text('|'.join(text(f'bad.{i}', v, raw=True) for i, v in enumerate(p['bad']))), p['duration_ms'], character('character'), 0, p['refresh_ms'])
    elif kind == 'football':
        tables = [asm.table([word for row in plan for word in row] + [0x7ffe]) for plan in p['plans']]
        instructions = asm.table([text(f'instructions.{i}', value) for i, value in enumerate(p['instructions'])])
        asm.call(94, p['first_seconds'], p['second_seconds'], *tables, instructions, int(p['start_offense']),
                 p['home_team'], p['away_team'], p['home_position'], p['away_position'], p['home_score'],
                 p['away_score'], int(p['allow_block']), int(p['pass_bonus']), int(p['run_bonus']), int(p['coach']),
                 text('extra_offense') if p['extra_offense'] else -1,
                 text('extra_defense') if p['extra_defense'] else -1)
    else:
        problems = []
        for i, r in enumerate(p['problems']):
            ref = lambda key, default='': text(f'problems.{i}.{key}', r.get(key, default))
            # A trailing delimiter protects the native splitter's final one-byte word.
            targets = '|'.join(text(f'problems.{i}.words.{j}', w, raw=True) for j, w in enumerate(r['words'])) + '|'
            problems.extend((r['width'], r['height'], ref('heading'), ref('prompt'), asm.text(targets), ref('alphabet'),
                             int(r.get('highlight', False)), int(r.get('advance_after_one', False)),
                             r.get('minimum_starts', 1), r.get('id', 1001)))
        problem_ref = asm.table(problems)
        symbols = asm.table([item for char, resource in p['symbols'] for item in (ord(char), resource)])
        tutorials = []
        for i, r in enumerate(p['tutorials']):
            ref = lambda key, default='': text(f'tutorials.{i}.{key}', r.get(key, default))
            targets = '|'.join(text(f'tutorials.{i}.words.{j}', w, raw=True) for j, w in enumerate(r.get('words', []))) + '|'
            tutorials.extend((ref('title'), ref('body'), r.get('position', 0), int(r.get('tap_to_advance', False)),
                              int(r.get('hide_board', False)), r['width'], r['height'], ref('heading'), ref('prompt'),
                              asm.text(targets), int(r.get('highlight', False)), ref('fixed_board'),
                              int(r.get('show_hints', False)), int(r.get('animate', True)), int(r.get('timed', False)),
                              r.get('failure_next', -2), r.get('success_next', -2)))
        tutorial_ref = asm.table(tutorials)
        asm.call(96, p['seconds'], p['target'], p['round_ms'], p['bonus_ms'], p['variant'], p['background'],
                 character('left_character'), p['left_expression'], character('right_character'), p['right_expression'],
                 int(p['shuffle']), len(p['problems']), problem_ref, int(p['feedback']), text('success'), text('failure'),
                 len(p['symbols']), symbols, len(p['tutorials']), tutorial_ref)
