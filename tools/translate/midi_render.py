"""Render the legacy games' MIDI music to audio offline through a SoundFont 2 bank (the owner's decision 4).

    python tools/translate/midi_render.py SONG.mid BANK.sf2 OUT.mp3 [--once]

The bank and generator logic follow Tardy-Slip's Web Audio player (player/src/audio/sf2.js and web/synth.js), which
plays BREW and New Rules MIDI through TimGM6mb; here every voice is mixed into a numpy buffer instead of being scheduled.
`render` returns float stereo samples; `mp3` encodes them with ffmpeg (on PATH). A looping song's release tails are
wrapped to its start so the loop has no gap in the music itself. The lowpass filter needs scipy and is skipped without it.
Nothing this reads or writes belongs in the repo.
"""
from dataclasses import dataclass
import argparse
from pathlib import Path
import shutil
import struct
import subprocess

import numpy as np

RATE = 44100
FLOOR = 1e-4
RELEASE_LIMIT = 3.0

G = dict(startOffset=0, endOffset=1, loopStartOffset=2, loopEndOffset=3, startCoarse=4, vibLfoToPitch=6, filterFc=8,
         filterQ=9, modEnvToFilterFc=11, endCoarse=12, pan=17, delayVibLfo=23, freqVibLfo=24, delayVol=33,
         attackVol=34, holdVol=35, decayVol=36, sustainVol=37, releaseVol=38, keynumToHold=39, keynumToDecay=40,
         instrument=41, keyRange=43, velRange=44, loopStartCoarse=45, keynum=46, attenuation=48, loopEndCoarse=50,
         coarseTune=51, fineTune=52, sampleId=53, sampleModes=54, scaleTuning=56, exclusiveClass=57, rootKey=58)
DEFAULTS = {G['filterFc']: 13500, G['delayVol']: -12000, G['attackVol']: -12000, G['holdVol']: -12000,
            G['decayVol']: -12000, G['releaseVol']: -12000, G['delayVibLfo']: -12000, G['scaleTuning']: 100,
            G['rootKey']: -1, G['keynum']: -1}
INSTRUMENT_ONLY = {0, 1, 2, 3, 4, 12, 45, 50, 46, 47, 54, 57, 58}


def timecents(tc):
    return 0.0 if tc <= -12000 else 2 ** (tc / 1200)


@dataclass
class Sample:
    start: int
    end: int
    loop_start: int
    loop_end: int
    rate: int
    root: int
    correction: int


class SoundFont:
    def __init__(self, data: bytes):
        if data[:4] != b'RIFF' or data[8:12] != b'sfbk':
            raise ValueError('not a SoundFont 2 bank')
        chunks = {}

        def walk(p, end):
            while p + 8 <= end:
                tag, size = data[p:p + 4], struct.unpack_from('<I', data, p + 4)[0]
                if tag == b'LIST':
                    walk(p + 12, min(end, p + 8 + size))
                else:
                    chunks.setdefault(tag.decode('latin-1'), (p + 8, size))
                p += 8 + size + (size & 1)
        walk(12, min(len(data), 8 + struct.unpack_from('<I', data, 4)[0]))
        at, size = chunks['smpl']
        self.pcm = np.frombuffer(data, '<i2', size // 2, at).astype(np.float32) / 32768

        def records(tag, width):
            at, size = chunks[tag]
            return [data[p:p + width] for p in range(at, at + size - width + 1, width)]
        self.samples = [Sample(*struct.unpack_from('<5I', r, 20), r[40], struct.unpack_from('<b', r, 41)[0])
                        for r in records('shdr', 46)[:-1]]
        gens = lambda tag: [struct.unpack('<Hh', r) + (struct.unpack_from('<H', r, 2)[0],) for r in records(tag, 4)]
        bags = lambda tag: [struct.unpack_from('<H', r)[0] for r in records(tag, 4)]

        def zones(first, last, bag, gen, target_op):
            out, glob = [], None
            for b in range(first, last):
                zone = dict(gens={}, keys=(0, 127), vels=(0, 127), target=-1)
                for op, amount, raw in gen[bag[b]:bag[b + 1]]:
                    if op == G['keyRange']:
                        zone['keys'] = (raw & 0xff, raw >> 8)
                    elif op == G['velRange']:
                        zone['vels'] = (raw & 0xff, raw >> 8)
                    elif op == target_op:
                        zone['target'] = raw
                    else:
                        zone['gens'][op] = amount
                if zone['target'] >= 0:
                    out.append(zone)
                elif b == first:
                    glob = zone
            return out, glob
        ibag, igen = bags('ibag'), gens('igen')
        inst = records('inst', 22)
        self.instruments = [zones(struct.unpack_from('<H', inst[i], 20)[0], struct.unpack_from('<H', inst[i + 1], 20)[0],
                                  ibag, igen, G['sampleId']) for i in range(len(inst) - 1)]
        pbag, pgen = bags('pbag'), gens('pgen')
        phdr = records('phdr', 38)
        self.presets = {}
        for i in range(len(phdr) - 1):
            program, bank, first = struct.unpack_from('<3H', phdr[i], 20)
            last = struct.unpack_from('<H', phdr[i + 1], 24)[0]
            self.presets.setdefault((bank, program), zones(first, last, pbag, pgen, G['instrument']))

    def find(self, bank, program):
        return (self.presets.get((bank, program))
                or (self.presets.get((128, 0)) if bank == 128 else self.presets.get((0, program))))

    def voices(self, bank, program, key, velocity):
        preset = self.find(bank, program)
        if not preset:
            return []
        inside = lambda r, v: r[0] <= v <= r[1]
        pzones, pglobal = preset
        out = []
        for pz in pzones:
            if not (inside(pz['keys'], key) and inside(pz['vels'], velocity)) or pz['target'] >= len(self.instruments):
                continue
            izones, iglobal = self.instruments[pz['target']]
            for iz in izones:
                if not (inside(iz['keys'], key) and inside(iz['vels'], velocity)) or iz['target'] >= len(self.samples):
                    continue
                g = dict(DEFAULTS)
                g.update((iglobal or {}).get('gens', {}))
                g.update(iz['gens'])
                for zone in (pglobal, pz):
                    for op, v in (zone or {}).get('gens', {}).items():
                        if op not in INSTRUMENT_ONLY:
                            g[op] = g.get(op, 0) + v
                out.append(self.voice(g, self.samples[iz['target']], key))
        return out

    def voice(self, g, sample, key):
        v = lambda name: g.get(G[name], 0)
        root = v('rootKey') if v('rootKey') >= 0 else sample.root
        k = v('keynum') if v('keynum') >= 0 else key
        cents = (k - root) * v('scaleTuning') + v('coarseTune') * 100 + v('fineTune') + sample.correction
        fc = v('filterFc')
        return dict(
            sample=sample, pitch=2 ** (cents / 1200),
            start=v('startOffset') + v('startCoarse') * 32768,
            end=sample.end - sample.start + v('endOffset') + v('endCoarse') * 32768,
            loop_start=sample.loop_start - sample.start + v('loopStartOffset') + v('loopStartCoarse') * 32768,
            loop_end=sample.loop_end - sample.start + v('loopEndOffset') + v('loopEndCoarse') * 32768,
            loop=v('sampleModes') & 3 in (1, 3),
            attenuation=10 ** (-0.4 * max(0, v('attenuation')) / 200),
            pan=max(-1.0, min(1.0, v('pan') / 500)),
            filter_hz=8.176 * 2 ** (fc / 1200) if fc < 13500 else None, filter_q=v('filterQ') / 10,
            delay=timecents(v('delayVol')), attack=timecents(v('attackVol')),
            hold=timecents(v('holdVol') + v('keynumToHold') * (60 - k)),
            decay=timecents(v('decayVol') + v('keynumToDecay') * (60 - k)),
            sustain=10 ** (-max(0, min(1440, v('sustainVol'))) / 200), release=timecents(v('releaseVol')),
            vibrato=(timecents(v('delayVibLfo')), 8.176 * 2 ** (v('freqVibLfo') / 1200), v('vibLfoToPitch')),
            exclusive=v('exclusiveClass'))


@dataclass
class Song:
    notes: list          # (time, duration, channel, key, velocity)
    controls: list       # (time, channel, kind, value)
    duration: float


def parse_midi(data: bytes) -> Song:
    if data[:4] != b'MThd':
        raise ValueError('not a Standard MIDI file')
    header, tracks, division = struct.unpack_from('>I', data, 4)[0], *struct.unpack_from('>Hh', data, 10)
    tempos, notes, controls, order, last = [], [], [], 0, 0
    p = 8 + header
    for _ in range(tracks):
        if data[p:p + 4] != b'MTrk':
            break
        end = min(len(data), p + 8 + struct.unpack_from('>I', data, p + 4)[0])
        p += 8
        tick, running, rpn = 0, 0, {}

        def vlq():
            nonlocal p
            value = 0
            while True:
                c = data[p]; p += 1
                value = value << 7 | c & 0x7f
                if not c & 0x80 or p >= end:
                    return value
        while p < end:
            tick += vlq()
            status = data[p]
            if status < 0x80:
                status = running
            else:
                p += 1
                if status < 0xf0:
                    running = status
            if status == 0xff:
                kind = data[p]; p += 1
                size = vlq()
                if kind == 0x51 and size == 3:
                    tempos.append((tick, int.from_bytes(data[p:p + 3], 'big')))
                p += size
                if kind == 0x2f:
                    break
                continue
            if status in (0xf0, 0xf7):
                p += vlq()
                continue
            kind, channel = status & 0xf0, status & 0x0f
            a, b = data[p], data[p + 1] if p + 1 < len(data) else 0

            def control(name, value):
                nonlocal order
                controls.append((tick, order, channel, name, value)); order += 1
            if kind in (0x80, 0x90):
                notes.append((tick, order, kind == 0x90 and b > 0, channel, a, b)); order += 1
                p += 2
            elif kind == 0xa0:
                p += 2
            elif kind == 0xb0:
                p += 2
                if a in (7, 10, 11):
                    control({7: 'volume', 10: 'pan', 11: 'expression'}[a], b)
                elif a == 101:
                    rpn[channel] = (b & 0x7f) << 7 | rpn.get(channel, 0x3fff) & 0x7f
                elif a == 100:
                    rpn[channel] = rpn.get(channel, 0x3fff) & ~0x7f | b & 0x7f
                elif a == 6 and rpn.get(channel) == 0:
                    control('bendRange', b)
            elif kind == 0xc0:
                control('program', a)
                p += 1
            elif kind == 0xd0:
                p += 1
            elif kind == 0xe0:
                control('bend', ((b << 7 | a) - 8192) / 8192)
                p += 2
            else:
                p = end
        last = max(last, tick)
        p = end
    seconds = timeline(division, tempos)
    notes.sort(key=lambda n: (n[0], n[1]))
    controls.sort(key=lambda c: (c[0], c[1]))
    out, open_notes = [], {}
    for tick, _, on, channel, key, velocity in notes:
        if on:
            open_notes.setdefault((channel, key), []).append((tick, velocity))
        elif open_notes.get((channel, key)):
            start, velocity = open_notes[channel, key].pop(0)
            out.append((seconds(start), seconds(tick) - seconds(start), channel, key, velocity))
    for (channel, key), starts in open_notes.items():
        out += [(seconds(t), seconds(last) - seconds(t), channel, key, v) for t, v in starts]
    out.sort(key=lambda n: (n[0], n[2], n[3]))
    return Song(out, [(seconds(t), ch, kind, value) for t, _, ch, kind, value in controls], seconds(last))


def timeline(division, tempos):
    if division < 0:
        fps, per_frame = -(division >> 8), division & 0xff
        return lambda tick: tick / (fps * per_frame)
    ppq = division or 480
    starts = [(0, 0.0, 500_000)]
    for tick, us in sorted(tempos):
        t0, s0, u0 = starts[-1]
        if tick == t0:
            starts[-1] = (t0, s0, us)
        else:
            starts.append((tick, s0 + (tick - t0) * u0 / ppq / 1e6, us))

    def seconds(tick):
        base = starts[0]
        for start in starts:
            if start[0] > tick:
                break
            base = start
        return base[1] + (tick - base[0]) * base[2] / ppq / 1e6
    return seconds


def track(controls, channel, kind, initial):
    """[(time, value)] for one channel's controller, starting with the initial value at time 0."""
    return [(0.0, initial)] + [(t, v) for t, ch, k, v in controls if ch == channel and k == kind]


def value_at(points, time):
    value = points[0][1]
    for t, v in points:
        if t > time:
            break
        value = v
    return value


def envelope(n, voice, release_index):
    """Per-sample amplitude: delay, linear attack, hold, exponential decay to sustain, exponential release."""
    t = np.arange(n) / RATE
    a0 = voice['delay']; a1 = a0 + voice['attack']; h1 = a1 + voice['hold']; d1 = h1 + voice['decay']
    sustain = max(voice['sustain'], FLOOR)
    level = np.full(n, sustain, np.float32)
    level[t < d1] = sustain ** ((t[t < d1] - h1) / max(voice['decay'], 1e-6))
    level[t < h1] = 1
    attack = t < a1
    level[attack] = (t[attack] - a0) / max(voice['attack'], 1e-6)
    level[t <= a0] = 0
    if release_index < n:
        from_level = max(float(level[release_index]), FLOOR)
        length = max(min(voice['release'], RELEASE_LIMIT), 0.005)
        k = (t[release_index:] - t[release_index]) / length
        level[release_index:] = np.where(k < 1, from_level * (FLOOR / from_level) ** k, 0)
    return np.clip(level, 0, 1)


def render(song: Song, bank: SoundFont, loop=False):
    """Stereo float samples (n, 2). Looping songs are exactly `duration` long, tails wrapped to the start."""
    length = int(round(song.duration * RATE))
    planned = []
    channels = {}
    for time, duration, channel, key, velocity in song.notes:
        if channel not in channels:
            c = song.controls
            channels[channel] = {name: track(c, channel, name, initial) for name, initial in (
                ('program', 0), ('volume', 100), ('expression', 127), ('pan', 64), ('bend', 0), ('bendRange', 2))}
        drums = channel == 9
        program = 0 if drums else value_at(channels[channel]['program'], time)
        for voice in bank.voices(128 if drums else 0, program, key, velocity):
            planned.append([voice, time, duration, channel, velocity])
    cut = {}
    for item in reversed(planned):
        voice, time, duration, channel, _ = item
        if voice['exclusive']:
            later = cut.get((channel, voice['exclusive']))
            if later is not None and later < time + duration:
                item[2] = later - time
            cut[channel, voice['exclusive']] = time
    total = length + int((RELEASE_LIMIT + 1) * RATE) + max(
        [int((t + d) * RATE) for _, t, d, _, _ in planned] or [0])
    mix = np.zeros((total, 2), np.float32)
    try:
        from scipy.signal import lfilter
    except ImportError:
        lfilter = None
    for voice, time, duration, channel, velocity in planned:
        c = channels[channel]
        level = ((velocity / 127) ** 2 * voice['attenuation'] * (value_at(c['volume'], time) / 127) ** 2
                 * (value_at(c['expression'], time) / 127) ** 2)
        if level <= 0:
            continue
        start = int(round(time * RATE))
        release = int(round(max(duration, 0) * RATE))
        n = release + int(min(voice['release'], RELEASE_LIMIT) * RATE) + int(0.01 * RATE)
        sample = voice['sample']
        step = voice['pitch'] * sample.rate / RATE
        t = (start + np.arange(n)) / RATE
        bend_range = value_at(c['bendRange'], time)
        bends = [(b_t, b) for b_t, b in c['bend'] if b_t <= time + n / RATE]
        bend = np.full(n, value_at(bends, time), np.float32)
        for b_t, b in bends:
            if b_t > time:
                bend[t >= b_t] = b
        inc = step * 2 ** (bend * bend_range / 12)
        vib_delay, vib_hz, vib_cents = voice['vibrato']
        if vib_cents:
            local = t - time - vib_delay
            inc = inc * 2 ** (np.where(local > 0, np.sin(2 * np.pi * vib_hz * local), 0) * vib_cents / 1200)
        pos = max(0, voice['start']) + np.concatenate(([0.0], np.cumsum(inc[:-1])))
        end = min(voice['end'], sample.end - sample.start)
        if voice['loop'] and voice['loop_end'] > voice['loop_start'] and voice['loop_end'] <= end:
            span = voice['loop_end'] - voice['loop_start']
            beyond = pos >= voice['loop_end']
            pos[beyond] = voice['loop_start'] + (pos[beyond] - voice['loop_start']) % span
        else:
            valid = pos < end - 1
            if not valid.all():
                n = int(np.argmin(valid))
                pos = pos[:n]
        if n <= 0:
            continue
        i = pos.astype(np.int64)
        frac = (pos - i).astype(np.float32)
        base = sample.start
        wave = bank.pcm[base + i] * (1 - frac) + bank.pcm[np.minimum(base + i + 1, sample.end - 1)] * frac
        if voice['filter_hz'] and lfilter is not None:
            wave = lfilter(*lowpass(voice['filter_hz'], voice['filter_q']), wave).astype(np.float32)
        wave = wave * envelope(n, voice, release)[:n] * level
        pan = max(-1.0, min(1.0, voice['pan'] + (value_at(c['pan'], time) - 64) / 64))
        angle = (pan + 1) * np.pi / 4
        mix[start:start + n, 0] += wave * np.cos(angle)
        mix[start:start + n, 1] += wave * np.sin(angle)
    if loop and length:
        out = mix[:length].copy()
        for k in range(length, total, length):
            piece = mix[k:k + length]
            out[:len(piece)] += piece
    else:
        audible = np.nonzero(np.abs(mix).max(axis=1) > 1e-4)[0]
        out = mix[:max(length, int(audible[-1]) + 1 if len(audible) else 0)]
    peak = float(np.abs(out).max()) if len(out) else 0
    return out * (0.89 / peak) if peak > 0 else out


def lowpass(hz, q_db):
    """RBJ biquad lowpass coefficients; the SF2 filter Q is in centibels of resonance."""
    hz = min(max(hz, 20), RATE * 0.45)
    q = max(10 ** (q_db / 20), 0.5) if q_db > 0 else 0.7071
    w = 2 * np.pi * hz / RATE
    alpha = np.sin(w) / (2 * q)
    cos = np.cos(w)
    b = np.array([(1 - cos) / 2, 1 - cos, (1 - cos) / 2])
    a = np.array([1 + alpha, -2 * cos, 1 - alpha])
    return b / a[0], a / a[0]


def mp3(samples, bitrate='128k'):
    """MP3 bytes for stereo float samples, through ffmpeg on PATH."""
    ffmpeg = shutil.which('ffmpeg')
    if ffmpeg is None:
        raise RuntimeError('ffmpeg is needed on PATH to encode MP3')
    pcm = (np.clip(samples, -1, 1) * 32767).astype('<i2').tobytes()
    result = subprocess.run([ffmpeg, '-loglevel', 'error', '-f', 's16le', '-ar', str(RATE), '-ac', '2', '-i', 'pipe:0',
                             '-c:a', 'libmp3lame', '-b:a', bitrate, '-f', 'mp3', 'pipe:1'],
                            input=pcm, capture_output=True, check=True)
    return result.stdout


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('song', type=Path)
    parser.add_argument('bank', type=Path)
    parser.add_argument('out', type=Path)
    parser.add_argument('--once', action='store_true', help="keep the release tail instead of wrapping it for a loop")
    args = parser.parse_args()
    audio = render(parse_midi(args.song.read_bytes()), SoundFont(args.bank.read_bytes()), loop=not args.once)
    args.out.write_bytes(mp3(audio))
