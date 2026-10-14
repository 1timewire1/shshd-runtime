"""Native services 17/40 name editing, independent of the desktop and VM.

See docs/NAME_INPUT.md. The width check is on the existing text plus the
cursor, before appending the next character (FUN_000d3cb0).
"""
from .fonts import BitmapFont


MAX_NAME_LENGTH = 16
NAME_FONT = 'ArialRoundedMTBold28'
CURSOR_FONT = 'PajamaHip26'
NAME_ENTRY_ERROR = (
    'The name entry screen only supports the following alphanumeric '
    'characters: A-Z and 0-9.'
)


def input_fonts(resources):
    if getattr(getattr(resources, 'library', None), 'kind', 'apk') == 'ipa':
        return 'PajamaHip24', 'PajamaHip24'
    return NAME_FONT, CURSOR_FONT


def _alphanumeric(text: str) -> bool:
    return all('a' <= c <= 'z' or 'A' <= c <= 'Z' or '0' <= c <= '9' for c in text)


def _has_room(current: str, font: BitmapFont | None, cursor_width: float) -> bool:
    # Kerning shifts ink, not the native measuring pen. Authored headless
    # fixtures without APK fonts can still exercise the byte/length rules.
    return font is None or sum(font.glyph(c).advance for c in current) + cursor_width < 240


def accept_name_character(current: str, char: str, *, font: BitmapFont | None = None,
                          cursor_width: float = 0) -> tuple[str, str | None]:
    if (len(char) != 1 or not _alphanumeric(char) or len(current) >= MAX_NAME_LENGTH
            or not _alphanumeric(current) or not _has_room(current, font, cursor_width)):
        return current, NAME_ENTRY_ERROR
    if current and 'A' <= char <= 'Z':
        char = char.lower()
    return current + char, None


def validate_name(value: str, *, font: BitmapFont | None = None, cursor_width: float = 0):
    """Validate a confirmed value without recasing script defaults or callers.

    A final character may cross the width threshold: native checks the prefix
    before accepting it. Empty Return hides the keyboard; it never resumes.
    """
    if not isinstance(value, str) or len(value) > MAX_NAME_LENGTH or not _alphanumeric(value):
        raise ValueError(NAME_ENTRY_ERROR)
    if not value:
        raise ValueError('Enter a name before continuing.')
    if not _has_room(value[:-1], font, cursor_width):
        raise ValueError(NAME_ENTRY_ERROR)
