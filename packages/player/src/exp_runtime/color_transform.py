"""Opaque RGB matrix transforms shared by SDL and the native drawing oracle."""


def transform_rgb(pixels, matrix):
    output = bytearray(len(pixels))
    for offset in range(0, len(pixels), 3):
        red, green, blue = pixels[offset:offset + 3]
        for channel, (r, g, b) in enumerate(matrix):
            output[offset + channel] = max(0, min(255, int((red * r + green * g) + blue * b)))
    return bytes(output)
