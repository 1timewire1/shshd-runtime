"""Small, discoverable authoring contracts and authored examples."""
from copy import deepcopy
from dataclasses import asdict

from .features import DEFAULTS, NAMES
from .model import Node, ProjectError


FIELDS = {
    'dialogue': ('text', 'speaker', 'portrait', 'theme', 'character', 'expression', 'next'),
    'choice': ('text', 'speaker', 'theme', 'character', 'options', 'timeout_ms', 'timeout_option'),
    'background': ('asset', 'next'), 'set': ('variable', 'value', 'next'),
    'branch': ('variable', 'operator', 'value', 'next', 'otherwise'),
    'text_branch': ('next', 'otherwise'), 'relationship': ('character', 'next'),
    'input': ('text', 'next'), 'title': ('text', 'next'), 'message': ('text', 'next'),
    'notice': ('text', 'next'), 'scene_label': ('text', 'next'),
    'word_game': ('text', 'character', 'next'), 'grid': ('next',), 'football': ('next',),
    'end': (), 'native': (),
}
NOTES = {
    'dialogue': 'Use character for a reusable speaker, or speaker/portrait for an inline speaker. Text must be nonempty.',
    'choice': 'Provide 2–8 nonempty answers. Conditions enable answers; timeout_option is a zero-based visible row; native shuffling moves labels/return values, while enabled flags remain on rows.',
    'background': 'asset must reference an imported image in this project.',
    'set': 'variable is required; a nonempty params.expression overrides value.',
    'branch': 'params.expression overrides variable/operator/value. Both destinations are required.',
    'relationship': 'character is required. Changes the native relationship property, with the real emotion animation.',
    'score': 'Choose the game/script property owner and key explicitly. There is no universal score property; owner -30000 is reserved.',
    'input': 'Stores a text variable. Native input uses the selected game\'s character and width limits.',
    'random': 'bound must be positive. Stores an actual native random draw in result.',
    'music': 'Music IDs are 8201–8232 in SHS and 8201–8209 in CoD. Some SHS IDs select offsets in another audio asset.',
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
        return dict(kinds=[dict(kind=k, title=v, games=['shs'] if k in ('football', 'grid') else ['shs', 'cod'])
                           for k, v in NAMES.items()],
                    languages=['en', 'fr', 'it', 'de', 'es'],
                    expressions='Integers, variables, + - * // %, comparisons, and/or/not; signed 16-bit arithmetic, no calls.',
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
        if name in properties: properties[name].update(minimum=0, maximum=3 if name == 'theme' else 4)
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
    return dict(kind=kind, title=NAMES[kind], games=['shs'] if kind in ('football', 'grid') else ['shs', 'cod'],
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
