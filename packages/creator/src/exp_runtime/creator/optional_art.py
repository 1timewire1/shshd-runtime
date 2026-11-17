"""shshd-runtime: what an optional add-on can show in place of a project's own pictures (presentation `optional_art`; owner,
2026-11-17): Surviving Hollywood's pictures by number (Hollywood Art), and the DSi's locations by their left screen (DSi
Backgrounds, exp_runtime.dsi)."""
import json

DSI_SPEC = 26000          # exp_runtime.dsi.SPEC


def addon_pictures(library, addon):
    """[(label, the add-on's picture)] a project picture can be shown as, [] without the add-on in the library."""
    found = library.addon(addon) if library is not None and hasattr(library, 'addon') else None
    if found is None:
        return []
    record, archive = found
    if addon == 'shsdsi':
        try:
            spec = json.loads(archive.read(DSI_SPEC))
        except (KeyError, ValueError, OSError):
            return []
        return [(f'{name} (DSi)', screens[0]) for name, screens in sorted(spec.get('screens', {}).items()) if screens]
    from .model import is_image
    pictures = []
    for resource in sorted(archive.entries):
        if 26000 <= resource <= 32767:
            try:
                if is_image(archive.read(resource)[:8]):
                    pictures.append((f'{resource} ({record.get("title", addon)})', resource))
            except (KeyError, OSError):
                continue
    return pictures
