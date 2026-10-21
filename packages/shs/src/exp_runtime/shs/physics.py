"""Single-precision stores used by the native minigame physics."""
import struct


def float32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]
