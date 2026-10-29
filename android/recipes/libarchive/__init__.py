"""libarchive for RAR import on Android (exp_runtime.rar), built as the desktop downloads build it (tools/build_rar.py):
the same pinned release, only the RAR decoders' needs, no compression libraries, tools or tests. The APK carries
libarchive.so; rar.py loads it by name. Its licence goes into the app's licenses folder (tools/build_android.stage)."""
from pathlib import Path

import sh
from pythonforandroid.logger import shprint
from pythonforandroid.recipe import Recipe
from pythonforandroid.util import current_directory


class LibarchiveRecipe(Recipe):
    name = 'libarchive'
    version = '3.8.9'
    url = 'https://github.com/libarchive/libarchive/releases/download/v{version}/libarchive-{version}.tar.xz'
    # tools/build_rar.py pins the release's SHA-256 (888c934f...); python-for-android checks SHA-512: the same file's.
    sha512sum = ('f37425417a9e3fdc194a2b892137452ddba6601c69e822598692d4d776c573a9'
                 '0e70aac4598d47c915615facc45d0c83fc46c24856ddf04afd7494b63bb9f137')
    built_libraries = {'libarchive.so': 'install/lib'}
    # As tools/build_rar.py: RAR reading needs none of these (CMake's Android platform builds no versioned soname).
    DISABLED = ('MBEDTLS NETTLE OPENSSL LIBB2 LZ4 LZO LZMA ZSTD ZLIB BZip2 LIBXML2 EXPAT WIN32_XMLLITE PCREPOSIX '
                'PCRE2POSIX LIBGCC TAR CPIO CAT UNZIP XATTR ACL ICONV TEST COVERAGE CLANG_TIDY CNG').split()

    def build_arch(self, arch):
        env = self.get_recipe_env(arch)
        toolchain = Path(self.ctx.ndk_dir) / 'build/cmake/android.toolchain.cmake'
        with current_directory(self.get_build_dir(arch.arch)):
            shprint(sh.rm, '-rf', 'cmake', 'install')
            shprint(sh.cmake, '-S', '.', '-B', 'cmake', '-G', 'Unix Makefiles',
                    f'-DCMAKE_TOOLCHAIN_FILE={toolchain}', f'-DANDROID_ABI={arch.arch}',
                    f'-DANDROID_PLATFORM=android-{self.ctx.ndk_api}',
                    '-DCMAKE_BUILD_TYPE=Release', '-DBUILD_SHARED_LIBS=ON',
                    '-DCMAKE_INSTALL_PREFIX=./install', '-DCMAKE_INSTALL_LIBDIR=lib',
                    '-DENABLE_INSTALL=ON', '-DPOSIX_REGEX_LIB=NONE',
                    *[f'-DENABLE_{name}=OFF' for name in self.DISABLED], _env=env)
            shprint(sh.cmake, '--build', 'cmake', '--parallel', '4', _env=env)
            shprint(sh.cmake, '--install', 'cmake', _env=env)


recipe = LibarchiveRecipe()
