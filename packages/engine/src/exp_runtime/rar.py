"""Bounded RAR4/RAR5 reading through libarchive, without external commands.

Apple platforms use the OS library. Desktop builds for Windows/Linux bundle
libarchive; source checkouts can use a locally installed copy. Only the RAR
decoders are enabled, and archive member paths are never used as output paths.
"""
import ctypes as c
from functools import lru_cache
import os
from pathlib import Path
import sys


class RarError(ValueError):
    pass


@lru_cache(maxsize=1)
def library():
    if sys.platform in ('darwin', 'ios'):
        candidates = ['/usr/lib/libarchive.2.dylib']
    else:
        from ctypes.util import find_library
        name = 'archive.dll' if sys.platform == 'win32' else 'libarchive.so.13'
        root = Path(__file__).resolve().parents[2]
        candidates = [str(Path(getattr(sys, '_MEIPASS', root)) / name),
                      str(root / 'build/rar/install' / ('bin' if sys.platform == 'win32' else 'lib') / name),
                      find_library('archive')]
    for path in filter(None, candidates):
        try:
            lib = c.CDLL(path)
            signatures = {
                'archive_read_new': (c.c_void_p, []),
                'archive_read_support_format_rar': (c.c_int, [c.c_void_p]),
                'archive_read_support_format_rar5': (c.c_int, [c.c_void_p]),
                'archive_read_open_filename': (c.c_int, [c.c_void_p, c.c_char_p, c.c_size_t]),
                'archive_read_next_header': (c.c_int, [c.c_void_p, c.POINTER(c.c_void_p)]),
                'archive_read_data': (c.c_ssize_t, [c.c_void_p, c.c_void_p, c.c_size_t]),
                'archive_read_data_skip': (c.c_int, [c.c_void_p]),
                'archive_read_free': (c.c_int, [c.c_void_p]),
                'archive_error_string': (c.c_char_p, [c.c_void_p]),
                'archive_entry_pathname_utf8': (c.c_char_p, [c.c_void_p]),
                'archive_entry_size': (c.c_int64, [c.c_void_p]),
                'archive_entry_filetype': (c.c_uint, [c.c_void_p]),
                'archive_entry_symlink': (c.c_char_p, [c.c_void_p]),
                'archive_entry_hardlink': (c.c_char_p, [c.c_void_p]),
                'archive_entry_is_encrypted': (c.c_int, [c.c_void_p]),
            }
            if sys.platform == 'win32':
                signatures['archive_read_open_filename_w'] = (c.c_int, [c.c_void_p, c.c_wchar_p, c.c_size_t])
            for name, (result, args) in signatures.items():
                function = getattr(lib, name)
                function.restype, function.argtypes = result, args
            return lib
        except (OSError, AttributeError):
            continue
    raise RarError('RAR support needs libarchive with RAR5 support. Install libarchive or use an '
                   'EXP Runtime desktop download. You can also import the extracted EXP files.')


class RarReader:
    """Single-pass archive. Read or skip each member before advancing."""
    def __init__(self, path):
        self.lib, self.handle = library(), None
        with Path(path).open('rb') as stream:
            magic = stream.read(8)
        if not (magic.startswith(b'Rar!\x1a\x07\x00') or magic == b'Rar!\x1a\x07\x01\x00'):
            raise RarError('Invalid RAR signature')
        self.handle = self.lib.archive_read_new()
        if not self.handle:
            raise RarError('Cannot allocate the RAR reader')
        try:
            self.check(self.lib.archive_read_support_format_rar(self.handle))
            self.check(self.lib.archive_read_support_format_rar5(self.handle))
            if sys.platform == 'win32':
                self.check(self.lib.archive_read_open_filename_w(self.handle, str(Path(path)), 65536))
            else:
                self.check(self.lib.archive_read_open_filename(self.handle, os.fsencode(path), 65536))
        except BaseException:
            self.close()
            raise

    def check(self, status):
        if status < 0:
            raw = self.lib.archive_error_string(self.handle)
            raise RarError(raw.decode('utf-8', 'replace') if raw else 'Invalid or unsupported RAR archive')
        return status

    def __iter__(self):
        while True:
            entry = c.c_void_p()
            status = self.check(self.lib.archive_read_next_header(self.handle, c.byref(entry)))
            if status == 1:  # ARCHIVE_EOF
                return
            raw = self.lib.archive_entry_pathname_utf8(entry)
            if raw is None:
                raise RarError('RAR member has an invalid filename')
            try:
                name = raw.decode('utf-8')
            except UnicodeDecodeError as error:
                raise RarError('RAR member has an invalid filename') from error
            yield dict(name=name, size=self.lib.archive_entry_size(entry),
                       mode=self.lib.archive_entry_filetype(entry),
                       link=bool(self.lib.archive_entry_symlink(entry) or self.lib.archive_entry_hardlink(entry)),
                       encrypted=bool(self.lib.archive_entry_is_encrypted(entry)))

    def skip(self):
        self.check(self.lib.archive_read_data_skip(self.handle))

    def copy_to(self, destination, size):
        buffer, total = c.create_string_buffer(65536), 0
        while True:
            count = self.check(self.lib.archive_read_data(self.handle, buffer, len(buffer)))
            if count == 0:
                break
            total += count
            if total > size:
                raise RarError('RAR member exceeds its declared size')
            destination.write(buffer.raw[:count])
        if total != size:
            raise RarError('RAR member is truncated')

    def close(self):
        if self.handle:
            self.lib.archive_read_free(self.handle)
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
