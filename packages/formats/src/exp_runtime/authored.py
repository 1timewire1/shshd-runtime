"""Optional authoring metadata. Native players may ignore resource 2 entirely."""
import json
from .exp import ContentError

RESOURCE = 2
MAGIC = b'EXP-RUNTIME-AUTHORED\0'


def authoring_record(archive):
    if RESOURCE not in archive.entries:
        return None
    data = archive.read(RESOURCE)
    if not data.startswith(MAGIC):
        return None
    try:
        record = json.loads(data[len(MAGIC):])
        if not isinstance(record, dict) or record.get('format') != 'exp-runtime-authored' or record.get('version') != 1:
            raise ValueError('unsupported metadata version')
        if record.get('project') is not None and not isinstance(record['project'], dict):
            raise ValueError('project must be an object')
        return record
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ContentError(f'Invalid authoring metadata: {error}') from error
