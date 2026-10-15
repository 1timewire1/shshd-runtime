"""Local desktop discovery, bounded JSON transport and cooperative file locks.

The desktop owns its live document. MCP clients read snapshots and submit a
revision-checked replacement; an unavailable desktop never falls back to disk.
This module has no Qt or MCP dependency.
"""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import struct

from .model import (MAX_PROJECT_BYTES, Project, ProjectError, atomic_write, project_bytes,
                    project_from_bytes, project_from_record)

MAX_MESSAGE = MAX_PROJECT_BYTES * 2
TIMEOUT = 15


class SharingError(ProjectError):
    code = 'desktop_unavailable'


class ProjectBusy(SharingError):
    code = 'project_busy'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def state_path(path, suffix):
    path = Path(path).resolve()
    folder = path.parent / '.creator-session'
    if folder.is_symlink(): raise SharingError('The creator session directory must not be a symlink')
    return folder / (digest(path.name.encode()) + suffix)


class FileLock:
    """Nonblocking process lock; the OS releases it if the owner crashes."""
    def __init__(self, path):
        self.path, self.stream = Path(path), None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.is_symlink(): raise SharingError('Creator lock files must not be symlinks')
        self.stream = open(self.path, 'a+b')
        if not self.stream.seek(0, 2):
            self.stream.write(b'\0'); self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.stream.close(); self.stream = None
            raise ProjectBusy('Project is busy in another operation or desktop window; retry after it finishes.') from error
        return self

    def __exit__(self, *args):
        if self.stream is not None:
            self.stream.close()
            self.stream = None


def guard(path):
    if not Path(path).resolve().parent.is_dir(): raise ProjectError('Project directory must already exist')
    return FileLock(state_path(path, '.lock'))


def session_info(path):
    marker = state_path(path, '.json')
    try:
        if marker.is_symlink() or marker.stat().st_size > 4096:
            raise ValueError('Invalid desktop session file')
        record = json.loads(marker.read_bytes())
        if (not isinstance(record, dict) or record.get('version') != 1
                or record.get('path') != str(Path(path).resolve())
                or type(record.get('port')) is not int or not 1 <= record['port'] <= 65535
                or not isinstance(record.get('token'), str) or len(record['token']) != 64):
            raise ValueError('Invalid desktop session record')
        return record
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as error:
        raise SharingError('Cannot read the desktop session. Reopen the project in the creator.') from error


class Lease:
    """One desktop window may own a saved project at a time."""
    def __init__(self, path, port):
        self.path = Path(path).resolve()
        self.owner = FileLock(state_path(self.path, '.owner'))
        self.record = dict(version=1, path=str(self.path), port=port, token=secrets.token_hex(32))
        with guard(self.path):
            self.owner.__enter__()
            try:
                atomic_write(state_path(self.path, '.json'), json.dumps(self.record).encode())
            except BaseException:
                self.owner.__exit__()
                raise

    def close(self):
        if self.owner.stream is not None:
            # The owner lock prevents another window replacing this record.
            try: state_path(self.path, '.json').unlink(missing_ok=True)
            finally: self.owner.__exit__()


def encode_message(record):
    data = json.dumps(record, ensure_ascii=False, allow_nan=False).encode()
    if len(data) > MAX_MESSAGE: raise ProjectError('Desktop request exceeds the project size limit')
    return struct.pack('>I', len(data)) + data


def _receive(stream, size):
    data = bytearray()
    while len(data) < size:
        part = stream.recv(min(size - len(data), 1024 * 1024))
        if not part: raise OSError('Desktop connection closed')
        data.extend(part)
    return bytes(data)


def request(info, action, **values):
    try:
        with socket.create_connection(('127.0.0.1', info['port']), timeout=TIMEOUT) as stream:
            stream.sendall(encode_message(dict(token=info['token'], path=info['path'], action=action, **values)))
            size, = struct.unpack('>I', _receive(stream, 4))
            if not 0 < size <= MAX_MESSAGE: raise ValueError('Invalid desktop response size')
            response = json.loads(_receive(stream, size))
            if not isinstance(response, dict): raise ValueError('Invalid desktop response')
    except (OSError, ValueError) as error:
        raise SharingError('Desktop session is unavailable; reopen the project in the creator, then reread it '
                           'before retrying. No fallback file write was attempted.') from error
    if 'error' in response:
        kind = ProjectBusy if response.get('code') == 'project_busy' else ProjectError
        raise kind(response['error'])
    return response


@dataclass
class Snapshot:
    project: Project
    revision: str
    data: bytes
    live: bool = False
    unsaved: bool = False


def snapshot(path):
    path = Path(path).resolve()
    with guard(path):
        info = session_info(path)
        if info is None:
            if path.stat().st_size > MAX_PROJECT_BYTES: raise ProjectError('Project file exceeds 96 MiB')
            data = path.read_bytes()
            return Snapshot(project_from_bytes(data, path), digest(data), data)
    response = request(info, 'read')
    project = project_from_record(response['project'])
    data = project_bytes(project, path)
    if digest(data) != response['revision']: raise SharingError('Desktop snapshot checksum does not match')
    return Snapshot(project, response['revision'], data, True, response['unsaved'])
