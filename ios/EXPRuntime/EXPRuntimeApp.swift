import SwiftUI
import UniformTypeIdentifiers
import AVFAudio
import AudioToolbox

// The orientations the app allows. A SwiftUI app's own view controller is not the window's root, so its
// supportedInterfaceOrientations is never asked: the app delegate's answer is (RuntimeController.requestLandscape).
final class AppDelegate: NSObject, UIApplicationDelegate {
    static var orientations: UIInterfaceOrientationMask = .all
    func application(_ application: UIApplication,
                     supportedInterfaceOrientationsFor window: UIWindow?) -> UIInterfaceOrientationMask {
        AppDelegate.orientations
    }
}

@main
struct EXPRuntimeApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    var body: some Scene {
        WindowGroup { RuntimeView().background(Color.black.ignoresSafeArea()).ignoresSafeArea(.keyboard) }
    }
}

struct RuntimeView: UIViewControllerRepresentable {
    func makeUIViewController(context: Context) -> RuntimeController { RuntimeController() }
    func updateUIViewController(_ controller: RuntimeController, context: Context) {}
}

final class GameCanvasView: UIView, UIKeyInput {
    // The frame is a layer's contents, composited and scaled by Core Animation, not redrawn by the CPU in `draw(_:)`
    // (a 1536 x 2048 copy each frame). A frame that did not change is the same image and changes nothing.
    var image: CGImage? {
        didSet {
            guard image !== oldValue else { return }
            frameLayer.contents = image
            frameLayer.frame = viewport
        }
    }
    private let frameLayer: CALayer = {
        let layer = CALayer()
        layer.actions = ["contents": NSNull(), "bounds": NSNull(), "position": NSNull(), "frame": NSNull()]
        layer.magnificationFilter = .linear
        layer.minificationFilter = .linear
        return layer
    }()
    override init(frame: CGRect) {
        super.init(frame: frame)
        setUp()
    }
    required init?(coder: NSCoder) {
        super.init(coder: coder)
        setUp()
    }
    // HD's story tree is a UIScrollView, zoomed with UIKit's own pinch: the same recognizer here, its steps sent to
    // the shared app (ios.Host pinch: SidePanels.zoom_tree about the fingers' midpoint, which carries the tree along).
    // Once it recognizes, UIKit cancels the first finger's touch (`touchesCancelled`), so that drag ends.
    private func setUp() {
        layer.addSublayer(frameLayer)
        addGestureRecognizer(UIPinchGestureRecognizer(target: self, action: #selector(pinched(_:))))
    }
    @objc private func pinched(_ pinch: UIPinchGestureRecognizer) {
        let phase: String
        switch pinch.state {
        case .began: phase = "began"
        case .changed: phase = "changed"
        case .ended, .cancelled, .failed: phase = "ended"
        default: return
        }
        let p = point(pinch.location(in: self))
        send?(["kind": "pinch", "phase": phase, "scale": Double(pinch.scale), "point": [p.x, p.y]])
        pinch.scale = 1                 // each step's own factor, not the gesture's running one
    }
    override func layoutSubviews() {
        super.layoutSubviews()
        frameLayer.frame = viewport
    }
    // A view that does not draw itself keeps a content scale of 1, which made `pixelSize` the view's points: the app
    // drew a 768 x 992 frame for the iPad mini's 1536 x 2048 screen, and everything looked soft. The screen's own
    // scale makes the frame one pixel per screen pixel, as SHS HD drew.
    override func didMoveToWindow() {
        super.didMoveToWindow()
        if let scale = window?.windowScene?.screen.scale { contentScaleFactor = scale }
    }
    var send: (([String: Any]) -> Void)?
    var scrollable = false
    var generation = 0
    private var touchGeneration = 0

    // The options' switches and volume sliders are UIKit's own, as SHS HD's were (subviews of its menus): each frame
    // names the controls the menus show, where (a switch's `right` edge, a slider's `left` and `right` track ends, and
    // their `middle`, in the frame's pixels), how big (`scale`: frame pixels per menu point, the card zooming open)
    // and how faded. Those not named are hidden. A change goes back as a `switch` or `slider` event: the app sets
    // that option as a tap or drag on the drawn one did, and the next frame confirms it or puts the control back.
    private var switches: [String: UISwitch] = [:]
    private var sliders: [String: UISlider] = [:]
    func placeControls(_ placed: [[String: Any]]) {
        let v = viewport, frame = frameSize
        let k = v.width / max(1, frame.width)        // view points per frame pixel
        var shown = Set<String>()
        func number(_ item: [String: Any], _ key: String) -> CGFloat? {
            (item[key] as? NSNumber).map { CGFloat($0.doubleValue) }
        }
        for item in placed {
            guard let kind = item["kind"] as? String, let key = item["key"] as? String,
                  let right = number(item, "right"), let middle = number(item, "middle"),
                  let scale = number(item, "scale") else { continue }
            let s = max(0.001, scale * k)
            let control: UIControl
            let size: CGSize
            if kind == "slider" {
                guard let left = number(item, "left"), let value = number(item, "value") else { continue }
                let slider = sliders[key] ?? makeSlider(key)
                control = slider
                // As wide as the drawn track once scaled (UIKit's thumb then travels the track's ends, as HD's).
                slider.transform = .identity
                size = CGSize(width: (right - left) * k / s, height: slider.intrinsicContentSize.height)
                if !slider.isTracking && abs(CGFloat(slider.value) - value) > 0.001 { slider.value = Float(value) }
            } else if kind == "switch" {
                guard let on = item["on"] as? Bool else { continue }
                let toggle = switches[key] ?? makeSwitch(key)
                control = toggle
                toggle.transform = .identity
                size = toggle.intrinsicContentSize
                if toggle.isOn != on && !toggle.isTracking { toggle.setOn(on, animated: true) }
            } else { continue }
            shown.insert(kind + ":" + key)
            control.transform = .identity
            control.bounds = CGRect(origin: .zero, size: size)
            control.transform = CGAffineTransform(scaleX: s, y: s)
            control.center = CGPoint(x: v.minX + right * k - size.width * s / 2, y: v.minY + middle * k)
            control.alpha = number(item, "alpha") ?? 1
            control.isHidden = false
        }
        for (key, control) in switches where !shown.contains("switch:" + key) { control.isHidden = true }
        for (key, control) in sliders where !shown.contains("slider:" + key) { control.isHidden = true }
    }
    private func makeSwitch(_ key: String) -> UISwitch {
        let control = UISwitch()
        control.accessibilityIdentifier = key
        control.isHidden = true
        control.addTarget(self, action: #selector(switchFlipped(_:)), for: .valueChanged)
        addSubview(control)
        switches[key] = control
        return control
    }
    private func makeSlider(_ key: String) -> UISlider {
        let control = UISlider()
        control.accessibilityIdentifier = key
        control.minimumValue = 0
        control.maximumValue = 1
        control.isContinuous = true         // the volume follows the thumb, its preview sound with it
        control.isHidden = true
        control.addTarget(self, action: #selector(sliderMoved(_:)), for: .valueChanged)
        addSubview(control)
        sliders[key] = control
        return control
    }
    @objc private func switchFlipped(_ control: UISwitch) {
        guard let key = control.accessibilityIdentifier else { return }
        send?(["kind": "switch", "key": key, "on": control.isOn])
    }
    @objc private func sliderMoved(_ control: UISlider) {
        guard let key = control.accessibilityIdentifier else { return }
        send?(["kind": "slider", "key": key, "value": Double(control.value)])
    }
    private var start: CGPoint?
    private var previous: CGPoint?
    private var dragging = false
    private var tracked: UITouch?       // the one finger the app follows (a second one is the pinch's)
    // SHS HD's name entry keyboard (`SHSUITextEntry::initTextEntry`'s UITextView): the name layout (keyboard type 6)
    // and a Done key (return type 9) that stays grey while the name is empty (`enablesReturnKeyAutomatically`).
    // `typed` is the name as far as this view knows: each frame brings the app's (`syncText`), and keys typed since
    // the frame was asked for are applied to it here at once, so Done follows each key.
    private(set) var typed = ""
    private(set) var edits = 0
    var hasText: Bool { !typed.isEmpty }
    var keyboardType: UIKeyboardType = .namePhonePad
    var enablesReturnKeyAutomatically = true
    func syncText(_ text: String?, editsSent: Int) {
        if edits == editsSent { typed = text ?? "" }
    }
    override var canBecomeFirstResponder: Bool { true }
    var autocorrectionType: UITextAutocorrectionType = .no
    var autocapitalizationType: UITextAutocapitalizationType = .none
    var returnKeyType: UIReturnKeyType = .done

    // The app's window in pixels: the frame Python draws. Normally the view's own pixel size (`pixelSize`), so the
    // frame fills the view one pixel per pixel; the simulator check keeps the app's default window.
    private var frameSize: CGSize { image.map { CGSize(width: $0.width, height: $0.height) } ?? CGSize(width: 540, height: 720) }

    var pixelSize: CGSize {
        CGSize(width: (bounds.width * contentScaleFactor).rounded(), height: (bounds.height * contentScaleFactor).rounded())
    }

    private var viewport: CGRect {
        let frame = frameSize
        let scale = min(bounds.width / frame.width, bounds.height / frame.height)
        let size = CGSize(width: frame.width * scale, height: frame.height * scale)
        return CGRect(x: (bounds.width - size.width) / 2, y: (bounds.height - size.height) / 2,
                      width: size.width, height: size.height)
    }

    // Gestures are judged in the phone layout's 480 x 720 units, whatever the frame's size: the drag threshold and the
    // scroll step feel the same on every screen.
    private func units(_ distance: CGFloat) -> CGFloat { distance * 720 / max(1, viewport.height) }

    // A touch in the frame's pixels (the app's window coordinates; the shared app maps them to its own canvases).
    private func point(_ touch: UITouch) -> CGPoint { point(touch.location(in: self)) }
    private func point(_ p: CGPoint) -> CGPoint {
        let v = viewport, frame = frameSize
        return CGPoint(x: (p.x - v.minX) * frame.width / v.width, y: (p.y - v.minY) * frame.height / v.height)
    }

    // `time`: when UIKit saw the touch (ms of system uptime, CACurrentMediaTime's clock), not when the frame read it:
    // a flick's speed (momentum.py) comes from these, as UIScrollView's does.
    private func pointer(_ kind: String, _ p: CGPoint, _ touch: UITouch) {
        send?(["kind": kind, "point": [p.x, p.y], "generation": touchGeneration, "time": touch.timestamp * 1000])
    }
    override func touchesBegan(_ touches: Set<UITouch>, with event: UIEvent?) {
        if let old = tracked, old.phase == .ended || old.phase == .cancelled { tracked = nil }   // ended unseen
        guard tracked == nil, let touch = touches.first else { return }
        tracked = touch
        let p = point(touch)
        touchGeneration = generation
        start = p; previous = p; dragging = false
        if !scrollable { pointer("down", p, touch) }
    }
    override func touchesMoved(_ touches: Set<UITouch>, with event: UIEvent?) {
        guard let touch = tracked, touches.contains(touch), let first = start, let last = previous else { return }
        let p = point(touch)
        if scrollable {
            let scale = frameSize.height / max(1, viewport.height)      // frame pixels per view point
            if units(abs(p.y - first.y) / scale) > 8 { dragging = true }
            if dragging {
                send?(["kind": "scroll", "delta": units((p.y - last.y) / scale) / 52.5, "generation": touchGeneration])
            }
        } else { pointer("move", p, touch) }
        previous = p
    }
    override func touchesEnded(_ touches: Set<UITouch>, with event: UIEvent?) {
        guard let touch = tracked, touches.contains(touch), let first = start else { return }
        tracked = nil
        let p = point(touch)
        if scrollable && !dragging { pointer("down", first, touch); pointer("up", p, touch) }
        else if !scrollable { pointer("up", p, touch) }
        start = nil; previous = nil
    }
    override func touchesCancelled(_ touches: Set<UITouch>, with event: UIEvent?) {
        guard let touch = tracked, touches.contains(touch) else { return }
        send?(["kind": "cancel"]); start = nil; previous = nil; tracked = nil
    }
    func insertText(_ text: String) {
        if text == "\n" { send?(["kind": "key", "key": "return", "generation": generation]) }
        else {
            typed += text; edits += 1
            send?(["kind": "text", "text": text, "generation": generation])
        }
    }
    func deleteBackward() {
        if !typed.isEmpty { typed.removeLast() }
        edits += 1
        send?(["kind": "key", "key": "backspace", "generation": generation])
    }
}

final class NativeAudio: NSObject, AVAudioPlayerDelegate {
    private var tracks: [String: AVAudioPlayer] = [:]
    private var pausedTracks: Set<String> = []
    private var sounds: [AVAudioPlayer] = []
    // pygame's music queue: a track's next cue (an intro's loop), started when the playing one ends.
    private var queued: [String: (player: AVAudioPlayer, loops: Int)] = [:]
    // Tracks whose queued cue is already scheduled on the audio clock for the moment the playing one ends
    // (`play(atTime:)`). Started from `audioPlayerDidFinishPlaying` instead, Day of Diss's loop came about half a
    // second after its intro (the files themselves meet with no silence): the callback arrives late, and a player
    // started then still has to spin up.
    private var scheduled: Set<String> = []
    private func scheduleQueued(_ track: String) {
        unscheduleQueued(track)
        guard let current = tracks[track], current.isPlaying, current.numberOfLoops == 0,
              let next = queued[track] else { return }
        next.player.numberOfLoops = next.loops
        next.player.volume = current.volume
        let remaining = max(0, current.duration - current.currentTime)
        if next.player.play(atTime: current.deviceCurrentTime + remaining) { scheduled.insert(track) }
    }
    private func unscheduleQueued(_ track: String) {
        guard scheduled.remove(track) != nil, let next = queued[track]?.player else { return }
        next.stop()
        next.currentTime = 0
        next.prepareToPlay()
    }
    func perform(_ commands: [[String: Any]]) throws {
        for command in commands {
            guard let kind = command["kind"] as? String else { throw CanvasError(message: "Missing audio command") }
            let track = command["track"] as? String ?? (kind.hasPrefix("menu_") ? "menu" : "music")
            let action = kind.hasPrefix("menu_") ? "music_" + kind.dropFirst(5) : kind
            switch action {
            case "music_load", "music_queue", "sound":
                guard let encoded = command["data"] as? String, let data = Data(base64Encoded: encoded) else {
                    throw CanvasError(message: "Invalid audio data")
                }
                try AVAudioSession.sharedInstance().setCategory(.ambient, mode: .default)
                try AVAudioSession.sharedInstance().setActive(true)
                let player = try AVAudioPlayer(data: data)
                player.delegate = self
                guard player.prepareToPlay() else { throw CanvasError(message: "Could not prepare audio playback") }
                if action == "music_load" {
                    unscheduleQueued(track)
                    tracks[track] = player; pausedTracks.remove(track); queued.removeValue(forKey: track)
                } else if action == "music_queue" {
                    unscheduleQueued(track)
                    queued[track] = (player, (command["loops"] as? NSNumber)?.intValue ?? 0)
                    scheduleQueued(track)
                } else {
                    guard player.play() else { throw CanvasError(message: "Could not start sound playback") }
                    sounds.append(player)
                }
            case "music_play":
                guard let player = tracks[track] else { throw CanvasError(message: "Music has not been loaded") }
                player.numberOfLoops = (command["loops"] as? NSNumber)?.intValue ?? 0
                player.currentTime = (command["start"] as? NSNumber)?.doubleValue ?? 0
                guard player.play() else { throw CanvasError(message: "Could not start music playback") }
                pausedTracks.remove(track)
                scheduleQueued(track)
            case "music_pause":
                if let player = tracks[track], player.isPlaying {
                    unscheduleQueued(track)
                    player.pause()
                    pausedTracks.insert(track)
                }
            case "music_resume":
                if pausedTracks.remove(track) != nil, let player = tracks[track] {
                    guard player.play() else { throw CanvasError(message: "Could not resume music playback") }
                    scheduleQueued(track)
                }
            case "music_stop":
                unscheduleQueued(track)
                tracks[track]?.stop(); tracks.removeValue(forKey: track); pausedTracks.remove(track)
                queued.removeValue(forKey: track)
            case "music_volume":
                let volume = (command["volume"] as? NSNumber)?.floatValue ?? 1
                tracks[track]?.volume = volume
                queued[track]?.player.volume = volume
            case "music_loops":
                tracks[track]?.numberOfLoops = (command["loops"] as? NSNumber)?.intValue ?? 0
                scheduleQueued(track)
            case "sounds_stop": sounds.forEach { $0.stop() }; sounds.removeAll()
            default: throw CanvasError(message: "Unsupported audio command")
            }
        }
    }
    func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        sounds.removeAll { $0 === player }
        for (key, value) in tracks where value === player {
            // The intro has ended: its queued loop takes over the track, at the intro's volume. Scheduled, it is
            // already playing from the intro's last sample (scheduleQueued).
            guard let next = queued.removeValue(forKey: key) else { continue }
            let started = scheduled.remove(key) != nil && next.player.isPlaying
            tracks[key] = next.player
            if !started {
                next.player.numberOfLoops = next.loops
                next.player.volume = player.volume
                next.player.play()
            }
        }
        for (key, value) in tracks where key.hasPrefix("effect:") && value === player {
            tracks.removeValue(forKey: key)
            pausedTracks.remove(key)
        }
    }

    var playing: [String: Bool] {
        tracks.mapValues { $0.isPlaying }
    }

    var positions: [String: Int] {
        tracks.mapValues { max(0, Int($0.currentTime * 1000)) }
    }

    func verifyMenuPlaying() throws {
        guard tracks["menu"]?.isPlaying == true else { throw CanvasError(message: "Menu theme is not playing") }
    }

    func verifySoundPlaying() throws {
        guard sounds.contains(where: { $0.isPlaying }) else { throw CanvasError(message: "Click sound is not playing") }
    }

    func verifyEffectPlaying(_ track: String) throws {
        guard tracks[track]?.isPlaying == true else { throw CanvasError(message: "Script sound is not playing: \(track)") }
    }

    static func verify(_ encoded: String) throws {
        let audio = NativeAudio()
        defer { try? audio.perform([["kind": "music_stop"], ["kind": "menu_stop"]]) }
        try audio.perform([["kind": "music_load", "data": encoded], ["kind": "music_play", "start": 1.0, "loops": -1]])
        guard let story = audio.tracks["music"], story.isPlaying else { throw CanvasError(message: "Story audio did not start") }
        try audio.perform([["kind": "music_volume", "volume": 0.25]])
        guard story.volume == 0.25, audio.playing["music"] == true else {
            throw CanvasError(message: "Music fade changed the active stream or failed to set its volume")
        }
        try audio.perform([["kind": "music_volume", "volume": 1.0]])
        try audio.perform([["kind": "music_pause"]])
        guard audio.playing["music"] == false else { throw CanvasError(message: "Paused music reported itself playing") }
        let position = story.currentTime
        try audio.perform([["kind": "music_loops", "loops": 0]])
        guard audio.tracks["music"] === story, story.numberOfLoops == 0,
              story.currentTime == position, audio.positions["music"] == Int(position * 1000) else {
            throw CanvasError(message: "Changing repeat mode reset the music playhead")
        }
        try audio.perform([["kind": "music_loops", "loops": -1]])
        try audio.perform([["kind": "menu_load", "data": encoded], ["kind": "menu_play"]])
        try audio.verifyMenuPlaying()
        guard audio.tracks["music"] === story, !story.isPlaying, story.currentTime == position else {
            throw CanvasError(message: "Menu playback changed the paused story stream")
        }
        try audio.perform([["kind": "menu_pause"]])
        guard audio.tracks["menu"]?.isPlaying == false else { throw CanvasError(message: "Menu audio did not pause") }
        try audio.perform([["kind": "menu_resume"]])
        try audio.verifyMenuPlaying()
        try audio.perform([["kind": "menu_stop"], ["kind": "music_resume"]])
        // currentTime briefly includes output scheduling latency on resume.
        // Check the retained cue with tolerance, rather than exact clock equality.
        guard audio.tracks["menu"] == nil, audio.tracks["music"] === story,
              story.isPlaying, story.numberOfLoops == -1, abs(story.currentTime - position) < 0.5 else {
            throw CanvasError(message: "Story audio did not resume at its retained cue")
        }
        // Cross the actual end of the authored PCM in both modes. Merely
        // checking numberOfLoops would miss playback/transport regressions.
        for loops in [-1, 0] {
            try audio.perform([["kind": "music_play", "start": story.duration - 0.15, "loops": loops]])
            RunLoop.current.run(until: Date().addingTimeInterval(0.65))
            guard story.isPlaying == (loops == -1) else {
                throw CanvasError(message: "Music did not honor its repeat flag at the end of the track")
            }
        }
        story.stop() // A finished stream must not restart on a focus round trip.
        try audio.perform([["kind": "music_pause"], ["kind": "music_resume"]])
        guard !story.isPlaying else { throw CanvasError(message: "A stopped track restarted on resume") }
        try audio.perform([["kind": "music_load", "track": "effect:1", "data": encoded],
                           ["kind": "music_play", "track": "effect:1", "start": 0.75, "loops": 0],
                           ["kind": "music_pause", "track": "effect:1"]])
        guard let effect = audio.tracks["effect:1"], !effect.isPlaying,
              abs(effect.currentTime - 0.75) < 0.5, audio.tracks["music"] === story else {
            throw CanvasError(message: "Saved sound effect did not retain its independent playback position")
        }
        try audio.perform([["kind": "music_volume", "track": "effect:1", "volume": 0.5],
                           ["kind": "music_resume", "track": "effect:1"]])
        guard effect.isPlaying, effect.volume == 0.5 else {
            throw CanvasError(message: "Sound effect fade/resume failed")
        }
        try audio.perform([["kind": "music_stop", "track": "effect:1"]])
        guard audio.tracks["effect:1"] == nil else { throw CanvasError(message: "Stopped sound effect was retained") }
        // An intro runs into its queued loop when it ends (pygame's music.queue), which then repeats.
        try audio.perform([["kind": "music_play", "start": story.duration - 0.15, "loops": 0],
                           ["kind": "music_queue", "data": encoded, "loops": -1]])
        let handover = Date().addingTimeInterval(2)
        while audio.tracks["music"] === story && Date() < handover {
            RunLoop.current.run(until: Date().addingTimeInterval(0.05))
        }
        guard let loop = audio.tracks["music"], loop !== story, loop.isPlaying, loop.numberOfLoops == -1,
              audio.queued["music"] == nil else {
            throw CanvasError(message: "An intro did not run into its queued loop")
        }
        try audio.perform([["kind": "music_queue", "data": encoded, "loops": -1], ["kind": "music_stop"]])
        guard audio.tracks["music"] == nil, audio.queued["music"] == nil else {
            throw CanvasError(message: "Stopping the music kept its queued loop")
        }
    }
}

enum NativeVibration {
    static var available: Bool { UIDevice.current.userInterfaceIdiom == .phone }

    static func perform(_ count: Int, active: Bool, available: Bool,
                        play: (SystemSoundID) -> Void = AudioServicesPlayAlertSound) {
        guard active && available && count > 0 else { return }
        // Both original iOS games request this system alert, not a timed
        // Android vibration or a custom Taptic Engine pattern.
        for _ in 0..<count { play(kSystemSoundID_Vibrate) }
    }

    static func verify() throws {
        var alerts: [SystemSoundID] = []
        let record: (SystemSoundID) -> Void = { alerts.append($0) }
        perform(2, active: true, available: true, play: record)
        perform(1, active: false, available: true, play: record)
        perform(1, active: true, available: false, play: record)
        perform(0, active: true, available: true, play: record)
        guard alerts == [kSystemSoundID_Vibrate, kSystemSoundID_Vibrate] else {
            throw CanvasError(message: "Vibration did not honor device/activity gates or the native alert ID")
        }
    }
}

final class RuntimeController: UIViewController, UIDocumentPickerDelegate {
    private let canvas = GameCanvasView()
    private let engineQueue = DispatchQueue(label: "org.expruntime.engine", qos: .userInitiated)
    // Picked files are copied here, off the engine's queue, so frames (and the busy screen) keep running meanwhile.
    private let copyQueue = DispatchQueue(label: "org.expruntime.import-copy", qos: .userInitiated)
    private let renderer = NativeCanvas()
    // Frames are drawn here, in order, while the engine's queue runs Python for the next one: a frame takes the longer
    // of the two, not both. At most two wait (`rendering`), so the picture is never more than a frame behind.
    private let renderQueue = DispatchQueue(label: "org.expruntime.render", qos: .userInitiated)
    private var rendering = 0
    private let audio = NativeAudio()
    private let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
    private var displayLink: CADisplayLink?
    private var events: [[String: Any]] = []
    private var requests: [[String: Any]] = []
    private var working = false
    private var started = false             // the first request has gone (with the canvas's size)
    private var running = true
    private var activityGeneration = 0
    private var failed = false
    private var lastFrame = CACurrentMediaTime()
    private var pickerKind: String?
    private var backgroundTask = UIBackgroundTaskIdentifier.invalid
    private var verifying = false
    private var verificationReport: [String: Any] = [:]
    private var verificationChecks: [String] = []
    // The name entry's alert (SHS HD's UIAlertView in `SHSUITextEntry::tick`), as a UIAlertController: shown while
    // the app has one (each frame's `alert`), its button sent back as an `alert` event (the drawn alert's OK).
    private var alert: UIAlertController?
    private var alertAnswered = false       // OK was tapped; frames asked for before it still name the alert
    private func showAlert(_ wanted: [String: Any]?) {
        guard let wanted = wanted else {
            alertAnswered = false
            if let shown = alert { alert = nil; shown.dismiss(animated: true) }
            return
        }
        guard alert == nil, !alertAnswered, presentedViewController == nil else { return }
        let shown = UIAlertController(title: wanted["title"] as? String, message: wanted["message"] as? String,
                                      preferredStyle: .alert)
        shown.addAction(UIAlertAction(title: wanted["button"] as? String ?? "OK", style: .default) { [weak self] _ in
            self?.alert = nil
            self?.alertAnswered = true
            self?.events.append(["kind": "alert"])
        })
        alert = shown
        present(shown, animated: true)
    }
    private var holdingLandscape = false    // the side panels' landscape, held until the iPad is turned (requestLandscape)
    // The last frame's whole engine call and its drawing (ms), sent with the next frame for the runtime log's timings.
    private var engineMs = 0.0
    private var renderMs = 0.0

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .black
        canvas.backgroundColor = view.backgroundColor
        canvas.isMultipleTouchEnabled = true     // the pinch's second finger (GameCanvasView follows only one)
        canvas.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(canvas)
        NSLayoutConstraint.activate([
            canvas.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor),
            canvas.leadingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.leadingAnchor),
            canvas.trailingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.trailingAnchor),
            // The keyboard is drawn over the game, as HD's is (its name entry sits above it); tied to the keyboard's
            // top, the whole frame shrank into the space left above it.
            canvas.bottomAnchor.constraint(equalTo: view.safeAreaLayoutGuide.bottomAnchor)
        ])
        canvas.send = { [weak self] event in self?.events.append(event) }
        NotificationCenter.default.addObserver(self, selector: #selector(suspend), name: UIApplication.willResignActiveNotification, object: nil)
        NotificationCenter.default.addObserver(self, selector: #selector(resume), name: UIApplication.didBecomeActiveNotification, object: nil)
        NotificationCenter.default.addObserver(self, selector: #selector(audioInterrupted(_:)), name: AVAudioSession.interruptionNotification, object: nil)
        verifying = ProcessInfo.processInfo.arguments.contains("--self-test")
        if verifying { requests.append(["operation": "verify"]) }
        displayLink = CADisplayLink(target: self, selector: #selector(frame))
        displayLink?.preferredFramesPerSecond = 60
        displayLink?.add(to: .main, forMode: .common)
        frame()
    }

    @objc private func suspend() {
        running = false
        activityGeneration += 1
        events.removeAll()
        canvas.resignFirstResponder()
        requests.append(["operation": "active", "active": false])
        if backgroundTask == .invalid {
            backgroundTask = UIApplication.shared.beginBackgroundTask(withName: "Save story progress") { [weak self] in self?.finishBackgroundTask() }
        }
        frame()
    }
    private func finishBackgroundTask() {
        if backgroundTask != .invalid { UIApplication.shared.endBackgroundTask(backgroundTask); backgroundTask = .invalid }
    }
    @objc private func resume() {
        activityGeneration += 1
        running = true
        lastFrame = CACurrentMediaTime()
        requests.append(["operation": "active", "active": true])
        frame()
    }
    @objc private func audioInterrupted(_ note: Notification) {
        guard let type = note.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt else { return }
        if type == AVAudioSession.InterruptionType.began.rawValue { suspend() }
        else if UIApplication.shared.applicationState == .active { resume() }
    }

    @objc private func frame() {
        guard !working, !failed, rendering < 2, running || !requests.isEmpty else { return }
        // The app starts once the canvas has its size: the first frame's size picks the menus' scale (ios.Host).
        if !verifying && !started && canvas.pixelSize.width < 320 { return }
        started = true
        working = true
        let now = CACurrentMediaTime()
        let operation: [String: Any]
        if !requests.isEmpty { operation = requests.removeFirst() }
        else {
            let elapsed = Int((now - lastFrame) * 1000)
            operation = ["operation": "frame", "elapsed": elapsed, "events": events]
            events.removeAll()
            lastFrame += Double(elapsed) / 1000
        }
        if operation["operation"] as? String != "frame" { lastFrame = now }
        var body = operation.merging(["audio_playing": audio.playing, "audio_positions": audio.positions,
                                      "vibration_available": NativeVibration.available]) { _, value in value }
        body["timing"] = ["engine_ms": engineMs, "render_ms": renderMs]
        body["now"] = now * 1000         // the touches' clock (their `time`), for momentum.py
        // The app draws at the view's own pixel size (the iPad mini's 1536 x 2048), not a stretched 540 x 720 frame.
        // The simulator check keeps the app's default window: its taps are placed for that size.
        let pixels = canvas.pixelSize
        if !verifying && pixels.width >= 320 && pixels.height >= 320 {
            body["size"] = [Int(pixels.width), Int(pixels.height)]
        }
        let request = body
        let editsSent = canvas.edits           // keys typed after this go with the next frame (syncText)
        let directory = documents.path
        let renderer = self.renderer
        let feedbackGeneration = activityGeneration
        // The simulator check draws each frame before its result is handled: its captures and checks read that image.
        let drawsInline = verifying
        engineQueue.async {
            let began = CACurrentMediaTime()
            let response: Result<([String: Any], CGImage?), Error>
            var drawing: [String: Any]?
            do {
                let input = String(data: try JSONSerialization.data(withJSONObject: request), encoding: .utf8)!
                let output = try PythonBridge().request(input, directory: directory)
                guard let result = try JSONSerialization.jsonObject(with: Data(output.utf8)) as? [String: Any] else {
                    throw CanvasError(message: "Invalid runtime response")
                }
                if let fixture = result["drawing_test"] as? [String: Any] { try NativeCanvas.verify(fixture) }
                if drawsInline {
                    let image = try (result["frame"] as? [String: Any]).map { try renderer.render($0) }
                    response = .success((result, image))
                } else {
                    drawing = result["frame"] as? [String: Any]
                    response = .success((result, nil))
                }
            } catch { response = .failure(error) }
            // Queued before the drawing below can finish, so the main queue counts it (`rendering`) before it ends.
            let drawn = drawing
            // A frame's UIKit controls go up with its picture, when the render queue has drawn it: placed as the
            // result came, they ran a frame or more ahead of the sliding and zooming cards (more so at Retina).
            var framedControls: [[String: Any]]?
            if drawn != nil, case .success(let (result, _)) = response {
                framedControls = result["controls"] as? [[String: Any]]
            }
            let controls = framedControls
            let spent = (CACurrentMediaTime() - began) * 1000
            DispatchQueue.main.async {
                self.working = false
                self.engineMs = spent
                if drawn != nil { self.rendering += 1 }
                if operation["operation"] as? String == "active", operation["active"] as? Bool == false { self.finishBackgroundTask() }
                switch response {
                case .success(let (result, image)):
                    if let image = image { self.canvas.image = image }
                    self.canvas.generation = result["generation"] as? Int ?? 0
                    self.canvas.scrollable = result["scrollable"] as? Bool ?? false
                    if drawn == nil, let placed = result["controls"] as? [[String: Any]] { self.canvas.placeControls(placed) }
                    self.canvas.syncText(result["text"] as? String, editsSent: editsSent)
                    self.showAlert(result["alert"] as? [String: Any])
                    if self.running && result["keyboard"] as? Bool == true && self.alert == nil {
                        self.canvas.becomeFirstResponder()
                    } else { self.canvas.resignFirstResponder() }
                    NativeVibration.perform(result["vibrations"] as? Int ?? 0,
                                            active: self.running && feedbackGeneration == self.activityGeneration
                                                && UIApplication.shared.applicationState == .active,
                                            available: NativeVibration.available)
                    do {
                        if result["vibration_test"] as? Bool == true {
                            try NativeVibration.verify()
                            self.verificationChecks.append("Native vibration alert routing and device/activity gates (hardware not measured)")
                        }
                        if let fixture = result["audio_test"] as? String {
                            try NativeAudio.verify(fixture)
                            self.verificationChecks.append("Native audio looping, one-shot completion, in-place repeat/volume changes, playback positions, independent menu stream, pause and resume, an intro into its queued loop")
                        }
                        try self.audio.perform(result["audio"] as? [[String: Any]] ?? [])
                        if result["verify_menu_audio"] as? Bool == true { try self.audio.verifyMenuPlaying() }
                        if result["verify_click_audio"] as? Bool == true { try self.audio.verifySoundPlaying() }
                        if let track = result["verify_effect_audio"] as? String { try self.audio.verifyEffectPlaying(track) }
                    }
                    catch { self.showError("Audio: \(error.localizedDescription)", fatal: false); return }
                    // Copying, importing or preparing episodes (the app's busy screen): the iPad must not auto-lock
                    // and suspend the work. Auto-lock comes back once the app is idle (the main menu, ready).
                    let keepAwake = result["busy"] as? Bool == true
                    if UIApplication.shared.isIdleTimerDisabled != keepAwake {
                        UIApplication.shared.isIdleTimerDisabled = keepAwake
                    }
                    if let picker = result["picker"] as? String { self.pick(picker) }
                    if let link = result["open_url"] as? String, let url = URL(string: link) {
                        UIApplication.shared.open(url)
                    }
                    switch result["orientation"] as? String {
                    case "landscape": self.requestLandscape()
                    case "release": self.releaseOrientation()
                    default: break
                    }
                    if let request = result["update_request"] as? [String: Any] {
                        self.fetchRelease(request)
                    }
                    if self.verifying && result["status"] as? String == "passed" { self.verifyPresentation(result) }
                    if self.verifying && operation["operation"] as? String != "verify" {
                        if let check = result["verification_check"] as? String {
                            self.verificationChecks.append(check)
                            if let game = result["game"] as? String, let image = image {
                                let capture = check.contains("original playback") ? game
                                    : check.contains("shared main menu") ? "\(game)-menu"
                                    : check.contains("football scoreboard") ? "\(game)-football"
                                    : check.contains("word grid projection") ? "\(game)-word-grid"
                                    : check.contains("timed word choices") ? "\(game)-word-choices"
                                    : check.contains("orange gear held") ? "\(game)-gear-held"
                                    : check.contains("pause centered zoom") ? "\(game)-pause-zoom"
                                    : check.contains("scene badge within") ? "\(game)-scene-badge"
                                    : check.contains("original classroom quiz hints") ? "\(game)-classroom-hints"
                                    : check.contains("pause held selection") ? "\(game)-pause-held"
                                    : check.contains("grid tile fragments") ? "\(game)-grid-fragments"
                                    : check.contains("solid grid tile flip") ? "\(game)-grid-flip"
                                    : check.contains("word choice hints") ? "\(game)-word-held"
                                    : check.contains("Yes/No update prompt") ? "\(game)-update"
                                    : check.contains("project link") ? "\(game)-about" : nil
                                if let capture = capture {
                                    try? UIImage(cgImage: image).pngData()?.write(to: self.documents.appendingPathComponent("ios-content-\(capture).png"))
                                }
                            }
                        }
                        if result["verification_done"] as? Bool == true {
                            self.verifying = false
                            self.verificationReport["checks"] = self.verificationChecks
                            self.verificationReport["status"] = "passed"
                            try? JSONSerialization.data(withJSONObject: self.verificationReport, options: [.prettyPrinted, .sortedKeys])
                                .write(to: self.documents.appendingPathComponent("ios-presentation-verification.json"), options: .atomic)
                            if let image = image {
                                try? UIImage(cgImage: image).pngData()?.write(to: self.documents.appendingPathComponent("ios-chooser.png"))
                            }
                        } else if (operation["operation"] as? String)?.hasPrefix("verify_") == true {
                            self.requests.append(["operation": "verify_next"])
                        }
                    }
                case .failure(let error): self.showError(error.localizedDescription, fatal: true)
                }
                if !self.requests.isEmpty { self.frame() }
            }
            guard let drawn = drawn else { return }
            self.renderQueue.async {
                let began = CACurrentMediaTime()
                let rendered = Result { try renderer.render(drawn) }
                let spent = (CACurrentMediaTime() - began) * 1000
                DispatchQueue.main.async {
                    self.rendering -= 1
                    self.renderMs = spent
                    switch rendered {
                    case .success(let image):
                        self.canvas.image = image
                        if let placed = controls { self.canvas.placeControls(placed) }
                    case .failure(let error): self.showError(error.localizedDescription, fatal: true)
                    }
                    if !self.requests.isEmpty { self.frame() }
                }
            }
        }
    }

    // The side panels were turned on in portrait: the interface turns to landscape and stays there (only landscape is
    // allowed) until the iPad itself is held sideways; from then it follows the device again, so turning it back to
    // portrait is how the panels go off (ios.Host). A request with every orientation allowed was ignored: the iPad
    // was still held upright. iPadOS only turns a full-screen app (Info.plist UIRequiresFullScreen).
    private func requestLandscape() {
        guard !holdingLandscape, let scene = view.window?.windowScene else { return }
        holdingLandscape = true
        AppDelegate.orientations = .landscape
        UIDevice.current.beginGeneratingDeviceOrientationNotifications()
        NotificationCenter.default.addObserver(self, selector: #selector(deviceTurned),
                                               name: UIDevice.orientationDidChangeNotification, object: nil)
        if #available(iOS 16.0, *) {
            view.window?.rootViewController?.setNeedsUpdateOfSupportedInterfaceOrientations()
            scene.requestGeometryUpdate(.iOS(interfaceOrientations: .landscape)) { [weak self] error in
                DispatchQueue.main.async {
                    self?.requests.append(["operation": "message",
                                           "text": "Side panels could not turn to landscape: \(error.localizedDescription)"])
                }
            }
        } else {
            UIDevice.current.setValue(UIInterfaceOrientation.landscapeRight.rawValue, forKey: "orientation")
            UIViewController.attemptRotationToDeviceOrientation()
        }
    }

    @objc private func deviceTurned() {
        if UIDevice.current.orientation.isLandscape { releaseOrientation() }
    }

    // The iPad was turned to landscape, or the panels went off: every orientation is allowed again.
    private func releaseOrientation() {
        guard holdingLandscape else { return }
        holdingLandscape = false
        NotificationCenter.default.removeObserver(self, name: UIDevice.orientationDidChangeNotification, object: nil)
        UIDevice.current.endGeneratingDeviceOrientationNotifications()
        AppDelegate.orientations = .all
        if #available(iOS 16.0, *) {
            view.window?.rootViewController?.setNeedsUpdateOfSupportedInterfaceOrientations()
        } else {
            UIViewController.attemptRotationToDeviceOrientation()
        }
    }

    private func fetchRelease(_ parameters: [String: Any]) {
        guard let address = parameters["url"] as? String, let url = URL(string: address),
              url.scheme == "https", url.host == "api.github.com" else { return }
        let timeout = Double(parameters["timeout"] as? Int ?? 8)
        let limit = parameters["max_bytes"] as? Int ?? 1_048_576
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = timeout
        configuration.timeoutIntervalForResource = timeout
        configuration.urlCache = nil
        let session = URLSession(configuration: configuration)
        var request = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: timeout)
        for (key, value) in parameters["headers"] as? [String: String] ?? [:] {
            request.setValue(value, forHTTPHeaderField: key)
        }
        session.dataTask(with: request) { [weak self] data, response, error in
            var payload: String?
            if error == nil, (response as? HTTPURLResponse)?.statusCode == 200,
               let data = data, data.count <= limit {
                payload = String(data: data, encoding: .utf8)
            }
            session.finishTasksAndInvalidate()
            let result: [String: Any] = ["operation": "update_result", "payload": payload.map { $0 as Any } ?? NSNull()]
            DispatchQueue.main.async {
                guard let self = self, !self.failed else { return }
                self.requests.append(result)
            }
        }.resume()
    }

    private func showError(_ message: String, fatal: Bool) {
        if fatal || verifying { failed = true; finishBackgroundTask() }
        if fatal { UIApplication.shared.isIdleTimerDisabled = false }     // a stopped runtime is never busy
        guard presentedViewController == nil else { return }
        if !fatal && !verifying { suspend() }
        let alert = UIAlertController(title: fatal ? "Runtime stopped" : "Audio unavailable", message: message, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "OK", style: .default) { [weak self] _ in
            if !fatal && self?.verifying == false { self?.resume() }
        })
        present(alert, animated: true)
        if verifying {
            let report: [String: Any] = ["status": "failed", "platform": "ios", "error": message, "checks": verificationChecks]
            try? JSONSerialization.data(withJSONObject: report).write(to: documents.appendingPathComponent("ios-presentation-verification.json"), options: .atomic)
        }
    }

    private func pick(_ kind: String) {
        pickerKind = kind
        // File providers can initially report an IPA/EXP as an opaque item.
        // Let the shared importer validate extensions and archive contents.
        let types: [UTType] = kind == "library" ? [.folder] : [.item]
        let picker = UIDocumentPickerViewController(forOpeningContentTypes: types, asCopy: false)
        picker.allowsMultipleSelection = kind == "episodes" || kind == "apk"
        picker.delegate = self
        present(picker, animated: true)
    }

    func documentPicker(_ controller: UIDocumentPickerViewController, didPickDocumentsAt urls: [URL]) {
        guard let kind = pickerKind else { return }
        let documents = self.documents
        let scopes = urls.map { $0.startAccessingSecurityScopedResource() }
        // The app shows "Copying ..." until the copy below ends in an import or a message (a 1 GB zip takes a while;
        // the screen used to stay frozen on the page the picker was opened from).
        requests.append(["operation": "import_copying", "kind": kind, "names": urls.map { $0.lastPathComponent }])
        frame()
        copyQueue.async {
            let result: Result<[String], Error>
            do {
                let parent = documents.appendingPathComponent(kind == "library" ? "SHSHD Runtime/libraries/imported" : "Imports")
                    .appendingPathComponent(UUID().uuidString)
                try FileManager.default.createDirectory(at: parent, withIntermediateDirectories: true)
                var paths: [String] = []
                for (index, url) in urls.enumerated() {
                    // Coordinate iCloud downloads; keep the original basename for catalogs.
                    let destination = parent.appendingPathComponent("\(index)", isDirectory: true).appendingPathComponent(url.lastPathComponent)
                    try FileManager.default.createDirectory(at: destination.deletingLastPathComponent(), withIntermediateDirectories: true)
                    var coordinationError: NSError?
                    var copyingError: Error?
                    NSFileCoordinator().coordinate(readingItemAt: url, options: .withoutChanges, error: &coordinationError) { source in
                        do { try FileManager.default.copyItem(at: source, to: destination) }
                        catch { copyingError = error }
                    }
                    if let error = coordinationError ?? copyingError as NSError? { throw error }
                    paths.append(destination.path)
                }
                result = .success(paths)
            } catch { result = .failure(error) }
            for (url, scoped) in zip(urls, scopes) where scoped { url.stopAccessingSecurityScopedResource() }
            DispatchQueue.main.async {
                switch result {
                case .success(let paths): self.requests.append(["operation": "import", "kind": kind, "paths": paths])
                case .failure(let error): self.requests.append(["operation": "message", "text": error.localizedDescription])
                }
                self.frame()
            }
        }
    }

    private func verifyPresentation(_ core: [String: Any]) {
        verificationReport = core
        verificationChecks = (core["checks"] as? [String] ?? []) + ["Native CoreGraphics pixels: orientation, clipping, scale, rotation, alpha, background panning, dialogue-box growth, portrait housing, expression fades, intersecting depth and pause sepia"]
        requests.append(["operation": "verify_start"])
    }
}
