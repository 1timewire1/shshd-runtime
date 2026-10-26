// Render one MIDI song through Java's built-in synthesizer (Gervill, with its own generated bank, reverb and chorus), as
// FreeJ2ME's "Default" soundfont plays the Java builds' music. midi_render.render_java runs it:
//
//   java --add-exports java.desktop/com.sun.media.sound=ALL-UNNAMED JavaMidi.java SECONDS < SONG.mid > PCM
//
// stdin: the MIDI file; stdout: 44.1 kHz stereo signed 16-bit little-endian PCM, the song plus SECONDS of tail.
import com.sun.media.sound.AudioSynthesizer;

import javax.sound.midi.*;
import javax.sound.sampled.*;
import java.io.*;
import java.util.*;

public class JavaMidi {
    public static void main(String[] args) throws Exception {
        Sequence sequence = MidiSystem.getSequence(new ByteArrayInputStream(System.in.readAllBytes()));
        AudioSynthesizer synth = (AudioSynthesizer) MidiSystem.getSynthesizer();
        AudioFormat format = new AudioFormat(44100f, 16, 2, true, false);
        AudioInputStream stream = synth.openStream(format, null);
        Receiver receiver = synth.getReceiver();

        List<MidiEvent> events = new ArrayList<>();
        for (Track track : sequence.getTracks())
            for (int i = 0; i < track.size(); i++) events.add(track.get(i));
        events.sort(Comparator.comparingLong(MidiEvent::getTick));      // stable: each track keeps its order

        // Ticks to microseconds through the tempo map; the synthesizer plays each message at its timestamp.
        double resolution = sequence.getResolution(), tempo = 500000, micros = 0;
        long lastTick = 0;
        for (MidiEvent event : events) {
            micros += (event.getTick() - lastTick) * tempo / resolution;
            lastTick = event.getTick();
            MidiMessage message = event.getMessage();
            if (message instanceof MetaMessage meta) {
                if (meta.getType() == 0x51) {
                    byte[] d = meta.getData();
                    tempo = ((d[0] & 0xff) << 16) | ((d[1] & 0xff) << 8) | (d[2] & 0xff);
                }
                continue;
            }
            receiver.send(message, (long) micros);
        }
        long frames = (long) ((micros / 1e6 + Double.parseDouble(args[0])) * format.getFrameRate());
        OutputStream out = new BufferedOutputStream(System.out);
        byte[] buffer = new byte[4096 * format.getFrameSize()];
        long left = frames * format.getFrameSize();
        while (left > 0) {
            int n = stream.read(buffer, 0, (int) Math.min(buffer.length, left));
            if (n <= 0) break;
            out.write(buffer, 0, n);
            left -= n;
        }
        out.flush();
        synth.close();
    }
}
