"""Public file-tools API; requires neither the engine nor a game adapter.

``ExpArchive.read`` returns a resource's decompressed bytes by exact ID.
Decoded ``KiwiProgram`` objects retain their lossless ``to_bytes`` contract.
Image/font parsers return data, without initializing a display or audio host.
"""
from .exp import ContentError, ExpArchive, Metadata
from .decode.bytecode import KiwiFormatError, KiwiProgram, decode_program
from .fonts import BitmapFont, FontError
from .atlas import AtlasFont, SpriteAtlas
from .ui_assets import ImagePack, LayoutBank, UIAssetError
from .menu_assets import MenuFont, MenuStrings

__all__ = [
    'ContentError', 'ExpArchive', 'Metadata', 'KiwiFormatError', 'KiwiProgram',
    'decode_program', 'BitmapFont', 'FontError', 'AtlasFont', 'SpriteAtlas',
    'ImagePack', 'LayoutBank', 'UIAssetError', 'MenuFont', 'MenuStrings',
]
