"""Build the pinned libarchive dependency for Windows/Linux desktop downloads.

macOS/iOS use the OS library. No unrar executable is needed. CMake and a native
C compiler are build-time requirements only; external compression libraries,
command-line tools and tests are disabled.
"""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request


VERSION = '3.8.9'
SHA256 = '888c934f9d95648ecb9163dc8e23ab80a476ecb81a8f1154704a227b5b676dde'
URL = f'https://github.com/libarchive/libarchive/releases/download/v{VERSION}/libarchive-{VERSION}.tar.xz'
ROOT = Path(__file__).resolve().parents[1]


def source_archive(*, offline=False):
    """The pinned libarchive release, downloaded once into build/rar and checked against SHA256."""
    directory = ROOT / 'build/rar'
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / f'libarchive-{VERSION}.tar.xz'
    if not archive.exists():
        if offline:
            raise ValueError('libarchive source is not cached; build once without --offline')
        temporary = archive.with_suffix('.download')
        try:
            with urllib.request.urlopen(URL, timeout=60) as response, temporary.open('wb') as output:
                shutil.copyfileobj(response, output)
            if hashlib.sha256(temporary.read_bytes()).hexdigest() != SHA256:
                raise ValueError('libarchive source checksum mismatch')
            temporary.replace(archive)
        finally:
            temporary.unlink(missing_ok=True)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
        raise ValueError('libarchive source checksum mismatch')
    return archive


def notices(source):
    """Upstream's licensing plus the individual source files' copyright headers (an extracted release)."""
    notices = [(source / 'COPYING').read_text()]
    for path in sorted((source / 'libarchive').glob('*')):
        if path.suffix in ('.c', '.h'):
            text = path.read_text(errors='replace')
            if text.startswith('/*') and '*/' in text:
                notices.append(path.name + '\n' + text[:text.index('*/') + 2])
    return '\n\n'.join(notices)


def license_text(*, offline=False):
    """The notices for a build that carries libarchive without this script building it (the Android APK's)."""
    with tempfile.TemporaryDirectory() as directory, tarfile.open(source_archive(offline=offline)) as source:
        source.extractall(directory, **({'filter': 'data'} if hasattr(tarfile, 'data_filter') else {}))
        return notices(Path(directory) / f'libarchive-{VERSION}')


def build(*, offline=False):
    if sys.platform == 'darwin':
        return None
    directory = ROOT / 'build/rar'
    archive = source_archive(offline=offline)
    install = directory / 'install'
    binary = install / ('bin/archive.dll' if sys.platform == 'win32' else 'lib/libarchive.so.13')
    marker = install / '.source-sha256'
    license = install / 'libarchive-LICENSE.txt'
    if binary.is_file() and license.is_file() and marker.is_file() and marker.read_text() == SHA256:
        return binary, license
    with tarfile.open(archive) as source:
        source.extractall(directory, **({'filter': 'data'} if hasattr(tarfile, 'data_filter') else {}))
    source = directory / f'libarchive-{VERSION}'
    disabled = ('MBEDTLS NETTLE OPENSSL LIBB2 LZ4 LZO LZMA ZSTD ZLIB BZip2 LIBXML2 EXPAT '
                'WIN32_XMLLITE PCREPOSIX PCRE2POSIX LIBGCC TAR CPIO CAT UNZIP '
                'XATTR ACL ICONV TEST COVERAGE CLANG_TIDY').split()
    # RAR import does not use regex. libarchive 3.8.9's AUTO provider search
    # requires libgcc on MSVC even when both PCRE providers are disabled.
    args = ['cmake', '-S', str(source), '-B', str(directory / 'cmake'),
            '-DCMAKE_BUILD_TYPE=Release', '-DBUILD_SHARED_LIBS=ON',
            f'-DCMAKE_INSTALL_PREFIX={install}', '-DCMAKE_INSTALL_LIBDIR=lib',
            '-DENABLE_INSTALL=ON', '-DPOSIX_REGEX_LIB=NONE',
            # Windows random/temp-file helpers require the system BCrypt API
            # even without encrypted archives. CNG enables its link library.
            f'-DENABLE_CNG={"ON" if sys.platform == "win32" else "OFF"}',
            *[f'-DENABLE_{name}=OFF' for name in disabled]]
    # Bundle the C runtime with the DLL instead of requiring a separately
    # installed Visual C++ runtime on the player's machine.
    if sys.platform == 'win32':
        args.append('-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded')
    subprocess.run(args, check=True)
    subprocess.run(['cmake', '--build', str(directory / 'cmake'), '--config', 'Release', '--parallel', '4'], check=True)
    subprocess.run(['cmake', '--install', str(directory / 'cmake'), '--config', 'Release'], check=True)
    if not binary.is_file():
        raise ValueError(f'libarchive build did not produce {binary.name}')
    # Include upstream licensing plus the individual source copyright headers.
    license.write_text(notices(source), encoding='utf-8')
    marker.write_text(SHA256)
    return binary, license


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline', action='store_true')
    result = build(offline=parser.parse_args().offline)
    print(f'RAR decoder: {result[0]}' if result else 'RAR decoder: macOS system libarchive')
