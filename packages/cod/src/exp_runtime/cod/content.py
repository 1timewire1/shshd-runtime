"""Cause of Death's bundled Volume One is itself an EXP at base resource 12."""
BUILTIN = 'volume-one'


def extract_builtin(package, asset_root, *, ios):
    from ..content import _zip_read
    return _zip_read(package, asset_root + '12'), 'Volume_One.exp', dict(builtin=BUILTIN)
