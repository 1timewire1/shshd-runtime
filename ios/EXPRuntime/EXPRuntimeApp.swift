import SwiftUI
import UniformTypeIdentifiers
import AVFAudio
import AudioToolbox

@main
struct EXPRuntimeApp: App {
    var body: some Scene {
        WindowGroup { RuntimeView().background(Color.black.ignoresSafeArea()).ignoresSafeArea(.keyboard) }
    }
}

struct RuntimeView: UIViewControllerRepresentable {
    func makeUIViewController(context: Context) -> RuntimeController { RuntimeController() }
    func updateUIViewController(_ controller: RuntimeController, context: Context) {}
}

final class GameCanvasView: UIView, UIKeyInput {
    var image: CGImage? { didSet { setNeedsDisplay() } }
    var send: (([String: Any]) -> Void)?
    var scrollable = false
    var generation = 0
    private var touchGeneration = 0
    private var start: CGPoint?
    private var previous: CGPoint?
    private var dragging = false
    var hasText: Bool { true }
    override var canBecomeFirstResponder: Bool { true }
    var autocorrectionType: UITextAutocorrectionType = .no
    var autocapitalizationType: UITextAutocapitalizationType = .none
    var returnKeyType: UIReturnKeyType = .done

    private var viewport: CGRect {
        let scale = min(bounds.width / 480, bounds.height / 720)
        let size = CGSize(width: 480 * scale, height: 720 * scale)
        return CGRect(x: (bounds.width - size.width) / 2, y: (bounds.height - size.height) / 2,
                      width: size.width, height: size.height)
    }

    override func draw(_ rect: CGRect) {
        UIColor.black.setFill()
        UIRectFill(bounds)
        guard let image = image else { return }
        UIImage(cgImage: image).draw(in: viewport)
    }

    private func point(_ touch: UITouch) -> CGPoint {
        let p = touch.location(in: self), v = viewport
        return CGPoint(x: (p.x - v.minX) * 480 / v.width, y: (p.y - v.minY) * 720 / v.height)
    }

    private func pointer(_ kind: String, _ p: CGPoint) { send?(["kind": kind, "point": [p.x, p.y], "generation": touchGeneration]) }
    override func touchesBegan(_ touches: Set<UITouch>, with event: UIEvent?) {
        guard let touch = touches.first else { return }
        let p = point(touch)
        touchGeneration = generation
        start = p; previous = p; dragging = false
        if !scrollable { pointer("down", p) }
    }
    override func touchesMoved(_ touches: Set<UITouch>, with event: UIEvent?) {
        guard let touch = touches.first, let first = start, let last = previous else { return }
        let p = point(touch)
        if scrollable {
            if abs(p.y - first.y) > 8 { dragging = true }
            if dragging { send?(["kind": "scroll", "delta": (p.y - last.y) / 52.5, "generation": touchGeneration]) }
        } else { pointer("move", p) }
        previous = p
    }
    override func touchesEnded(_ touches: Set<UITouch>, with event: UIEvent?) {
        guard let touch = touches.first, let first = start else { return }
        let p = point(touch)
        if scrollable && !dragging { pointer("down", first); pointer("up", p) }
        else if !scrollable { pointer("up", p) }
        start = nil; previous = nil
    }
    override func touchesCancelled(_ touches: Set<UITouch>, with event: UIEvent?) {
        send?(["kind": "cancel"]); start = nil; previous = nil
    }
    func insertText(_ text: String) {
        if text == "\n" { send?(["kind": "key", "key": "return", "generation": generation]) }
        else { send?(["kind": "text", "text": text, "generation": generation]) }
    }
    func deleteBackward() { send?(["kind": "key", "key": "backspace", "generation": generation]) }
}

final class NativeAudio: NSObject, AVAudioPlayerDelegate {
    private var tracks: [String: AVAudioPlayer] = [:]
    private var pausedTracks: Set<String> = []
    private var sounds: [AVAudioPlayer] = []
    func perform(_ commands: [[String: Any]]) throws {
        for command in commands {
            guard let kind = command["kind"] as? String else { throw CanvasError(message: "Missing audio command") }
            let track = command["track"] as? String ?? (kind.hasPrefix("menu_") ? "menu" : "music")
            let action = kind.hasPrefix("menu_") ? "music_" + kind.dropFirst(5) : kind
            switch action {
            case "music_load", "sound":
                guard let encoded = command["data"] as? String, let data = Data(base64Encoded: encoded) else {
                    throw CanvasError(message: "Invalid audio data")
                }
                try AVAudioSession.sharedInstance().setCategory(.ambient, mode: .default)
                try AVAudioSession.sharedInstance().setActive(true)
                let player = try AVAudioPlayer(data: data)
                player.delegate = self
                guard player.prepareToPlay() else { throw CanvasError(message: "Could not prepare audio playback") }
                if action == "music_load" { tracks[track] = player; pausedTracks.remove(track) }
                else {
                    guard player.play() else { throw CanvasError(message: "Could not start sound playback") }
                    sounds.append(player)
                }
            case "music_play":
                guard let player = tracks[track] else { throw CanvasError(message: "Music has not been loaded") }
                player.numberOfLoops = (command["loops"] as? NSNumber)?.intValue ?? 0
                player.currentTime = (command["start"] as? NSNumber)?.doubleValue ?? 0
                guard player.play() else { throw CanvasError(message: "Could not start music playback") }
                pausedTracks.remove(track)
            case "music_pause":
                if let player = tracks[track], player.isPlaying {
                    player.pause()
                    pausedTracks.insert(track)
                }
            case "music_resume":
                if pausedTracks.remove(track) != nil, let player = tracks[track], !player.play() {
                    throw CanvasError(message: "Could not resume music playback")
                }
            case "music_stop":
                tracks[track]?.stop(); tracks.removeValue(forKey: track); pausedTracks.remove(track)
            case "music_volume":
                tracks[track]?.volume = (command["volume"] as? NSNumber)?.floatValue ?? 1
            case "music_loops":
                tracks[track]?.numberOfLoops = (command["loops"] as? NSNumber)?.intValue ?? 0
            case "sounds_stop": sounds.forEach { $0.stop() }; sounds.removeAll()
            default: throw CanvasError(message: "Unsupported audio command")
            }
        }
    }
    func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        sounds.removeAll { $0 === player }
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
    private let audio = NativeAudio()
    private let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
    private var displayLink: CADisplayLink?
    private var events: [[String: Any]] = []
    private var requests: [[String: Any]] = []
    private var working = false
    private var running = true
    private var activityGeneration = 0
    private var failed = false
    private var lastFrame = CACurrentMediaTime()
    private var pickerKind: String?
    private var backgroundTask = UIBackgroundTaskIdentifier.invalid
    private var verifying = false
    private var verificationReport: [String: Any] = [:]
    private var verificationChecks: [String] = []

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .black
        canvas.backgroundColor = view.backgroundColor
        canvas.isMultipleTouchEnabled = false
        canvas.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(canvas)
        NSLayoutConstraint.activate([
            canvas.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor),
            canvas.leadingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.leadingAnchor),
            canvas.trailingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.trailingAnchor),
            canvas.bottomAnchor.constraint(equalTo: view.keyboardLayoutGuide.topAnchor)
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
        guard !working, !failed, running || !requests.isEmpty else { return }
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
        let request = operation.merging(["audio_playing": audio.playing, "audio_positions": audio.positions,
                                         "vibration_available": NativeVibration.available]) { _, value in value }
        let directory = documents.path
        let renderer = self.renderer
        let feedbackGeneration = activityGeneration
        engineQueue.async {
            let response: Result<([String: Any], CGImage?), Error>
            do {
                let input = String(data: try JSONSerialization.data(withJSONObject: request), encoding: .utf8)!
                let output = try PythonBridge().request(input, directory: directory)
                guard let result = try JSONSerialization.jsonObject(with: Data(output.utf8)) as? [String: Any] else {
                    throw CanvasError(message: "Invalid runtime response")
                }
                if let fixture = result["drawing_test"] as? [String: Any] { try NativeCanvas.verify(fixture) }
                let image = try (result["frame"] as? [String: Any]).map { try renderer.render($0) }
                response = .success((result, image))
            } catch { response = .failure(error) }
            DispatchQueue.main.async {
                self.working = false
                if operation["operation"] as? String == "active", operation["active"] as? Bool == false { self.finishBackgroundTask() }
                switch response {
                case .success(let (result, image)):
                    if let image = image { self.canvas.image = image }
                    self.canvas.generation = result["generation"] as? Int ?? 0
                    self.canvas.scrollable = result["scrollable"] as? Bool ?? false
                    if self.running && result["keyboard"] as? Bool == true { self.canvas.becomeFirstResponder() }
                    else { self.canvas.resignFirstResponder() }
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
                            self.verificationChecks.append("Native audio looping, one-shot completion, in-place repeat/volume changes, playback positions, independent menu stream, pause and resume")
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
