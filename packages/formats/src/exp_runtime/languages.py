"""Language slots in EXP title metadata, independent of story bytecode.

The supplied packages have one UI string bank and one script per scene.
Selecting a title slot cannot select or translate dialogue. See MAIN_MENU.md.
"""


# EXP record 1 order; native menu strings 118..122 use the same order.
TITLE_LANGUAGES = ('en', 'fr', 'it', 'de', 'es')


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
