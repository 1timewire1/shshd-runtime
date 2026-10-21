"""Consistent MCP results with a bounded view and recoverable full output."""
from functools import wraps
import json
import uuid

from .model import ProjectError


def register(server, workspace, annotations):
    from mcp.types import CallToolResult, TextContent
    def response(value, *, error=False):
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
        if len(encoded.encode()) > 18000:
            key = uuid.uuid4().hex
            workspace.responses[key] = encoded
            while len(workspace.responses) > 8: workspace.responses.pop(next(iter(workspace.responses)))
            value = {k: value[k] for k in ('revision', 'valid', 'passed', 'session', 'live', 'unsaved', 'error') if k in value}
            value.update(result_id=key, truncated=True, characters=len(encoded), next_offset=0,
                         preview=encoded[:800], next_action='Use result_read to retrieve bounded slices of the full JSON.')
            encoded = json.dumps(value, ensure_ascii=False)
        return CallToolResult(content=[TextContent(type='text', text=encoded)], structuredContent=value, isError=error)
    def tool(*, name=None, title=None):
        def decorate(fn):
            @wraps(fn)
            def invoke(*args, **kwargs):
                try:
                    with workspace.lock:
                        result = fn(*args, **kwargs)
                    return result if isinstance(result, CallToolResult) else response(result)
                except (ProjectError, ValueError, KeyError, TypeError, OSError) as error:
                    from .sharing import SharingError
                    message = str(error)
                    stale = 'changed;' in message.lower()
                    code = 'stale_revision' if stale else getattr(error, 'code', 'invalid_request')
                    recovery = ('Call project_get and reapply against its revision.' if stale else
                                'Finish the desktop interaction, then call project_get and retry.' if code == 'project_busy' else
                                'Reopen the project in the desktop creator, then call project_get before retrying.'
                                if isinstance(error, SharingError) else
                                'Check the indicated IDs, paths and schema_get requirements, then retry.')
                    return response(dict(error=dict(code=code, message=message, recovery=recovery)), error=True)
            server.tool(name=name, title=title, annotations=annotations)(invoke)
            return invoke
        return decorate
    return tool


def media_result(data, mime_type, metadata):
    import base64
    from mcp.types import AudioContent, CallToolResult, ImageContent, TextContent
    block = ImageContent if mime_type.startswith('image/') else AudioContent
    return CallToolResult(content=[TextContent(type='text', text=json.dumps(metadata)),
        block(type='image' if mime_type.startswith('image/') else 'audio',
              data=base64.b64encode(data).decode(), mimeType=mime_type)], structuredContent=metadata)
