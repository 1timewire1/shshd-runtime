"""Claire Hart Classic (build 157) for Cause of Death: the reader of its cases and the story add-on `chc`
(Other Games/docs/CLAIRE_HART_PLAN.md, Stage 1).

    python tools/translate/claire_hart.py report --mirror CLAIRE_HART_DIR
    python tools/translate/claire_hart.py ids --mirror CLAIRE_HART_DIR --out claire_hart_ids.tsv
    python tools/translate/claire_hart.py addon --mirror CLAIRE_HART_DIR --pairs PAIRS.txt --catalog COD_CATALOG_PORTRAITS \\
        --cod-library COD_LIBRARY --extras EXTRAS_DIR --out OUT_DIR
    python tools/translate/claire_hart.py rounds --mirror CLAIRE_HART_DIR --out OUT_DIR   (chcrounds: claire_rounds_addon.py)

CLAIRE_HART_DIR is the mirror (`reference/Other Games/Claire Hart Classic`: bundle_names.csv, raw/, unpacked/, index/).

The reader (`Mirror`) holds what the converter needs, besides each episode's own nodes:
- the cases in the case list's order, each a translated entry of pack 31500 numbered `index` x 10 (decision N), its title
  "Case n" or a special's own (N2), its parts the original episodes (`ids`: E-number <-> case and part);
- the looks (`looks`): every portrait folded into a look of CoD's 5 expression slots, Normal, Angry, Happy, Sad and Surprised
  (CoD's 4th, a worried face), so a look is 5 consecutive IDs as CoD draws one (cod/profile.py LOOK_BANKS). A face the look
  lacks takes its Normal, as Classic's driver falls back to `default`; Young*, Masked and the numbered Normals are looks of
  their own, and so is a face past the five (Lavender's Scream);
- the scenes (`scenes`): each of the 787 scene folders' backdrop (`template`) with its 3:4 slice (decision M, A): where
  Cause of Death cut that scene (index/bg_vs_template.json, a confident match), else centred;
- the tracks and story-object pictures, and the rounds' story-object lists resolved to the scene's items (`story_objects`,
  decision G2: the 985 that name an item).

`chc` holds all of it, used or not (owner, 2026-11-19), around chslim revision 1's resources under their IDs (chslim.py):

    26000-26786  the backdrops, the folders' sorted order, their original PNGs (full brightness: dimmed at draw time)
    26900-26932  the tracks, MP3 128 kb/s (FFmpeg)
    26960-26962  the Title Screen Look; 26990 Title Screen Music, the main jingle
    26998        the spec, JSON (SPEC_VERSION): looks, look names, picture IDs, scenes and slices, tracks, story objects
    27000-27644  the story-object pictures, their original PNGs
    28000-28005  chslim's map, frame backdrop, bubbles and fonts; 28010-28844 every portrait (28010 + its place in the sorted
                 list); 29000-29001 chslim's CoD-only edits; 29100-29108 Claire Hart Dialogue (ch_dialogue_skin.py)
"""
import argparse
import collections
import csv
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chslim                                               # noqa: E402
from exp_runtime.claire_round_services import round_key  # noqa: E402

PACK_ID = chslim.PACK_ID                                    # 31500
SLOTS = ('Normal', 'Angry', 'Happy', 'Sad', 'Surprised')    # CoD's expression slots, in order
BACKDROP_BASE, MUSIC_BASE, STORY_OBJECT_BASE = 26000, 26900, 27000
TITLE_SPEC, TITLE_BACKGROUND, TITLE_LOGO, TITLE_MUSIC = 26960, 26961, 26962, 26990
SPEC, SPEC_VERSION = 26998, 1                               # (LOOK_BANKS reads its `looks`)
LOOK_BANK_BASE = 30000                                      # cod/profile.py LOOK_BANKS: look n is 30000 + 5n on
CUT_AGREEMENT = 0.5                                         # a CoD cut this sure of its scene places the slice
# The Title Screen Look (Stage 0, decision Q): Classic's Play Now forest, and its logo (Claire and Paul over the gem banner)
# cut from the loading atlas; the jingle the episode select plays once.
FOREST = 'textures/new/loading_playnow_bg'
ATLAS, LOGO = 'raw/157/assets/resources/native/17/170baf746.png', (3, 3, 3 + 456, 3 + 381)
JINGLE = 'raw/157/assets/resources/native/b1/b143c842-d6d6-4a59-bf1f-2a3d0884f1e6.ogg'
TITLE_LOOK = {'version': 1,
              'background': {'cover': {'id': TITLE_BACKGROUND, 'scale': 1}},
              # 1.4 points a pixel: 638 points of the 768-wide frame, its foot about 50 points above Play/Resume (HD's
              # 753); in a taller frame it stays halfway between the top and where the buttons go.
              'title': {'picture': {'id': TITLE_LOGO, 'scale': 1.4}, 'centre': [384, 440], 'follow': 0.5}}
# Title cards (decision N2; owner, 2026-11-19): a part's card shows the scene its store picture shows (matched, STORE_MATCH),
# but for two whose store art is no Classic scene: E265's is the sequel's Van der Walt Den without its objects, which chc
# carries as an extra scene (EXTRA_SCENES, from the sequel's mirror); E191's bridal shop exists nowhere, so the episode's
# own Dress Shop stands in.
STORE_MATCH = 0.9
DEN = 'Shadows/VanDerWaltDen'
EXTRA_SCENES = {DEN: (26800, 'references/backgrounds/VanDerWaltDen_HO/hd/hovanderwaltden')}
STORE_SCENES = {'E191': 'DressShop', 'E265': DEN}
STORY_VERSION = 1                       # the cases' version (episode_version.py): a newer build replaces an older copy
# The chc revision the cases need: 1. Revision 2 adds only the skin's other screens (29109 on), which the player draws when
# it finds them, so a case plays with either (and a library still on revision 1 isn't asked for an update).
CASES_NEED_CHC = 1
TITLE_TAG = ' (CHC)'                    # the Claire Hart category (cod/profile.py)
NARRATOR_DEFAULT = {                    # characterutil.NARRATOR.DEFAULT: narration's portraits when a chapter has no 'Claire'
    'default': 'references/characters/ClaireHart/Avatar_Claire_Normal',
    'Avatar_Troy_Event': 'references/characters/TroyHarris/Avatar_Troy_Normal',
    'Avatar_Harper_Event': 'references/characters/Harper/Avatar_Harper_Normal',
    'Avatar_ClairePurple_Event': 'references/characters/ClaireHart/Avatar_Claire_Purple_Normal',
    'Avatar_Purple_Event': 'references/characters/ClaireHart/Avatar_Claire_Purple_Normal',
    'Avatar_Event_Purple': 'references/characters/ClaireHart/Avatar_Claire_Purple_Normal',
    'Avatar_Event_Troy': 'references/characters/TroyHarris/Avatar_Troy_Normal',
    'Avatar_WillYuBlue_Event': 'references/characters/WillYu/Avatar_WillYu_Blue_Normal',
}
# Text (TRANSLATOR_PLAN's rules for Classic): the Creator's text is Latin-1, so the 124 curly quotes, ellipses and dashes
# and 3 ō become plain ones; a line's trailing space goes and its 6 newlines join as spaces.
TEXT = str.maketrans({'\u2018': "'", '\u2019': "'", '\u201c': '"', '\u201d': '"', '\u2026': '...', '\u2013': '-',
                      '\u2014': '-', '\u014d': 'o', '\n': ' ', '\r': ' '})
WRAPPED = ('textColors', 'music', 'sounds', 'dialog objects', 'sprites')    # driver.runConfig keeps these as sub-maps
NOTHING = ('nothing', 'none', 'noobject', 'nostoryobject')
FACE = re.compile(r'(.*?)_?(Normal|Sad|Angry|Happy|Surprised|Scream|Masked)( \d)?$')


def norm(text):
    return re.sub(r'[^a-z0-9]', '', text.lower())


def folder_of(scene):
    """sceneloader: a scene's name to its folder."""
    return re.sub(r'[^a-zA-Z0-9]', '', scene)


def refs_for(chapter_refs):
    """driver.runConfig: a chapter's sceneRefs merged into one lookup, the WRAPPED maps kept whole."""
    refs = {}
    for key, value in chapter_refs.items():
        if key in WRAPPED:
            refs[key] = value
        else:
            refs.update(value)
    return refs


def look_of(path):
    """(look key, face) of a portrait path: the folder and the stem without its face. Masked and a numbered Normal are their
    own looks; Young* folds as a look of its own by its stem (Avatar_Claire_YoungSad -> Avatar_Claire_Young, Sad)."""
    folder, stem = path.rsplit('/', 1)
    match = FACE.match(stem)
    if match is None:
        return path, 'Normal'
    base, face, number = match.groups()
    if face == 'Masked':
        base, face = base + '_Masked', 'Normal'
    elif number:
        base, face = f'{base}_Normal{number.strip()}', 'Normal'
    return f'{folder}/{base}', face


def look_name(key):
    """A look's name for the Creator: 'references/characters/ClaireHart/Avatar_Claire_Young' -> 'Claire Young'."""
    stem = re.sub(r'^Avatar_', '', key.rsplit('/', 1)[1])
    words = re.sub(r'(?<=[a-z])(?=[A-Z0-9])', ' ', stem.replace('_', ' '))
    return ' '.join(words.split())


def case_title(case):
    """N2: a numbered case is "Case n"; a special keeps its title."""
    return case['title'].strip() or case['case'].strip().title()


class Mirror:
    """Claire Hart Classic's data, read from the mirror folder."""

    def __init__(self, root):
        self.root = Path(root)
        with open(self.root / 'bundle_names.csv', encoding='utf-8-sig', newline='') as file:
            rows = [row for row in csv.DictReader(file) if row['part'] == 'native']
        self.files = {row['real_path']: self.root / row['local_path'] for row in rows}
        self.kinds = {row['real_path']: row['kind'] for row in rows}
        self.cases_dir = self.root / 'unpacked/resources_json/cases'
        self.scenes_dir = self.root / 'raw/157/res/raw-assets/references/backgrounds'

    def _load(self, path):
        return json.loads(Path(path).read_text(encoding='utf-8'))

    # --- cases ---------------------------------------------------------------------------------------------------------
    def cases(self):
        """[(case key, case record, [(part, epconfig, sequences)])] in the case list's order."""
        caselist = self._load(self.cases_dir / 'caselist.json')
        out = []
        for key, case in sorted(caselist.items(), key=lambda kv: kv[1]['index']):
            folder = case['case'].replace('CASE ', 'case').replace(' ', '')     # hogstart / chapterselection rule
            parts = []
            for number, _ in enumerate(case['episodes'], 1):
                episode = self.cases_dir / folder / f'ep{number}'
                parts.append((number, self._load(episode / 'epconfig.json'),
                              self._load(episode / 'sequences.json')['sequences']))
            out.append((key, case, parts))
        return out

    def ids(self):
        """The testing table (decision N): a row per original episode, E-number to its case, part and translated entry."""
        rows = []
        for key, case, parts in self.cases():
            for (number, config, _), listed_episode in zip(parts, case['episodes']):
                # the title players saw: the case list's (4 differ from epconfig's, which the game never reads)
                rows.append(dict(epid=config['epid'], case=key, case_index=case['index'], case_title=case_title(case),
                                 part=number, parts=len(parts), pack=PACK_ID, episode=case['index'] * 10,
                                 title=listed_episode['name'].strip()))
        return rows

    # --- portraits and looks -------------------------------------------------------------------------------------------
    def portraits(self):
        return sorted(path for path, kind in self.kinds.items() if kind == 'portrait')

    def picture_ids(self):
        """{portrait path: its lasting ID} (chslim's rule)."""
        return chslim.portrait_ids(self.portraits())

    def looks(self):
        """[(look key, {face: path})], sorted by key: the look's number is its place here."""
        found = collections.defaultdict(dict)
        for path in self.portraits():
            key, face = look_of(path)
            if face in found[key]:
                raise ValueError(f'two {face} faces for look {key}')
            found[key][face] = path
        out = []
        for key in sorted(found):
            faces = found[key]
            extra = sorted(set(faces) - set(SLOTS))
            if extra and 'Surprised' not in faces and len(extra) == 1:
                faces['Surprised'] = faces.pop(extra[0])        # a lone extra face takes the 5th slot (plan, Stage 1)
                extra = []
            for face in extra:                                  # else its own look (Lavender's Scream)
                out.append((f'{key}_{face}', {'Normal': faces.pop(face)}))
            out.append((key, faces))
        return sorted(out)

    def look_banks(self):
        """(banks, names, slots): each look's 5 picture IDs (a missing face its Normal, or its first face without one), its name,
        and {portrait path: (look, slot)} of the faces it shows itself."""
        ids = self.picture_ids()
        banks, names, slots = [], [], {}
        for number, (key, faces) in enumerate(self.looks()):
            fallback = faces.get('Normal') or next(faces[face] for face in SLOTS if face in faces)
            banks.append([ids[faces.get(face, fallback)] for face in SLOTS])
            names.append(look_name(key))
            for slot, face in enumerate(SLOTS):
                if face in faces:
                    slots[faces[face]] = (number, slot)
        return banks, names, slots

    # --- scenes --------------------------------------------------------------------------------------------------------
    def scene_folders(self):
        return sorted(p.name for p in self.scenes_dir.iterdir() if (p / 'hd' / 'template.png').exists())

    def cod_cuts(self):
        """{scene folder: [(CoD background, centre x in the template)]}: Cause of Death's own cuts, the confident ones."""
        cuts = collections.defaultdict(list)
        index = self._load(self.root / 'index/bg_vs_template.json')
        for number, entry in sorted(index.items()):
            best = (entry.get('cands') or [None])[0]
            if best and best.get('agree', 0) >= CUT_AGREEMENT:
                x, _, w, _ = best['crop']
                cuts[best['scene']].append((number, x + w / 2))
        return cuts

    def scenes(self):
        """{scene folder: (backdrop ID, slice x, how)}: the 3:4 slice's left edge in the template's pixels (a 1024 x 768
        template's slice is 576 wide), at CoD's first cut of the scene ('cod') or centred ('centre')."""
        from PIL import Image
        cuts = self.cod_cuts()
        out = {}
        for number, folder in enumerate(self.scene_folders()):
            with Image.open(self.scenes_dir / folder / 'hd' / 'template.png') as image:
                width, height = image.size
            span = round(height * 3 / 4)
            if folder in cuts:
                centre, how = cuts[folder][0][1], 'cod'
            else:
                centre, how = width / 2, 'centre'
            out[folder] = (BACKDROP_BASE + number, max(0, min(width - span, round(centre - span / 2))), how)
        return out

    def backdrop(self, folder):
        """A scene's picture for the story: its clean base (the layout's `default` layer, 1026 x 770, the scene without
        the round's hidden objects; owner, 2026-11-20), else `background.png`, else the `template` (objects drawn in)."""
        hd = self.scenes_dir / folder / 'hd'
        layout = self._load(hd / f'{folder}.json')
        for group in layout['textures']:
            if group['id'] == 'default':
                for texture in group['textures']:
                    path = hd / f"{texture['id']}.png"
                    if texture['width'] >= 1000 and path.exists():
                        return path.read_bytes()
        path = hd / 'background.png'
        return (path if path.exists() else hd / 'template.png').read_bytes()

    # --- music and story objects ---------------------------------------------------------------------------------------
    def tracks(self):
        """{track stem: (music ID, the OGG's path)}."""
        prefix = 'references/music/ogg/'
        stems = sorted(path[len(prefix):] for path in self.files if path.startswith(prefix))
        return {stem: (MUSIC_BASE + number, self.files[prefix + stem]) for number, stem in enumerate(stems)}

    def story_object_ids(self):
        """{story-object picture path: its ID}."""
        paths = sorted(path for path, kind in self.kinds.items() if kind == 'storyobj')
        return {path: STORY_OBJECT_BASE + number for number, path in enumerate(paths)}

    def scene_items(self, folder):
        """The scene's hidden objects as names.json gives them: [{'normal', 'name', ...}]."""
        path = self.scenes_dir / folder / 'names.json'
        return self._load(path)['names'] if path.exists() else []

    def round_items(self, value):
        """A round's story-object list (its chapter's `hogScene` entry, `value`) resolved (decision G2):
        [(entry, item or None)], the item the names.json entry the list names: by its name, else as build 157 matched (a
        substring of the sprite or name). Annotations ("(by the door)") are dropped; "Nothing" and the like list none."""
        listed = value.get('storyobject')
        if listed is None:
            return []
        out = []
        names = self.scene_items(folder_of(value['scene']))
        for entry in [listed] if isinstance(listed, str) else listed:
            base = norm(re.sub(r'\s*[\[\(].*$', '', entry).strip())
            if not base or base in NOTHING or 'nostoryobject' in norm(entry):
                continue
            hit = [e for e in names if norm(e['name']) == base] or \
                  [e for e in names if base in norm(e['normal']) or base in norm(e['name'])] or \
                  [e for e in names if norm(e['name']) and norm(e['name']) in base]
            out.append((entry, hit[0] if hit else None))
        return out

    def story_objects(self):
        """Every round's story-object list resolved: [(epid, round scene, entry, item or None)] (round_items)."""
        out = []
        for _, _, parts in self.cases():
            for _, config, _ in parts:
                for chapter in config['sceneRefs'].values():
                    for value in chapter.get('backgrounds', {}).values():
                        if value.get('type') == 'hogScene':
                            out += [(config['epid'], value['scene'], entry, item)
                                    for entry, item in self.round_items(value)]
        return out

    # --- the store pictures (title cards) ------------------------------------------------------------------------------
    def store_scenes(self, cache=None):
        """{epid: scene folder}: the scene each episode's store picture shows (a template shrunk to 320 x 240; 264 of 266,
        found by matching). The two that show no Classic scene take STORE_SCENES' stand-ins. `cache`: a JSON file kept
        between runs (the matching reads all 787 scenes)."""
        if cache is not None and Path(cache).exists():
            return json.loads(Path(cache).read_text(encoding='utf-8'))
        import numpy as np
        from PIL import Image

        def vector(image):
            pixels = np.asarray(image.convert('L').resize((64, 48), Image.BILINEAR), dtype=float)
            pixels -= pixels.mean()
            return (pixels / (np.linalg.norm(pixels) + 1e-9)).ravel()
        folders = self.scene_folders()
        table = np.stack([vector(Image.open(self.scenes_dir / f / 'hd' / 'template.png')) for f in folders])
        out = {}
        for _, case, parts in self.cases():
            for (_, config, _), listed in zip(parts, case['episodes']):
                if config['epid'] in STORE_SCENES:
                    out[config['epid']] = STORE_SCENES[config['epid']]
                    continue
                scores = table @ vector(Image.open(self.files[listed['thumbnail']]))
                best = int(scores.argmax())
                if scores[best] < STORE_MATCH:
                    raise ValueError(f"{config['epid']}'s store picture matches no scene (best {folders[best]}, "
                                     f'{scores[best]:.3f}): give it a stand-in in STORE_SCENES')
                out[config['epid']] = folders[best]
        if cache is not None:
            Path(cache).write_text(json.dumps(out, indent=1, sort_keys=True), encoding='utf-8')
        return out

    # --- the add-on ----------------------------------------------------------------------------------------------------
    def spec(self):
        banks, names, slots = self.look_banks()
        return {'version': SPEC_VERSION, 'looks': banks, 'look_names': names,
                'pictures': {path: [*slots[path], ident] if path in slots else [None, None, ident]
                             for path, ident in self.picture_ids().items()},
                'scenes': {folder: [ident, x] for folder, (ident, x, _) in self.scenes().items()},
                'music': {stem: ident for stem, (ident, _) in self.tracks().items()},
                'story_objects': self.story_object_ids()}


# --- the converter: a case as a Creator project (plan Stage 2) ---------------------------------------------------------
# Scene names that take no "the" in a round line beyond the rule's own (place): proper names. The owner checks the list
# (`places` command) and moves names in or out.
PROPER_PLACES = frozenset((
    'Beacon Park', 'Buckingham Palace', 'Cherry Lake', 'Chinatown', 'Colfax Manor', 'Covent Garden', 'Dolores Park Knits',
    'Grafton Street', 'Gray Consultants', 'Haight Ashbury', 'Honey Island Swamp', 'La Maison', 'Lauderdale Beach', 'London',
    'Lower Haight', 'Lyon Street', 'Main Street', 'Mardi Gras', 'Pier 39', 'Point Reyes', 'Sannen Street', 'Seacliff Park',
    'Union Square', 'Whitman Manor'))
# Round scene names as the data spells them that a line would show oddly (joined words, a stray digit), as said.
SCENE_NAMES = {'CafeBakery': 'Cafe Bakery', 'CasualRestaurant': 'Casual Restaurant', 'NyeNightClub': 'NYE Night Club',
               'NyeDinnerNyeEvent': 'NYE Dinner', 'Nye Ballroom': 'NYE Ballroom', 'Poolside2': 'Poolside',
               'Busstop': 'Bus Stop', 'Tower Of London': 'Tower of London', "Farmer's Market 2": "Farmer's Market",
               "Claire and Claudia's Room Night": "Claire and Claudia's Room"}
# Possessives whose owner is a role, a group or a day, not a person: they take "the" ("the Farmer's Market", "the
# Director's Office", "the New Year's Party"); a person's place doesn't ("Troy's Apartment", "Santa's Village").
COMMON_OWNERS = frozenset(('Architect', 'Athletes', 'Director', 'Farmer', 'Foreman', 'Instructor', 'Keeper', 'Kid',
                           'Magician', 'Maid', 'New Year', 'Pharaoh', 'Professor', 'Publisher', 'Queen', 'Sheriff',
                           'St. Patrick', 'Valentine', 'Women', 'Writer'))


def story_text(body):
    """A line's text as Classic's dialogue shows it, by the text rules (TEXT): Latin-1, trimmed, single spaces (its
    tokenizer splits on spaces and drops the empty words), and a lone punctuation mark joined to the word before it
    ("wanting , loss" shows as "wanting, loss": dialogue.js's PUNCTUATION; "Wait ..." stays)."""
    text = re.sub(r' {2,}', ' ', body.translate(TEXT).strip())
    return re.sub(r''' ([.,;:'"?!])(?= |$)''', r'\1', text)


def place(scene, player=None):
    """A round scene's name as a round line says it: 'Driveway' -> 'the Driveway'. The `player`'s own place is theirs
    ("Claire's Office" -> 'my office', "Claire and Claudia's Room" -> 'our room' as Claire; owner, 2026-11-20); another
    possessive, a name that starts with 'The', or one of PROPER_PLACES keeps its own."""
    name = SCENE_NAMES.get(scene.strip(), scene.strip())
    if player:
        if name.startswith(f"{player}'s "):
            return 'my ' + name[len(player) + 3:].lower()
        shared = re.match(rf"{re.escape(player)} and \w+'s (.+)$", name)
        if shared:
            return 'our ' + shared.group(1).lower()
    owner = re.match(r"(.+?)'s? ", name)               # "Farmer's Market" -> Farmer, "Athletes' Village" -> Athletes
    if owner and owner.group(1) in COMMON_OWNERS:
        return 'the ' + name
    if "'s " in name or name.endswith("'s") or "s' " in name or name.startswith('The ') or name in PROPER_PLACES:
        return name
    return 'the ' + name


def listed(things):
    """'the A', 'the A and the B', 'the A, the B and the C'."""
    things = ['the ' + thing for thing in things]
    return things[0] if len(things) == 1 else ', '.join(things[:-1]) + ' and ' + things[-1]


def round_line(scene, items, player=None):
    """Decision G: a round, with the real rounds off, as one narration line, in the player's own voice as the story's
    narration is (owner, 2026-11-20: first person, past tense); `player` is their first name (place)."""
    if items:
        return f'I searched {place(scene, player)} and found {listed(items)}.'
    return f'I searched {place(scene, player)}.'


def first_name(folder):
    """A portrait folder's person's first name: 'TroyHarris' -> 'Troy', 'Harper' -> 'Harper'."""
    return re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', folder).split()[0]


def plate_name(header):
    """A speaker's name plate: the header, but a one-word header of joined names gets its space (the data's
    'JillianGish', 'WillYu', 'LihwaLo'...: Classic showed them joined; owner, 2026-11-20). 'Donald McAllister' keeps its
    own."""
    return header if ' ' in header.strip() else re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', header)


# An episode opens with its player introducing themselves ("My name is Claire Hart. I have the ability to...", "I'm Troy
# Harris, and I'm an investigator for the SFPD."): the name's sentence, then any about who they are.
INTRO = re.compile(r"^(My name is|My name's|I'm|I am)\s+[A-Z][a-z]+")
INTRO_MORE = re.compile(r"^(I|And I)\b.*\b(abilit(y|ies)|gift|talent|single, thirty|make my living|investigator for)\b")


def trim_intro(text):
    """A later part's first line without the player's introduction (owner, 2026-11-20: shown once a case); its story,
    the recap or what happens next, stays. '' when nothing else is left; a line that opens otherwise comes back as is."""
    marked = ABBREVIATION.sub(lambda match: match.group(1) + '.\0', text)
    sentences = [sentence.replace('\0', ' ') for sentence in re.split(r'(?<=[.!?])\s+', marked)]
    if not INTRO.match(sentences[0]):
        return text
    rest = sentences[1:]
    while rest and INTRO_MORE.search(rest[0]):
        rest = rest[1:]
    return ' '.join(rest).strip()


# The store's sign-off at an episode's end (owner, 2026-11-20: it breaks the story's flow): a sentence naming the game,
# its next episode or Club Pogo...
UPSELL = re.compile(r"Claire Hart Classic|Claire Hart: Soul Searcher|Club Pogo|next episode|new episode|Episode \d|"
                    r"come back for|next case|her new case|Look for the start|more episodes|next part|second part|"
                    r"Thanks for playing|stay tuned|future storyline", re.I)
# ...and a call to the player just before one ("Want to find out...?", "Curious where this leads?"). The story's own
# questions ("but just what was Ethan's message?"), asides and season's greetings stay (owner, 2026-11-20).
TEASER = re.compile(r"^(Want to|Curious|Wonder|Find out|Check out|Join Claire|Be sure)|\byour help\b", re.I)
ABBREVIATION = re.compile(r'\b(Dr|Mr|Mrs|Ms|St|Jr|Sr)\. ')
EVENT = re.compile(r'(^|_)Event(_|$)')     # characterutil's narration looks: 'Avatar_Troy_Event', 'Avatar_Event_Purple'
# The next chapter tells the search itself (owner, 2026-11-20: then the round's stand-in line is redundant).
SEARCH_TOLD = re.compile(r"\b(found|find|finds|searched|searching|discovered|turned up|came across|uncovered|located|"
                         r"spotted|noticed|picked up|followed my feelings|drawn to|caught my eye)\b", re.I)
# ...and, when the chapter opens with the round's finds as story objects, the narrator handling or looking at one (E019's
# "I followed my feelings to a bunch of coins": quarter, dime and penny).
HANDLED = re.compile(r"\b(handed|grabbed|touched|looked over at|studied|held up|showed|pulled|took)\b", re.I)


def trim_outro(text):
    """An episode-end line without its sign-off: each UPSELL sentence, and a TEASER one just before one; '' when nothing
    of the story is left. A line without one comes back as it is. "Dr. Lubbock" is one sentence."""
    if not UPSELL.search(text):
        return text
    marked = ABBREVIATION.sub(lambda match: match.group(1) + '.\0', text)
    sentences = [sentence.replace('\0', ' ') for sentence in re.split(r'(?<=[.!?])\s+', marked)]
    kept, before_sign_off = [], False
    for sentence in reversed(sentences):
        if UPSELL.search(sentence):
            before_sign_off = True
            continue
        if before_sign_off and TEASER.search(sentence.strip()):
            continue                    # (a call to the player just before a sign-off)
        before_sign_off = False
        kept.append(sentence)
    return ' '.join(reversed(kept)).strip()


def stem(word):
    word = word.lower()
    return word[:-1] if len(word) > 3 and word.endswith('s') and not word.endswith('ss') else word


def round_told(lines, finds, shown=False):
    """Why a round's stand-in line isn't needed: the next chapter's first two lines (`lines`) name one of its finds (an
    item the round's list resolves to, or a story object the chapter opens with), or tell a search, or, when it opens
    showing story objects (`shown`), handle one; else None."""
    text = ' '.join(lines)
    for find in finds:
        words = re.findall(r'[A-Za-z]+', find)
        if words and re.search(rf'\b{re.escape(stem(words[-1]))}(s|es)?\b', text, re.I):
            return f'names the {find}'
    found = SEARCH_TOLD.search(text) or (HANDLED.search(text) if shown else None)
    return f'tells the search ("{found.group(0)}")' if found else None


def item_title(object_id):
    """A story object's name from its `dialog objects` key, for players without the picture: 'Push_Broom_SO' -> 'Push
    Broom'."""
    words = re.sub(r'_?SO$', '', object_id).replace('_', ' ')
    return ' '.join(re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', words).split()) or object_id


class CaseBuilder:
    """One case's nodes, characters and assets (convert)."""

    def __init__(self, mirror, art):
        from exp_runtime.creator import Asset, Character, Node
        self.Asset, self.Character, self.Node = Asset, Character, Node
        self.mirror, self.art = mirror, art
        self.nodes, self.characters, self.assets = [], {}, {}
        self.looks = {}                 # character id -> its look now
        self.narrator = None            # the narrator character now
        self.narrator_name = 'Claire'
        self.player = None              # the player character now: the speaker who narrates the part (on the left)
        self.player_folder = 'ClaireHart'   # ...the portrait folder whose speaker that is
        self.folders = {}               # speaker character id -> its portrait folder
        self.cast = (None, None)        # the (player, narrator) the last `speakers` node set
        self.reviews = dict(rounds=[], outros=[], intros=[])
        self.pending = None             # loose ends the next node joins (add), else the last node
        self.asked = False              # whether the case has asked if its rounds can be played (round)
        self.track = None
        self.music = {}                 # every chapter's music map so far: audioplayer's, kept for the session
        self.faces = {}                 # speaker key -> the face showing, this chapter
        self.slices = {}
        self.report = collections.Counter()

    def add(self, kind='dialogue', **fields):
        """A node after the last one, or, where `pending` names loose ends ((node, 'next' or 'otherwise')), after those."""
        node = self.Node(f'n{len(self.nodes)}', kind, **fields)
        if self.pending is None:
            if self.nodes:
                self.nodes[-1].next = node.id
        else:
            for loose, slot in self.pending:
                setattr(loose, slot, node.id)
            self.pending = None
        self.nodes.append(node)
        return node

    def asset(self, ident, name):
        self.assets.setdefault(ident, self.Asset(ident, name, None, chslim.CHC_ID))

    def bank(self, look):
        """Look `look`'s 5 IDs (cod/profile.py LOOK_BANKS), declared as chc's."""
        base = LOOK_BANK_BASE + 5 * look
        for slot in range(5):
            self.asset(base + slot, f'{self.art["look_names"][look]} {SLOTS[slot]}')
        return base

    def scene(self, folder):
        """A scene's backdrop ID, its slice kept for the episode's record."""
        ident, x = self.art['scenes'][folder]
        self.asset(ident, folder)
        if folder in self.art['own_scenes']:
            self.slices[ident] = x
        return ident

    def face(self, path):
        look, slot = self.art['faces'][path]
        return look, slot

    def speaker(self, header, path):
        """A speaker's character, its art turned to this line's look when it changed (service 72)."""
        look, slot = self.face(path)
        key = header
        if key not in self.characters:
            cid = f'c{len(self.characters)}'
            base = self.bank(look)
            self.characters[key] = self.Character(cid, plate_name(header), base, 1, [base + i for i in range(5)])
            self.looks[cid] = look
            # No CoD relationship badge: Claire Hart has none (property 629 = 1 hides it; the X360 stories' way).
            self.add('relationship', character=cid, params={'operation': 'add', 'value': 0, 'romantic': False,
                                                            'hide': True, 'result': f'badge_{cid}'})
        character = self.characters[key]
        if self.looks[character.id] != look:
            self.add('character_art', character=character.id, asset=self.bank(look))
            self.looks[character.id] = look
            self.report['look changes'] += 1
        self.folders[character.id] = path.split('/')[2]
        if self.folders[character.id] == self.player_folder and self.player != character.id:
            self.player = character.id
            self.cast_now()
        return character.id, slot

    def cast_now(self):
        """A `speakers` node when the player or narrator changed: the player character's own lines go on the left, as
        CoD's player's do (owner, 2026-11-20: Claire, or whoever narrates, is the player character)."""
        if (self.player, self.narrator) != self.cast:
            self.add('speakers', params={'player': self.player or '', 'narrator': self.narrator or ''})
            self.cast = (self.player, self.narrator)

    def play_as(self, folder):
        """A part's player: the speaker with portrait folder `folder` (playing)."""
        self.player_folder = folder
        self.player = next((cid for cid, held in reversed(list(self.folders.items())) if held == folder), None)
        self.cast_now()

    def narrate(self, path):
        """The narrator character showing `path`'s look (narrate_look)."""
        look, slot = self.face(path)
        self.narrate_look(look)
        return slot

    def narrate_as_player(self):
        """The narrator turned to the player's look, for a line in their voice (a round's): the player's speaker as they
        look now, else their folder's first look."""
        if self.player is not None:
            look = self.looks[self.player]
        else:
            look = next((look for path, (look, slot) in self.art['faces'].items()
                         if path.split('/')[2] == self.player_folder and slot == 0), None)
        if look is not None:
            self.narrate_look(look)

    def narrate_look(self, look):
        """The narrator character showing look `look` (a character of its own, so the same person's speaker lines keep
        their name plate: engine.py takes any line of the narrator character as narration)."""
        key = ('narrator', look)
        if key not in self.characters:
            base = self.bank(look)
            name = self.art['look_names'][look].split()[0]
            self.characters[key] = self.Character(f'narrator{look}', name, base, 1, [base + i for i in range(5)])
        character = self.characters[key]
        self.narrator = character.id
        self.cast_now()
        self.narrator_name = character.name

    def portrait(self, key, expressions, expression):
        """The picture a line shows: its expression's; none asked shows `default` (character.slide asks setExpression for
        `default`); a key the speaker lacks (a typo) keeps the face showing for a speaker already on stage this chapter
        (setExpression never resolves it), and is `default` on entering (setImage)."""
        if expression in expressions:
            path = expressions[expression]
        elif expression and key in self.faces:
            path = self.faces[key]
            self.report['faces kept (a key the speaker lacks)'] += 1
        else:
            path = expressions['default']
        self.faces[key] = path
        return path

    def chapter(self, config, sequence, refs, last=False, reintroduced=False):
        """A chapter's nodes, in order (CLAIRE_HART_ENGINE.md section 4). In an episode's `last` chapter, its sign-off
        goes (trim_outro); when the player was `reintroduced` (a later part of the case), its first line's introduction
        goes (trim_intro; owner, 2026-11-20)."""
        self.faces = {}                 # each chapter reloads the scene, its characters with it
        self.music.update(refs.get('music') or {})
        for node in sequence['nodes']:
            kind = node['type'] if node['type'] != 'event' else node['eventtype']
            if kind == 'dialogText':
                text = story_text(node['body'])
                if reintroduced:
                    reintroduced = False
                    kept = trim_intro(text)
                    if kept != text:
                        self.reviews['intros'].append((config['epid'], text, kept))
                        self.report['introductions trimmed' if kept else 'introduction lines dropped'] += 1
                        if not kept:
                            continue
                        text = kept
                if last and UPSELL.search(text):
                    kept = trim_outro(text)
                    self.reviews['outros'].append((config['epid'], text, kept))
                    self.report['sign-offs trimmed' if kept else 'sign-off lines dropped'] += 1
                    if not kept:
                        continue
                    text = kept
                expression = node.get('expression') or ''
                if node['header'] == '':
                    ref = refs.get('Claire') or refs.get('claire')
                    expressions = (ref or {'expressions': NARRATOR_DEFAULT})['expressions']
                    if ref is None and expression not in expressions and self.player_folder != 'ClaireHart':
                        # Narration with no look of its own shows Claire (NARRATOR_DEFAULT) even in a part someone else
                        # plays; it is theirs (owner, 2026-11-20: E144's closing line showed Claire in Troy's case).
                        self.narrate_as_player()
                        self.add(text=text, expression=0)
                        self.report['narration shown as the player'] += 1
                    else:
                        slot = self.narrate(self.portrait('Claire', expressions, expression))
                        self.add(text=text, expression=slot)
                    self.report['narration'] += 1
                elif EVENT.search(expression):
                    # A speaker line with an `..._Event` look is the player narrating (Troy's 23, in his own parts), which
                    # Classic showed under his name plate: narration, with no plate (owner, 2026-11-20).
                    ref = refs.get(node['header']) or refs.get(node['header'].lower())
                    slot = self.narrate(self.portrait(node['header'], ref['expressions'], expression))
                    self.add(text=text, expression=slot)
                    self.report['narration'] += 1
                    self.report['speaker lines as narration (Event looks)'] += 1
                else:
                    ref = refs.get(node['header']) or refs.get(node['header'].lower())
                    cid, slot = self.speaker(node['header'],
                                             self.portrait(node['header'], ref['expressions'], expression))
                    self.add(text=text, character=cid, expression=slot)
                    self.report['speaker lines'] += 1
            elif kind == 'stageBlockIntro':
                backdrop = refs.get(node['ref']) or refs.get(node['ref'].lower())
                folder = backdrop['resource'].split('/')[2]
                self.add('background', asset=self.scene(folder))
                self.report['backdrops'] += 1
            elif kind == 'playMusic':
                # audioplayer: the id in every map loaded so far (an earlier chapter's may answer a missing one), else
                # nothing changes; a found track always restarts, even the one playing (a hard stop, then play).
                track = self.music.get(node['id'])
                if track is None:
                    self.report['music ids missing (track kept)'] += 1
                    continue
                if (refs.get('music') or {}).get(node['id']) is None:
                    self.report['music ids from an earlier chapter or case'] += 1
                ident = self.art['music'][track.rsplit('.', 1)[0]]
                self.asset(ident, track)
                self.add('music', params={'resource': ident, 'loop': True})
                self.track = ident
            elif kind == 'showStoryObject':
                picture = (refs.get('dialog objects') or {}).get(node['id'])
                ident = self.art['story_objects'][picture]
                self.asset(ident, node['id'])
                self.add('story_object', text=item_title(node['id']), asset=ident)
                self.report['story objects'] += 1
            elif kind in ('dialogIntro', 'stageBlockOutro'):
                continue                # (the box comes with a line; a new backdrop replaces the old)
            else:
                raise ValueError(f"{config['epid']}: a node this converter doesn't know: {kind}")

    def round(self, config, number, chapter_refs, following):
        """Round `number`, with the real rounds off: its scene, and a line naming what the narrator finds (G, G2), unless
        the next chapter (`following`, its nodes) tells it in its first two lines (round_told; owner, 2026-11-20)."""
        hog = config['hogConfig'][f'HIDDEN OBJECT GAME {number}']
        entry = next((value for value in chapter_refs['backgrounds'].values() if value.get('type') == 'hogScene'), {})
        items = []
        for _, item in self.mirror.round_items(entry) if entry else ():
            if item is not None and item['name'] not in items:
                items.append(item['name'])
        lines, shown = [], []
        for node in following:              # its first two lines, and the story objects it shows by then
            if node['type'] == 'dialogText':
                lines.append(story_text(node['body']))
                if len(lines) == 2:
                    break
            elif node.get('eventtype') == 'showStoryObject':
                shown.append(item_title(node['id']))
        told = round_told(lines, items + shown, shown=bool(shown))
        line = round_line(hog['scene'], items, first_name(self.player_folder))
        self.reviews['rounds'].append((config['epid'], number, hog['scene'], ', '.join(items), told or 'stand-in', line,
                                       ' / '.join(lines)[:220]))
        self.report['rounds'] += 1
        # The round played for real where it can be (chcrounds, Use Translated Mini-Games: Stage 3), else the stand-in.
        if not self.asked:
            self.add('minigames_available', params={'result': 'real_rounds', 'for': 'claire_round'})
            self.asked = True
        real = self.add('branch', params={'expression': '(real_rounds == 1)'})
        self.pending = [(real, 'next')]
        played = self.add('claire_round', params={'round': round_key(config['epid'], number), 'result': 'round_score'})
        ends = [(played, 'next')]
        self.pending = [(real, 'otherwise')]
        self.report['real rounds'] += 1
        if told:
            self.report['rounds told by the next chapter'] += 1
            self.pending += ends
        else:
            self.add('background', asset=self.scene(folder_of(hog['scene'])))
            self.narrate_as_player()
            last = self.add(text=line, expression=0)
            self.pending = [(last, 'next')] + ends
            self.report['round lines'] += 1
            self.report['round items'] += len(items)
        self.cast = (None, None)        # (only the stand-in turned the narrator: the next line says who's who again)


def converter_art(mirror, cache=None):
    """What convert reads of chc: the look table, scenes, tracks and story objects (as Mirror.spec), and the store scenes."""
    banks, names, slots = mirror.look_banks()
    scenes = {folder: (ident, x) for folder, (ident, x, _) in mirror.scenes().items()}
    own = set(scenes)
    for folder, (ident, _) in EXTRA_SCENES.items():
        scenes[folder] = (ident, 0)
    # audioplayer's map is kept for the session, so a case played after the ones before it in the case list starts with
    # their maps loaded (the last loaded wins): what answers an id missing from its own chapters (E035's "Claire's Office")
    music_before, session = {}, {}
    for _, case, parts in mirror.cases():
        music_before[case['index']] = dict(session)
        for _, config, _ in parts:
            for chapter in sorted(config['sceneRefs']):
                session.update(config['sceneRefs'][chapter].get('music') or {})
    return dict(looks=banks, look_names=names, faces=slots, scenes=scenes, own_scenes=own,
                music={stem: ident for stem, (ident, _) in mirror.tracks().items()}, music_before=music_before,
                story_objects=mirror.story_object_ids(), store=mirror.store_scenes(cache))


def convert(mirror, art, case, parts):
    """A case as (a Creator Project for Cause of Death, its backdrop slices {resource: x}, a report): its parts in order,
    each opened by a title card over its store picture's scene (N2), its chapters' lines, backdrops, music and story
    objects, and each round as a line (G)."""
    from exp_runtime.creator import Project
    builder = CaseBuilder(mirror, art)
    builder.music.update(art.get('music_before', {}).get(case['index'], {}))
    title = story_text(case_title(case))          # (Latin-1, as every line: St. Patrick's)
    for (number, config, sequences), listed_episode in zip(parts, case['episodes']):
        # The card shows the episode's title over the case's, as playing it (the list shows the case's; owner,
        # 2026-11-20, as the SHS '07 translations do).
        builder.add('title', text=story_text(listed_episode['name']), params={
            'subtitle': title, 'background': builder.scene(art['store'][config['epid']]), 'flag': 0})
        player = playing(config, sequences)
        again = player == builder.player_folder and number > 1     # the same player as the part before
        builder.play_as(player)
        chapters = [node['sequenceId'] for node in sequences['main']['nodes'] if node['type'] == 'playSequence']
        for node in sequences['main']['nodes']:
            if node['type'] == 'playSequence':
                chapter = node['sequenceId']
                builder.chapter(config, sequences[chapter], refs_for(config['sceneRefs'][chapter]),
                                last=chapter == chapters[-1], reintroduced=again and chapter == chapters[0])
            elif node['type'] == 'playHOG':
                n = int(node['hogId'].rsplit(' ', 1)[1])
                builder.round(config, n, config['sceneRefs'][f'SCENE 1_{n}'], sequences[f'SCENE 1_{n + 1}']['nodes'])
    builder.add('end')
    project = Project(title=title + TITLE_TAG, game='cod', pack_id=PACK_ID, episode_id=case['index'] * 10,
                      episode_version=STORY_VERSION, nodes=builder.nodes)
    project.addons = [dict(id=chslim.CHC_ID, revision=CASES_NEED_CHC)]
    project.assets = [builder.assets[ident] for ident in sorted(builder.assets)]
    project.characters = list(builder.characters.values())
    project.start = builder.nodes[0].id
    for i, node in enumerate(project.nodes):
        node.x, node.y = 40 + 320 * (i % 12), 80 + 140 * (i // 12)
    builder.report['parts'] = len(parts)
    builder.report.reviews = builder.reviews
    return project, builder.slices, builder.report


def playing(config, sequences):
    """The portrait folder of an episode's player: who introduces themselves in its first line ("I'm Troy Harris, and
    I'm an investigator..."; owner, 2026-11-20), as that line shows them; else whom its narration shows most."""
    chapter = next(node['sequenceId'] for node in sequences['main']['nodes'] if node['type'] == 'playSequence')
    refs = refs_for(config['sceneRefs'][chapter])
    first = next((node for node in sequences[chapter]['nodes'] if node['type'] == 'dialogText'), None)
    if first is not None and INTRO.match(story_text(first['body'])):
        ref = refs.get(first['header'] or 'Claire') or refs.get((first['header'] or 'Claire').lower())
        expressions = (ref or {'expressions': NARRATOR_DEFAULT})['expressions']
        path = expressions.get(first.get('expression') or '') or expressions['default']
        return path.split('/')[2]
    return narrating(config, sequences)


def narrating(config, sequences):
    """The portrait folder an episode's narration shows most (Claire's, or Troy's, Harper's... where they narrate)."""
    folders = collections.Counter()
    for chapter in [node['sequenceId'] for node in sequences['main']['nodes'] if node['type'] == 'playSequence']:
        refs = refs_for(config['sceneRefs'][chapter])
        ref = refs.get('Claire') or refs.get('claire')
        expressions = (ref or {'expressions': NARRATOR_DEFAULT})['expressions']
        for node in sequences[chapter]['nodes']:
            if node['type'] == 'dialogText' and node['header'] == '':
                path = expressions.get(node.get('expression') or '') or expressions['default']
                folders[path.split('/')[2]] += 1
    return folders.most_common(1)[0][0] if folders else 'ClaireHart'


def markdown_table(path, title, intro, headers, rows):
    """A review list as a Markdown table, for the owner to read (a cell's own | escaped)."""
    def cell(value):
        return str(value).replace('|', r'\|').replace('\n', ' ')
    with open(path, 'w', encoding='utf-8', newline='\n') as file:
        file.write(f'# {title}\n\n{intro}\n\n')
        file.write('| ' + ' | '.join(headers) + ' |\n|' + '---|' * len(headers) + '\n')
        for row in rows:
            file.write('| ' + ' | '.join(cell(value) for value in row) + ' |\n')


def write_reviews(folder, reviews):
    """The owner's lists (2026-11-20): every round, whether it keeps its stand-in line or the next chapter tells it
    (rounds.md), and every episode-end sign-off trimmed (outros.md); their TSVs beside them for scripts."""
    folder = Path(folder)
    for name, headers in (('rounds', ('epid', 'round', 'place', 'finds', 'decision', 'stand-in line',
                                       'next chapter opens')),
                          ('outros', ('epid', 'line', 'kept (empty: the line goes)')),
                          ('intros', ('epid', 'line', 'kept (empty: the line goes)'))):
        with open(folder / f'{name}.tsv', 'w', encoding='utf-8', newline='\n') as file:
            file.write('\t'.join(headers) + '\n')
            for row in reviews[name]:
                file.write('\t'.join(str(value) for value in row) + '\n')
    rounds = reviews['rounds']
    markdown_table(folder / 'rounds.md', 'Claire Hart Classic: rounds as lines',
                   f'With the real rounds off, a round is one stand-in line, unless the next chapter\'s first two lines '
                   f'already tell the search (they name a find, or say "I found..." / "I searched..."). '
                   f'{sum(1 for row in rounds if row[4] == "stand-in")} of {len(rounds)} keep their line.',
                   ('Episode', 'Round', 'Place', 'Finds', 'Decision', 'Stand-in line', 'Next chapter opens'), rounds)
    outros = reviews['outros']
    markdown_table(folder / 'outros.md', "Claire Hart Classic: episode-end sign-offs",
                   f'The store\'s sign-off at an episode\'s end goes (the next episode, Club Pogo, and a call to the '
                   f'player just before it); the story, its questions and season\'s greetings stay. '
                   f'{sum(1 for row in outros if not row[2])} of {len(outros)} lines go whole.',
                   ('Episode', 'Line', 'Kept (blank: the line goes)'), outros)
    intros = reviews.get('intros', [])
    markdown_table(folder / 'intros.md', "Claire Hart Classic: later parts' introductions",
                   'A case\'s later parts open with the player introducing themselves again; that introduction goes (the '
                   'first part keeps it), and the line\'s story stays. '
                   f'{sum(1 for row in intros if not row[2])} of {len(intros)} lines go whole.',
                   ('Episode', 'Line', 'Kept (blank: the line goes)'), intros)


def compiled(project, slices):
    """The case's .exp: the project compiled, with its backdrop slices (resource 7, backdrop_slices.py)."""
    from exp_runtime.backdrop_slices import RESOURCE as SLICES, encode as encode_slices
    from exp_runtime.creator import compile_project
    from exp_runtime.exp import ExpArchive, encode_exp
    archive = ExpArchive(compile_project(project))
    resources = {ident: archive.read(ident) for ident in archive.entries}
    resources[SLICES] = encode_slices(slices)
    return encode_exp(resources)


def mp3(ogg, folder):
    """An OGG as a 128 kb/s MP3, by FFmpeg."""
    out = Path(folder) / 'track.mp3'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(ogg), '-codec:a', 'libmp3lame', '-b:a', '128k', str(out)],
                   check=True)
    return out.read_bytes()


def sequel_file(sequel, real_path):
    """A picture of the sequel's mirror (Claire Hart: Secret in the Shadows), by its path in the game."""
    with open(Path(sequel) / 'bundle_names.csv', encoding='utf-8-sig', newline='') as file:
        row = next(r for r in csv.DictReader(file) if r['real_path'] == real_path and r.get('part') == 'native')
    return Path(sequel) / row['local_path']


def addon(mirror, pairs, catalog, sources, extras, sequel, progress=print):
    """chc's resources {ID: bytes} and a report: chslim revision 1's (`chslim.contents(chc=True)`) and the rest. `sequel`:
    the sequel's mirror, for EXTRA_SCENES (E265's title card)."""
    from PIL import Image
    from exp_runtime.addons import RESOURCE as ADDON_RECORD, provides_bytes
    if shutil.which('ffmpeg') is None:
        raise SystemExit('FFmpeg is needed for the tracks')
    resources, report = chslim.contents(mirror.root, pairs, catalog, sources, extras, chc=True)
    progress(f'chslim revision 1: {len(resources)} resources')
    added = 0
    for path, ident in mirror.picture_ids().items():         # every other portrait, whole (chslim's `whole`)
        if ident not in resources:
            resources[ident] = chslim.png(chslim.whole(Image.open(mirror.files[path]).convert('RGBA')))
            added += 1
    progress(f'portraits: {added} added')
    scenes = mirror.scenes()
    for folder, (ident, _, _) in scenes.items():
        resources[ident] = mirror.backdrop(folder)
    progress(f'backdrops: {len(scenes)}')
    for path, ident in mirror.story_object_ids().items():
        resources[ident] = mirror.files[path].read_bytes()
    tracks = mirror.tracks()
    with tempfile.TemporaryDirectory() as folder:
        for stem, (ident, ogg) in tracks.items():
            resources[ident] = mp3(ogg, folder)
        resources[TITLE_MUSIC] = mp3(mirror.root / JINGLE, folder)
    progress(f'tracks: {len(tracks)} and the jingle')
    resources[TITLE_SPEC] = json.dumps(TITLE_LOOK).encode()
    resources[TITLE_BACKGROUND] = chslim.png(Image.open(mirror.files[FOREST]).convert('RGBA'))
    resources[TITLE_LOGO] = chslim.png(Image.open(mirror.root / ATLAS).convert('RGBA').crop(LOGO))
    spec = mirror.spec()
    for folder, (ident, real_path) in EXTRA_SCENES.items():
        resources[ident] = sequel_file(sequel, real_path).read_bytes()
        with Image.open(sequel_file(sequel, real_path)) as image:
            width, height = image.size
        spec['scenes'][folder] = [ident, (width - round(height * 3 / 4)) // 2]     # centred
    resources[SPEC] = json.dumps(spec, separators=(',', ':')).encode('utf-8')
    resources[ADDON_RECORD] = provides_bytes(chslim.CHC_ID, chslim.CHC_TITLE, chslim.CHC_REVISION,
                                             supersedes=((chslim.ADDON_ID, chslim.ADDON_REVISION),))
    report.update(portraits=len(mirror.portraits()), looks=len(spec['looks']), backdrops=len(scenes),
                  cod_slices=sum(how == 'cod' for _, _, how in scenes.values()), tracks=len(tracks),
                  story_objects=len(spec['story_objects']), resources=len(resources))
    return resources, report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('report', 'ids', 'addon', 'build', 'places', 'rounds'):
        command = commands.add_parser(name)
        command.add_argument('--mirror', type=Path, required=True)
        if name in ('ids', 'build', 'places'):
            command.add_argument('--out', type=Path, required=True, help='(places: a .md file)')
        if name == 'build':
            command.add_argument('--episodes', help='only the cases holding these E-numbers (E001,E018,...)')
            command.add_argument('--cache', type=Path, help='the store scenes matched (made on first use)')
        if name == 'rounds':
            command.add_argument('--out', type=Path, required=True, help='the folder for CH_Classic_Rounds.exp')
            command.add_argument('--scenes', help='only these scene folders (a check build)')
            command.add_argument('--workers', type=int, default=3)
        if name == 'addon':
            command.add_argument('--pairs', type=Path, required=True)
            command.add_argument('--catalog', type=Path, required=True, help="the CoD catalogue's portraits folder")
            command.add_argument('--cod-library', type=Path, required=True)
            command.add_argument('--extras', type=Path, required=True)
            command.add_argument('--sequel', type=Path, required=True, help="the sequel's mirror (E265's title card)")
            command.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    mirror = Mirror(args.mirror)
    if args.command == 'ids':
        rows = mirror.ids()
        with open(args.out, 'w', encoding='utf-8', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=list(rows[0]), delimiter='\t', lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)
        print(f'{len(rows)} episodes in {len({row["case"] for row in rows})} cases -> {args.out}')
    elif args.command == 'build':
        wanted = set(args.episodes.split(',')) if args.episodes else None
        art = converter_art(mirror, args.cache)
        args.out.mkdir(parents=True, exist_ok=True)
        reviews = dict(rounds=[], outros=[], intros=[])
        for _, case, parts in mirror.cases():
            if wanted is not None and not wanted & {config['epid'] for _, config, _ in parts}:
                continue
            project, slices, report = convert(mirror, art, case, parts)
            reviews['rounds'] += report.reviews['rounds']
            reviews['outros'] += report.reviews['outros']
            reviews['intros'] += report.reviews['intros']
            name = f"CHC_{case['index']:03d}.exp"
            (args.out / name).write_bytes(compiled(project, slices))
            print(f'{name}: {project.title!r}, {len(project.nodes)} nodes, {dict(report)}')
        write_reviews(args.out, reviews)
    elif args.command == 'rounds':
        import claire_rounds_addon
        args.out.mkdir(parents=True, exist_ok=True)
        out = args.out / 'CH_Classic_Rounds.exp'
        report = claire_rounds_addon.build(mirror, out, only=set(args.scenes.split(',')) if args.scenes else None,
                                           workers=args.workers)
        print(f"addon: {claire_rounds_addon.ROUNDS_TITLE!r} -> {out} ({report['bytes'] // 2 ** 20} MB), {report}")
    elif args.command == 'places':
        scenes = sorted({hog['scene'] for _, _, parts in mirror.cases() for _, config, _ in parts
                         for hog in config['hogConfig'].values()})
        markdown_table(args.out, 'Claire Hart Classic: round scenes as the lines name them',
                       'A round line says "Claire searches <place>." Proper names that should take no "the" go in '
                       'PROPER_PLACES; data spellings that read oddly, in SCENE_NAMES.',
                       ('Scene (as the data spells it)', 'Said as'), [(scene, place(scene)) for scene in scenes])
        print(f'{len(scenes)} round scenes -> {args.out}')
    elif args.command == 'report':
        cases = mirror.cases()
        banks, _, slots = mirror.look_banks()
        scenes = mirror.scenes()
        resolved = mirror.story_objects()
        print(f'cases {len(cases)}, episodes {sum(len(parts) for _, _, parts in cases)}')
        print(f'portraits {len(mirror.portraits())}, looks {len(banks)}, faces shown in a look\'s own slot {len(slots)}')
        print(f'scenes {len(scenes)}: at CoD\'s cut {sum(h == "cod" for _, _, h in scenes.values())}, '
              f'centred {sum(h == "centre" for _, _, h in scenes.values())}')
        print(f'tracks {len(mirror.tracks())}, story-object pictures {len(mirror.story_object_ids())}')
        print(f'story-object list entries {len(resolved)}: resolve {sum(item is not None for *_, item in resolved)}')
    else:
        from exp_runtime.exp import encode_exp
        resources, report = addon(mirror, chslim.read_pairs(args.pairs.read_text(encoding='utf-8')), args.catalog,
                                  chslim.library_pictures(args.cod_library), args.extras, args.sequel)
        args.out.mkdir(parents=True, exist_ok=True)
        data = encode_exp(resources)
        del resources
        (args.out / 'CH_Classic.exp').write_bytes(data)
        print(f'addon: {chslim.CHC_TITLE!r} -> {args.out / "CH_Classic.exp"} ({len(data) // 2 ** 20} MB), {report}')
        return 1 if report['unfound'] else 0
    return 0


if __name__ == '__main__':
    sys.exit(main())
