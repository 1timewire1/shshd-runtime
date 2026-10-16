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


def cursor_alpha(elapsed_ms, *, ios=False):
    # Android d4658 repeats CCFadeIn(.5); iOS a0238 gives SHSAnimSprite
    # one 200ms frame followed by 200ms dead time.
    return (255 if elapsed_ms % 400 < 200 else 0) if ios else int(255 * (elapsed_ms % 500) / 500)


def input_fonts(resources):
    if getattr(getattr(resources, 'library', None), 'kind', 'apk') == 'ipa':
        return 'PajamaHip24', 'PajamaHip24'
    return NAME_FONT, CURSOR_FONT


def _alphanumeric(text: str, *, allow_space: bool = False) -> bool:
    return all('a' <= c <= 'z' or 'A' <= c <= 'Z' or '0' <= c <= '9'
               or (allow_space and c == ' ') for c in text)


def _has_room(current: str, font: BitmapFont | None, cursor_width: float) -> bool:
    # Kerning shifts ink, not the native measuring pen. Authored headless
    # fixtures without APK fonts can still exercise the byte/length rules.
    return font is None or sum(font.glyph(c).advance for c in current) + cursor_width < 240


def accept_name_character(current: str, char: str, *, font: BitmapFont | None = None,
                          cursor_width: float = 0, allow_space: bool = False,
                          capitalize_first: bool = False) -> tuple[str, str | None]:
    if (len(char) != 1 or not _alphanumeric(char, allow_space=allow_space)
            or len(current) >= MAX_NAME_LENGTH or not _alphanumeric(current, allow_space=allow_space)
            or not _has_room(current, font, cursor_width)):
        return current, NAME_ENTRY_ERROR
    if capitalize_first:
        # CoD 0003b872..0003b89e capitalizes an initial lowercase character;
        # subsequent characters retain their input case.
        if not current and 'a' <= char <= 'z':
            char = char.upper()
    elif current and 'A' <= char <= 'Z':
        char = char.lower()
    return current + char, None


def validate_name(value: str, *, font: BitmapFont | None = None, cursor_width: float = 0,
                  allow_space: bool = False):
    """Validate a confirmed value without recasing script defaults or callers.

    A final character may cross the width threshold: native checks the prefix
    before accepting it. Empty Return hides the keyboard; it never resumes.
    """
    # CoD spaces are an owner-requested convenience. The native filter rejects
    # them; inspected puzzles also have space-free solutions. Do not trim or
    # recase confirmed values before the script's exact string comparisons.
    if (not isinstance(value, str) or len(value) > MAX_NAME_LENGTH
            or not _alphanumeric(value, allow_space=allow_space)):
        raise ValueError(NAME_ENTRY_ERROR)
    if not value.strip(' '):
        raise ValueError('Enter a name before continuing.')
    if not _has_room(value[:-1], font, cursor_width):
        raise ValueError(NAME_ENTRY_ERROR)
