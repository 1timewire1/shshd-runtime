"""Authoring controls backed by the recovered KiWi host contracts.

Defaults are authored examples, not extracted game content. They are shared
by the editor and the API; validation never fills in an unknown native call.
"""
from copy import deepcopy

NAMES = dict(dialogue='Dialogue', choice='Choice', background='Background', set='Set variable',
             branch='Condition', music='Music', sound='Sound effect', stop_audio='Stop audio',
             relationship='Relationship', score='Score / property', input='Text input',
             text_branch='Text answer condition', title='Title card', message='Message',
             notice='Dialogue notification', emphasis='Emphasize dialogue', scene_label='Scene label',
             pan='Background pan', transition='Screen transition', close_dialogue='Close dialogue',
             random='Random variable', quest='Set quest', journal_updated='Journal updated',
             start_calendar='Start calendar', calendar_back='Back to the calendar', schedule_event='Schedule event',
             cancel_event='Cancel event', set_clock='Set the clock', skip_ahead='Skip ahead', run_due='Run due events',
             call_scene='Run a scene and come back', return_scene='Return', nr_arena='New Rules minigame',
             minigames_available='Real minigames?', cutscene_available='Cutscenes?', cutscene='Storyboard cutscene', x360_slot='X360 slot machine', x360_leash='X360 leash game', x360_puzzle='X360 jewel puzzle', x360_diss='X360 Diss Practice', x360_battle='X360 Diss Battle', word_game='Timed word choices', football='Football (SHS)',
             grid='Word / picture grid (SHS)', shs11_memory="Memory (SHS '11)", shs11_reflex="Reflex (SHS '11)", brew_catch='Catch game (BREW)', scene='Scene link',
             flag='Property flag', speakers='Player / narrator', set_text='Set text', text_default='Text default',
             expression_default='Default expression', character_art='Character art', character_name='Rename character',
             picker='Choose a look', vibrate='Vibrate',
             faceplace='Faceplace (SHS HD)', faceplace_post='Faceplace post (SHS HD)',
             faceplace_link='Faceplace link / photo (SHS HD)', tree='Decision Tree (SHS HD)',
             tree_node='Tree scene (SHS HD)', tree_result='Tree result (SHS HD)', append_text='Append text',
             loading='Loading screen (SHS)', open_url='Open a link', survey='Survey (SHS)',
             end='End episode', native='Native bytecode block')

DEFAULTS = {
    # shshd-runtime presentation (SHS only; the episode declares them in resource 3, SCHEMA.md "Presentation
    # extension"): a second speaker and their expression, a named line's bubble colour (0 its own, 1 blue, 2 pink,
    # 3 gray), an emoticon over the speaker (model.EMOTICONS, 0 none), and music's loop after its intro (-1 none).
    'dialogue': {'partner': '', 'partner_expression': 0, 'bubble': 0, 'emoticon': 0},
    'choice': {'shuffle': False}, 'background': {'variant': 0},
    'set': {'expression': ''}, 'branch': {'expression': ''},
    'music': {'resource': 8201, 'loop': True, 'then_loop': -1}, 'sound': {'resource': 8001},
    'stop_audio': {'channel': 0},
    'relationship': {'operation': 'add', 'value': 1, 'romantic': False, 'hide': False, 'result': 'relationship'},
    'score': {'owner': 0, 'key': 400, 'operation': 'add', 'value': 1, 'notification': '', 'result': 'score'},
    'input': {'prompt': 'Enter an answer.', 'default': '', 'result': 'answer'},
    'text_branch': {'variable': 'answer', 'equals': 'Answer'},
    'title': {'subtitle': '', 'background': -1, 'flag': 0},
    'message': {'title': '', 'flag': 0}, 'notice': {}, 'emphasis': {},
    'scene_label': {'icon': -1, 'icon_expression': ''}, 'pan': {'automatic': True, 'alignment': 2},
    # shshd-runtime: the quest journal the pause menu shows (presentation `journal`; owner, 2026-11-17). A quest's lines are the
    # node's text; an empty title takes the quest off. Journal updated is a scene label with its own words and a sound.
    'quest': {'number': 0, 'title': 'A quest'}, 'journal_updated': {'icon': -1, 'sound': -1},
    # shshd-runtime: calendars (calendar.py). Times are minutes after midnight; day and minute are expressions.
    'start_calendar': {'calendar': ''}, 'calendar_back': {},
    'schedule_event': {'calendar': '', 'event': '', 'target': '', 'name': '', 'icon': -1, 'duration': -1, 'first': False,
                       'day': 'day()', 'minute': ''},
    'cancel_event': {'calendar': '', 'event': '', 'all': True}, 'set_clock': {'minute': '540'},
    'skip_ahead': {'to': 'time', 'minute': '900'}, 'run_due': {}, 'call_scene': {'target': ''}, 'return_scene': {},
    # shshd-runtime: New Rules' minigame library through its arena, else the translators' fallback (nr_arena.py).
    'nr_arena': {'game': 'rhythm', 'target': 6, 'intro': '`Rhythm`\n\nHit the good notes, not the bent ones.',
                 'good': ['beat', 'groove', 'flow', 'bass', 'tempo', 'rhythm'],
                 'bad': ['bent note', 'off-key', 'screech', 'clunk', 'sour note', 'static'],
                 'rhymes': [['cat', 'hat', 'bat', 'rat'], ['day', 'play', 'way', 'say'], ['night', 'light', 'bright', 'fight'],
                            ['cool', 'school', 'rule', 'pool'], ['beat', 'street', 'heat', 'feet'], ['flow', 'show', 'go', 'slow']],
                 'result': 'arena_score'},
    'transition': {'selector': 0}, 'close_dialogue': {},
    'random': {'bound': 2, 'result': 'roll'},
    'minigames_available': {'result': 'real_minigames', 'for': ''}, 'cutscene_available': {'result': 'real_cutscene'}, 'cutscene': {'spec': 0}, 'x360_slot': {'result': 'slot_points'}, 'x360_leash': {'result': 'leash_won'}, 'x360_puzzle': {'result': 'puzzle_score'}, 'x360_diss': {'result': 'diss_score', 'tutorial': 0},
    'x360_battle': {'result': 'battle_grade', 'bonus': 0, 'tutorial': 1,
                    'rounds': [{'target': 'crash', 'words': ['trash', 'chatter', 'ride', 'rat']},
                               {'target': 'cool', 'words': ['school', 'shoes', 'ladle', 'store']}]},
    'word_game': {'good': ['Clear', 'Calm'], 'bad': ['Late', 'Lost', 'Loud'],
                  'duration_ms': 10000, 'refresh_ms': 1000, 'result': 'word_score'},
    'football': {'first_seconds': 30, 'second_seconds': 30,
                 'plans': [[[1, 5, 2, 1]], [[-1, 5, 2, 1]]] * 3,
                 'instructions': ['Choose a play.'] * 6, 'start_offense': True,
                 'home_team': 1, 'away_team': 2, 'home_position': 20, 'away_position': 20,
                 'home_score': 0, 'away_score': 0, 'allow_block': False,
                 'pass_bonus': False, 'run_bonus': False, 'coach': False,
                 'extra_offense': '', 'extra_defense': '', 'result': 'football_margin',
                 'home_result': '', 'away_result': ''},
    'grid': {'seconds': 30, 'target': 1, 'round_ms': 10000, 'bonus_ms': 1000,
             'background': -1, 'variant': 0, 'left_character': '', 'right_character': '',
             'left_expression': 0, 'right_expression': 0, 'shuffle': False,
             'feedback': True, 'success': 'Well done!', 'failure': 'Try again.',
             'problems': [{'width': 3, 'height': 3, 'heading': 'Find a word',
                           'prompt': 'Connect adjacent letters.', 'words': ['CAT'],
                           'alphabet': 'CAT', 'highlight': True, 'advance_after_one': True,
                           'minimum_starts': 1, 'id': 1001}],
             'symbols': [], 'tutorials': [], 'result': 'grid_passed', 'part_score': ''},
    # shshd-runtime: SHS '11's games (ENGINE_ABI.md 5.4). A round's fields are the words of its table there.
    'shs11_memory': {'seconds': 60, 'target': 200,
                     'rounds': [{'cue': 'A word for a small, mischievous helper.', 'word': 'ELF', 'bonus': 20, 'points': 10,
                                 'letter_ms': 200, 'limit_ms': 2000},
                                {'cue': 'A pet that purrs.', 'word': 'CAT', 'bonus': 20, 'points': 10,
                                 'letter_ms': 200, 'limit_ms': 2000}],
                     'result': 'memory_result'},
    'shs11_reflex': {'seconds': 60, 'target': 200,
                     'rounds': [{'least_right': 5, 'gauge': 10, 'bonus': 20, 'points': 5, 'right': 13, 'wrong': 3, 'skull': 8,
                                 'one_bar': 25, 'two_bars': 40, 'three_bars': 20, 'skulls': 15,
                                 'flash_ms': 300, 'hold_ms': 2100}],
                     'result': 'reflex_result'},
    # shshd-runtime: the BREW games' catch game (ENGINE_ABI.md 5.5), with the settings most of the '08 Campaign's open with: items
    # and the player are BREW picture numbers, which the shsbrew add-on draws (sizes: {picture: [width, height]}, read from it).
    'brew_catch': {'kind': 'angled', 'target': 45, 'interval_ms': 520, 'speed': 330, 'spread': 50, 'chance': 65, 'angle': 40,
                   'player': 109, 'items': [{'value': 3, 'picture': 149, 'count': 25}, {'value': -3, 'picture': 156, 'count': 15}],
                   'sizes': {}, 'result': 'catch_score'},
    'scene': {},
    'flag': {'owner': 0, 'key': 400, 'bit': 0, 'value': True},
    'speakers': {'player': '', 'narrator': ''},
    'set_text': {'key': '$NAME'}, 'text_default': {'key': '$NAME'},
    'expression_default': {}, 'character_art': {}, 'character_name': {'capitalize': False},
    'picker': {'characters': [], 'result': 'look'}, 'vibrate': {},
    'faceplace': {'action': 'enable', 'key': '$USR'}, 'faceplace_post': {}, 'faceplace_link': {'url': ''},
    'tree': {'action': 'enable', 'id': 0}, 'tree_node': {'type': 1203, 'width': 0, 'condition': 0},
    'tree_result': {'index': 0}, 'append_text': {'key': '$NAME'}, 'loading': {'wait': True},
    'open_url': {'url': ''}, 'survey': {'poll_id': 1001, 'answers': ['rating'], 'results': []},
    'end': {}, 'native': {},
}
INPUT_GATES = frozenset(('dialogue', 'choice', 'input', 'title', 'message', 'word_game', 'football', 'grid', 'shs11_memory', 'shs11_reflex', 'brew_catch', 'picker'))


def parameters(node):
    return dict(deepcopy(DEFAULTS[node.kind]), **node.params)


def text_fields(project):
    """Stable translation keys, including structured minigame text."""
    result = {'title': project.title}
    if project.native: return result
    for character in project.characters:
        result[f'character.{character.id}.name'] = character.name
    for calendar in project.calendars:              # (calendar_driver: its cards' title and its events' badges)
        if calendar['card_title']:
            result[f'calendar.{calendar["id"]}.card_title'] = calendar['card_title']
        for k, event in enumerate(calendar['events']):
            if event['name']:
                result[f'calendar.{calendar["id"]}.event.{k}.name'] = event['name']
    for node in project.nodes:
        for field in ('text', 'speaker'):
            result[f'node.{node.id}.{field}'] = getattr(node, field)
        for i, option in enumerate(node.options):
            result[f'node.{node.id}.option.{i}'] = option.text
            if option.detail:
                result[f'node.{node.id}.option.{i}.detail'] = option.detail
        p = parameters(node)
        for field in ('prompt', 'default', 'equals', 'subtitle', 'title', 'notification', 'success', 'failure',
                      'extra_offense', 'extra_defense', 'intro') + (('name',) if node.kind == 'schedule_event' else ()):
            if field in p:
                result[f'node.{node.id}.param.{field}'] = p[field]
        for field in ('good', 'bad', 'instructions'):
            for i, value in enumerate(p.get(field, [])):
                result[f'node.{node.id}.param.{field}.{i}'] = value
        for field in ('problems', 'tutorials', 'rounds'):
            for i, record in enumerate(p.get(field, [])):
                for key in ('title', 'body', 'heading', 'prompt', 'alphabet', 'fixed_board', 'cue', 'word'):
                    if key in record:
                        result[f'node.{node.id}.param.{field}.{i}.{key}'] = record[key]
                for j, word in enumerate(record.get('words', [])):
                    result[f'node.{node.id}.param.{field}.{i}.words.{j}'] = word
    return result


def translated(project, key, fallback):
    return project.locales.get(project.language, {}).get(key, fallback)
