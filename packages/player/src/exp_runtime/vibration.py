from array import array
from io import BytesIO
import math
import sys
import wave

RATE = 44_100
MOTOR_HZ = 175.0
AMPLITUDE = 0.4
RAMP = 0.012
BUZZ_MS = 400


def buzz_wav(duration_ms=BUZZ_MS):
    running = RATE * duration_ms // 1000
    ramp = RAMP * RATE
    samples = array('h')
    for i in range(running + math.ceil(ramp) + 1):
        level = min(1.0, i / ramp, max(0.0, (running - i) / ramp + 1))
        angle = 2 * math.pi * MOTOR_HZ * i / RATE
        buzz = 0.8 * math.tanh(4 * math.sin(angle)) + 0.2 * math.sin(2 * angle)
        samples.append(round(32767 * AMPLITUDE * level * buzz))
    if sys.byteorder == 'big':
        samples.byteswap()
    out = BytesIO()
    with wave.open(out, 'wb') as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(RATE)
        file.writeframes(samples.tobytes())
    return out.getvalue()
