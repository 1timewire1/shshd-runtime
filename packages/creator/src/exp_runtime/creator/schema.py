"""Small, discoverable authoring contracts and authored examples."""
from copy import deepcopy
from dataclasses import asdict

from .features import DEFAULTS, NAMES
from .model import Node, ProjectError

SHS_ONLY = frozenset(('football', 'grid', 'faceplace', 'faceplace_post', 'faceplace_link', 'tree', 'tree_node',
                      'tree_result', 'loading', 'survey'))


FIELDS = {
    'dialogue': ('text', 'speaker', 'portrait', 'theme', 'character', 'expression', 'next'),
    'choice': ('text', 'speaker', 'theme', 'character', 'options', 'timeout_ms', 'timeout_option'),
    'background': ('asset', 'next'), 'set': ('variable', 'value', 'next'),
    'branch': ('variable', 'operator', 'value', 'next', 'otherwise'),
    'text_branch': ('next', 'otherwise'), 'relationship': ('character', 'next'),
    'input': ('text', 'next'), 'title': ('text', 'next'), 'message': ('text', 'next'),
    'notice': ('text', 'next'), 'scene_label': ('text', 'next'),
    'word_game': ('text', 'character', 'next'), 'grid': ('next',), 'football': ('next',),
    'flag': ('character', 'next'), 'speakers': ('next',), 'set_text': ('text', 'next'),
    'text_default': ('text', 'next'), 'expression_default': ('character', 'expression', 'next'),
    'character_art': ('character', 'asset', 'next'), 'character_name': ('character', 'text', 'next'),
    'picker': ('text', 'character', 'next'), 'vibrate': ('next',),
    'faceplace': ('text', 'next'), 'faceplace_post': ('text', 'character', 'expression', 'next'),
    'faceplace_link': ('text', 'asset', 'next'), 'tree': ('next',), 'tree_node': ('text', 'next'),
    'tree_result': ('text', 'next'), 'append_text': ('text', 'next'), 'loading': ('next',),
    'open_url': ('next',), 'survey': ('next',),
    'end': (), 'native': (),
}
TEXT_NOTE = (' Text may format numbers with {expression} placeholders, such as {points} or {prop(0, 400)}, and shows '
             'stored texts as {name} or $KEY.')
NOTES = {
    'dialogue': 'Use character for a reusable speaker, or speaker/portrait for an inline speaker. Text must be nonempty. '
                'Expression -1 uses the character default (Default expression node).' + TEXT_NOTE,
    'choice': 'Provide 2–8 nonempty answers. Conditions enable answers; timeout_option is a zero-based visible row; native shuffling moves labels/return values, while enabled flags remain on rows.',
    'background': 'asset must reference an imported image in this project.',
    'set': 'variable is required; a nonempty params.expression overrides value.',
    'branch': 'params.expression overrides variable/operator/value. Both destinations are required.',
    'relationship': 'character is required. Changes the native relationship property, with the real emotion animation.',
    'score': 'Choose the game/script property owner and key explicitly. There is no universal score property; owner -30000 is reserved.',
    'input': 'Stores the answer under params.result: a name shown as {name}, or $KEY (such as $USR) to share it with '
             'other episodes. Native input uses the selected game\'s character and width limits.',
    'text_branch': 'Compares a stored text ({name} or $KEY) with params.equals.',
    'flag': 'Sets (value true) or clears bit 0-31 of a numeric property; character overrides params.owner. '
            'Read flags in expressions with bit(owner, key, n).',
    'speakers': 'params.player is the player character (native primary speaker, service 74); params.narrator a '
                'character whose lines become narration (service 75). Empty clears either.',
    'set_text': 'Stores the text under params.key ({name} or $KEY).',
    'text_default': 'Stores the text under params.key only while it is empty, as the original stories do for $ZOE.',
    'expression_default': 'The expression a character\'s dialogue uses when its expression is -1 (service 5).',
    'character_art': 'Changes a character\'s portrait base (service 72); five consecutive IDs are its expressions.',
    'character_name': 'Renames a character; the name may contain $KEY. capitalize applies the native case rule (49).',
    'picker': 'Shows 1-5 reusable characters (params.characters) to choose a look from, stores the zero-based index '
              'in params.result and, when character is set, gives that character the chosen look\'s portrait.',
    'vibrate': 'Native vibration (service 82); the desktop plays a buzz.',
    'faceplace': 'SHS HD only. params.action: enable (114, show the wall for this episode), clear (118), name_chosen '
                 '(119) or face_chosen (120) after the player picks a name or look, or default_name (113: stores the '
                 'text under params.key while $USR is empty).',
    'faceplace_post': 'SHS HD only. A wall post (115) from character (or the system when empty) with an expression.',
    'faceplace_link': 'SHS HD only. Continues the newest post with text and params.url (116), or a photo (asset) '
                      'with its caption (117).',
    'tree': 'SHS HD only. params.action: enable (101, show this episode\'s Decision Tree), join (112, where branches '
            'meet) or clear_accumulator (108, params.id). Each episode other than Football Star has its own tree.',
    'tree_node': 'SHS HD only. A scene on the Decision Tree (102/103) labelled by text. params.type 1202-1208 goes '
                 'straight on; 1209-1223 waits for a Tree result (1219-1223 branch until a join). params.width '
                 'widens an event box; params.condition (75-104) is a Football Star automatic branch test (111).',
    'tree_result': 'SHS HD only. Which result (0-4) the waiting tree scene took, with an optional exit label (106/107). '
                   'Scenes and results must alternate on every path.',
    'append_text': 'Appends the text to the stored text params.key ({name} or $KEY) with native concatenation (25); '
                   'keep the whole text under 1000 characters.',
    'loading': 'SHS only. The Loading / Please wait overlay for 3 s (91); params.wait holds the story until it closes.',
    'open_url': 'Asks to open params.url (100). The original apps leave the game for it; this runtime offers the link.',
    'survey': 'SHS only. Uploads params.answers (numeric expressions) to poll params.poll_id with service 9 and stores '
              'the returned percentages in params.results. The servers are gone: offline, the player sees a local '
              'receipt, the results stay 0 and the story continues.',
    'random': 'bound must be positive. Stores an actual native random draw in result.',
    'music': 'Music IDs are 8201–8232 in SHS and 8201–8209 in CoD, or an embedded MP3 (asset_import_audio). '
             'Some SHS IDs select offsets in another audio asset.',
    'sound': 'A game sound ID, or an embedded MP3/WAV (asset_import_audio).',
    'word_game': 'good needs at least 2 words; bad at least 3. Duration 1–32767 ms. Words cannot contain pipes.',
    'football': 'Six interleaved offense/defense tables, each 1–10 rows of [code, yards, variation, weight]. See defaults for a valid example.',
    'grid': 'Problems define dimensions, targets and alphabet. Tutorials use a fixed board. Native limits and table checks apply.',
    'end': 'Uses native episode-exit service 7. The player returns to its existing menu, where another installed episode can be selected.',
    'native': 'Imported native projects only. Preserve script/PC, instruction counts and data-bank lengths; no high-level reconstruction is assumed.',
}


def value_schema(value):
    if value is None: return {'type': ['integer', 'null'], 'minimum': 0, 'maximum': 32767}
    kind = {str: 'string', int: 'integer', float: 'number', bool: 'boolean', dict: 'object', list: 'array'}[type(value)]
    result = dict(type=kind, default=deepcopy(value))
    if kind == 'integer': result.update(minimum=-32768, maximum=32767)
    if kind == 'array' and value: result['items'] = value_schema(value[0])
    return result


def node_schema(kind=None):
    if kind is None:
        return dict(kinds=[dict(kind=k, title=v, games=['shs'] if k in SHS_ONLY else ['shs', 'cod'])
                           for k, v in NAMES.items()],
                    languages=['en', 'fr', 'it', 'de', 'es'],
                    expressions='Integers, variables, + - * // %, comparisons, and/or/not; signed 16-bit arithmetic. '
                                'Game state: prop(owner, key), bit(owner, key, n), art(character), build(2|3|9|10); '
                                'an owner may be a '
                                "character ID in quotes, such as prop('alex', 407).",
                    workflow='project_get → graph_search_nodes/graph_get_subgraph → project_preview_edits → project_apply_edits → project_validate → playtest → project_export_exp',
                    compatibility='Native KiWi/CSPUD export; full original-app playback remains unverified. Consult each kind for restrictions.',
                    resources=['creator://schema/{kind}', 'creator://examples/branching'],
                    limits=dict(nodes=20000, characters=199, options=8, batch_operations=200))
    if kind not in NAMES: raise ProjectError('Unknown node kind')
    defaults = asdict(Node('example', kind=kind))
    names = ('id', 'kind', 'label', 'x', 'y', 'scene', *FIELDS.get(kind, ('next',)))
    properties = {name: value_schema(defaults[name]) for name in names}
    properties['id'].update(minLength=1, maxLength=200, description='Stable, unique node ID; use readable names such as school_arrival.')
    properties['kind'] = {'const': kind}
    properties['scene'].update(minimum=25001, maximum=25999)
    properties['x'] = properties['y'] = dict(type='number', minimum=-100000, maximum=100000, default=0)
    for name in ('theme', 'expression'):
        if name in properties:
            properties[name].update(minimum=-1 if kind == 'dialogue' and name == 'expression' else 0,
                                    maximum=3 if name == 'theme' else 4)
    if 'options' in properties:
        properties['options'].update(minItems=2, maxItems=8, items=dict(type='object', additionalProperties=False,
            properties=dict(text=dict(type='string', minLength=1), target=dict(type='string', minLength=1),
                            condition=dict(type='string', default='')), required=['text', 'target']))
        properties['timeout_ms'].update(minimum=0, description='0 disables the timer; otherwise milliseconds, maximum 32767.')
        properties['timeout_option'].update(minimum=0, maximum=7)
    properties['params'] = dict(type='object', additionalProperties=False,
        properties={key: value_schema(value) for key, value in DEFAULTS[kind].items()}, default=deepcopy(DEFAULTS[kind]))
    if kind == 'native':
        properties['params'] = dict(type='object', description='Use native_get_data and graph_get_subgraph to inspect the imported block before editing.')
    example = dict(id='example', kind=kind, params=deepcopy(DEFAULTS[kind]))
    if 'next' in properties: example['next'] = 'end'
    if 'otherwise' in properties: example['otherwise'] = 'alternate_end'
    if 'text' in properties: example['text'] = 'An authored example.'
    if kind in ('set', 'branch'): example['variable'] = 'points'
    if kind == 'choice':
        example['options'] = [dict(text='Help', target='help'), dict(text='Leave', target='end')]
    if kind == 'relationship': example['character'] = 'friend'
    if kind == 'background': example['asset'] = 26000
    return dict(kind=kind, title=NAMES[kind], games=['shs'] if kind in SHS_ONLY else ['shs', 'cod'],
                schema=dict(type='object', properties=properties, required=['id', 'kind'], additionalProperties=False),
                notes=NOTES.get(kind, 'Uses the shared native compiler and host-service contract.'), example=example,
                compatibility='native_format',
                original_app_playback='unverified')


def branching_example():
    return dict(description='Apply to a new default project; uses no imported game assets.', operations=[
        dict(op='node', id='start', changes=dict(text='A friend needs help.', next='decision')),
        dict(op='node', id='decision', changes=dict(kind='choice', text='What do you do?', options=[
            dict(text='Help', target='reward'), dict(text='Leave', target='end')])),
        dict(op='node', id='reward', changes=dict(kind='set', variable='points', value=1, next='end'))],
        scenario=dict(seed=7, steps=[dict(action='run', until='choice'), dict(action='choose', option_id='decision:0'),
                                     dict(action='run', until='end')],
                      assertions=[dict(kind='variable', name='points', equals=1), dict(kind='ended')]))
