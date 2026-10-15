"""Paginated, content-derived asset discovery. Never guess original names."""
from exp_runtime.content import ContentLibrary
from .graph import page
from .media import inspect_asset


def library_assets(workspace, library, *, episode=None, kind=None, query='', offset=0, limit=50):
    page(offset, limit)
    with ContentLibrary(workspace.path(library)) as content:
        resources = content.open_episode(episode) if episode else content
        read = resources.archive.read if episode else content.read_asset
        ids = sorted(resources.archive.entries if episode else content.base_members.keys() | content.music_members.keys())
        found = []
        # Metadata is derived only for matching IDs. A type filter requires
        # inspection, so bound every scan and return a continuation offset.
        index = offset
        while index < len(ids) and index < offset + 200 and len(found) < limit:
            resource = ids[index]; index += 1
            if query.casefold() not in str(resource): continue
            info = inspect_asset(read(resource))
            if kind and info['type'] != kind: continue
            found.append(dict(id=resource, name=None, **info))
        return dict(assets=found, total_resources=len(ids), scanned=index - offset,
                    next_offset=index if index < len(ids) else None)


def read_asset(workspace, library, resource, episode=None):
    with ContentLibrary(workspace.path(library)) as content:
        resources = content.open_episode(episode) if episode else content
        return resources.archive.read(resource) if episode else content.read_asset(resource)
