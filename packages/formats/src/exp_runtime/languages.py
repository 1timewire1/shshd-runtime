"""Language slots in EXP title metadata, independent of story bytecode.

The supplied packages have one UI string bank and one script per scene.
Selecting a title slot cannot select or translate dialogue. See MAIN_MENU.md.
"""


# EXP record 1 order; native menu strings 118..122 use the same order.
TITLE_LANGUAGES = ('en', 'fr', 'it', 'de', 'es')

# shshd-runtime: General's "Preferred Language" (owner, 2026-11-18), one choice in place of Episode Titles and the
# add-ons' DSi Language, '11 Language and Story Language: each takes it where it has it. The four stay the names the
# rest of the player reads (`language_settings`).
PREFERRED_LANGUAGES = TITLE_LANGUAGES
LANGUAGE_SETTINGS = ('title_language', 'dsi_language', 'shs11_language', 'story_language')
_OFFERED = dict(title_language=TITLE_LANGUAGES, dsi_language=('fr', 'it', 'de', 'es'), shs11_language=('it',),
                story_language=TITLE_LANGUAGES)


def language_settings(preferred):
    """{setting: its value} for the Preferred Language `preferred`: the episode titles in it, and each add-on's stories in
    it where that add-on has it ('off' where it doesn't: the DSi's and '11's own English is 'off')."""
    return {key: preferred if preferred in _OFFERED[key] else ('en' if key == 'title_language' else 'off')
            for key in LANGUAGE_SETTINGS}


def with_preferred(options):
    """Shared options from before Preferred Language (an older device's sync, an older backup) with it added, from their
    four (preferred_from); others as they are."""
    if 'preferred_language' in options or not any(key in options for key in LANGUAGE_SETTINGS):
        return options
    return dict(options, preferred_language=preferred_from(options))


def with_language_settings(options):
    """Shared options as sent to another device, with the four Preferred Language replaced as well (language_settings),
    so one from before it takes them."""
    if options.get('preferred_language') not in PREFERRED_LANGUAGES:
        return options
    return dict(options, **language_settings(options['preferred_language']))


def preferred_from(values):
    """The Preferred Language a settings file written before it means: the first of its four language settings that
    isn't English ('en' or 'off'), else English."""
    for key in LANGUAGE_SETTINGS:
        value = values.get(key)
        if value in PREFERRED_LANGUAGES and value != 'en':
            return value
    return 'en'


def episode_title(record, language='en'):
    """Use the requested title, then English, then the source filename.

    Empty translated fields occur in valid metadata. Repeated English titles
    are also valid and do not establish which language the story contains.
    """
    if language not in TITLE_LANGUAGES:
        raise ValueError(f'Unsupported episode title language: {language!r}')
    for title in (record['titles'][TITLE_LANGUAGES.index(language)], record['titles'][0]):
        if title.strip():
            return title
    return record['name']
