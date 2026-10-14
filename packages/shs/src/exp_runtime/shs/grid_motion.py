"""Native grid camera and solid tile geometry, independent of the drawing host."""
import math


def project(width, height, x, y, z=0.):
    # Android 000cc398/000c7ef8 and iOS setup3DTransform 00095338.
    depth = -3800 if height == 5 else -3400 if (width, height) in ((5, 3), (4, 4), (5, 4)) else -3000
    x -= (width * 450 + (width - 1) * 72) / 2
    y = (height * 450 + (height - 1) * 72) / 2 + 480 - y
    camera_z = depth - y * .5 + z * math.cos(math.pi / 6)
    return (160 + 400 * x / -camera_z,
            240 - 400 * (y * math.cos(math.pi / 6) + z * .5 - 300) / -camera_z,
            camera_z)


def cube_faces(width, height, column, row, angle=0., scale=1.):
    """Visible faces of the native 450 x 450 x 100 cube, back to front.

    Each result is (depth, face, quad), with texture corners TL/TR/BR/BL.
    The original fifth-row bottom cap extends ten units to avoid a seam.
    """
    bottom = 60 if height == 5 and row == 4 else 50
    faces = (
        ('front', ((-225, -225, 50), (225, -225, 50), (225, 225, 50), (-225, 225, 50))),
        ('back', ((225, -225, -50), (-225, -225, -50), (-225, 225, -50), (225, 225, -50))),
        ('side', ((-225, -225, -50), (-225, -225, 50), (-225, 225, 50), (-225, 225, -50))),
        ('side', ((225, -225, 50), (225, -225, -50), (225, 225, -50), (225, 225, 50))),
        ('side', ((-225, -225, -50), (225, -225, -50), (225, -225, 50), (-225, -225, 50))),
        ('side', ((-225, 225, bottom), (225, 225, bottom), (225, 225, -50), (-225, 225, -50))),
    )
    cosine, sine = math.cos(angle), math.sin(angle)
    visible = []
    for face, vertices in faces:
        points = tuple(project(width, height,
                               column * 522 + 225 + scale * (x * cosine + z * sine),
                               row * 522 + 225 + scale * y,
                               -50 + scale * (-x * sine + z * cosine)) for x, y, z in vertices)
        a, b, c, _ = points
        if (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) > .001:
            visible.append((sum(p[2] for p in points) / 4, face, tuple(p[:2] for p in points)))
    return sorted(visible)
