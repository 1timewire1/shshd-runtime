import UIKit
import ImageIO

struct CanvasError: LocalizedError {
    let message: String
    var errorDescription: String? { message }
}

/// Renders the shared Python presentation commands. No game geometry or state
/// belongs here. Image nodes are immutable and released by each frame's graph.
final class NativeCanvas {
    private var images: [Int: CGImage] = [:]
    // Drawn nodes not made into an image yet: one is drawn when something reads it (`image`). A node that only
    // scales another, blitted by its parent, is never made: the parent draws the scaled source itself (the story
    // layer, scaled to the frame each time a line types on, would otherwise be a full-frame image of its own).
    private var drawings: [Int: [String: Any]] = [:]
    private struct Texture {
        let width: Int, height: Int
        let pixels: Data
    }
    private var textures: [Int: Texture] = [:]
    private let space = CGColorSpace(name: CGColorSpace.sRGB)!

    private func texture(_ op: [String: Any]) throws -> Texture {
        guard let id = op["source"] as? Int else { throw CanvasError(message: "Missing texture") }
        if let cached = textures[id] { return cached }
        let source = try image(op)
        guard let normalized = CGContext(data: nil, width: source.width, height: source.height,
            bitsPerComponent: 8, bytesPerRow: source.width * 4, space: space,
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue),
            let data = normalized.data else { throw CanvasError(message: "Cannot read texture") }
        normalized.draw(source, in: CGRect(x: 0, y: 0, width: source.width, height: source.height))
        let value = Texture(width: source.width, height: source.height,
                            pixels: Data(bytes: data, count: source.width * source.height * 4))
        textures[id] = value
        return value
    }

    private func perspectiveImage(_ op: [String: Any], size: CGSize,
                                  depth: inout [Double], viewport: CGSize, origin: CGPoint) throws -> CGImage {
        let source = try texture(op)
        let c = try numbers(op["coefficients"]).map { Double($0) }
        let width = Int(size.width), height = Int(size.height)
        let plane = (op["depth_plane"] as? [NSNumber])?.map { $0.doubleValue }
        if let plane = plane {
            guard plane.count == 3, plane.allSatisfy({ $0.isFinite }) else {
                throw CanvasError(message: "Invalid depth plane")
            }
            if depth.isEmpty { depth = Array(repeating: 0, count: Int(viewport.width * viewport.height)) }
        }
        guard c.count == 8, c.allSatisfy({ $0.isFinite }), width > 0, height > 0,
              width <= 8192, height <= 8192, width * height <= 16_777_216 else {
            throw CanvasError(message: "Invalid perspective texture")
        }
        // The shared renderer supplies the inverse projective map. Only pixel
        // sampling lives here; camera, faces, clocks and hit regions stay in Python.
        var pixels = Data(count: width * height * 4)
        pixels.withUnsafeMutableBytes { output in
            source.pixels.withUnsafeBytes { input in
                let src = input.bindMemory(to: UInt8.self)
                let dst = output.bindMemory(to: UInt8.self)
                for y in 0..<height {
                    let fy = Double(y) + 0.5
                    var un = c[0] * 0.5 + c[1] * fy + c[2]
                    var vn = c[3] * 0.5 + c[4] * fy + c[5]
                    var dn = c[6] * 0.5 + c[7] * fy + 1
                    for x in 0..<width {
                        let u = un / dn, v = vn / dn
                        un += c[0]; vn += c[3]; dn += c[6]
                        if !u.isFinite || !v.isFinite || u < 0 || v < 0 || u >= 1 || v >= 1 { continue }
                        if let plane = plane {
                            let px = Int(origin.x) + x, py = Int(origin.y) + y
                            if px < 0 || py < 0 || px >= Int(viewport.width) || py >= Int(viewport.height) { continue }
                            let index = py * Int(viewport.width) + px
                            let distance = plane[0] * (Double(px) + 0.5) + plane[1] * (Double(py) + 0.5) + plane[2]
                            if distance < depth[index] { continue }
                            depth[index] = distance
                        }
                        let sx = max(0, min(Double(source.width - 1), u * Double(source.width) - 0.5))
                        let sy = max(0, min(Double(source.height - 1), v * Double(source.height) - 0.5))
                        let ix = Int(sx), iy = Int(sy), ax = sx - Double(ix), ay = sy - Double(iy)
                        let p = (iy * source.width + ix) * 4
                        let q = (iy * source.width + min(ix + 1, source.width - 1)) * 4
                        let r = (min(iy + 1, source.height - 1) * source.width + ix) * 4
                        let s = (min(iy + 1, source.height - 1) * source.width + min(ix + 1, source.width - 1)) * 4
                        let destination = (y * width + x) * 4
                        for channel in 0..<4 {
                            let top = Double(src[p + channel]) * (1 - ax) + Double(src[q + channel]) * ax
                            let bottom = Double(src[r + channel]) * (1 - ax) + Double(src[s + channel]) * ax
                            dst[destination + channel] = UInt8(max(0, min(255, top * (1 - ay) + bottom * ay)))
                        }
                    }
                }
            }
        }
        guard let provider = CGDataProvider(data: pixels as CFData), let result = CGImage(
            width: width, height: height, bitsPerComponent: 8, bitsPerPixel: 32, bytesPerRow: width * 4,
            space: space, bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.premultipliedLast.rawValue)
                .union(.byteOrder32Big), provider: provider, decode: nil, shouldInterpolate: false, intent: .defaultIntent) else {
            throw CanvasError(message: "Cannot project texture")
        }
        return result
    }

    private func colorMatrixImage(_ op: [String: Any]) throws -> CGImage {
        let source = try texture(op)
        guard let rows = op["matrix"] as? [[NSNumber]], rows.count == 3,
              rows.allSatisfy({ $0.count == 3 && $0.allSatisfy { $0.doubleValue.isFinite } }) else {
            throw CanvasError(message: "Invalid color matrix")
        }
        let matrix = rows.map { $0.map { $0.doubleValue } }
        var pixels = Data(count: source.pixels.count)
        // Pillow's 12-value convert matrix (the HD pause overlay's sepia): a row and an offset per channel, in
        // single precision, rounded half up and clamped (`ImagingConvertMatrix`).
        if let offsets = op["offset"] as? [NSNumber] {
            guard offsets.count == 3, offsets.allSatisfy({ $0.doubleValue.isFinite }) else {
                throw CanvasError(message: "Invalid color matrix offset")
            }
            let m = rows.map { $0.map { $0.floatValue } }, o = offsets.map { $0.floatValue }
            pixels.withUnsafeMutableBytes { output in
                source.pixels.withUnsafeBytes { input in
                    let src = input.bindMemory(to: UInt8.self), dst = output.bindMemory(to: UInt8.self)
                    for offset in stride(from: 0, to: src.count, by: 4) {
                        let red = Float(src[offset]), green = Float(src[offset + 1]), blue = Float(src[offset + 2])
                        for channel in 0..<3 {
                            let row = m[channel]
                            let value: Float = red * row[0] + green * row[1] + blue * row[2] + o[channel] + 0.5
                            dst[offset + channel] = value <= 0 ? 0 : value >= 255 ? 255 : UInt8(value)
                        }
                        dst[offset + 3] = 255
                    }
                }
            }
            return try matrixImage(pixels, source)
        }
        pixels.withUnsafeMutableBytes { output in
            source.pixels.withUnsafeBytes { input in
                let src = input.bindMemory(to: UInt8.self), dst = output.bindMemory(to: UInt8.self)
                for offset in stride(from: 0, to: src.count, by: 4) {
                    let red = Double(src[offset]), green = Double(src[offset + 1]), blue = Double(src[offset + 2])
                    for channel in 0..<3 {
                        let row = matrix[channel]
                        let value = (red * row[0] + green * row[1]) + blue * row[2]
                        dst[offset + channel] = UInt8(max(0, min(255, value)))
                    }
                    dst[offset + 3] = 255
                }
            }
        }
        return try matrixImage(pixels, source)
    }

    private func matrixImage(_ pixels: Data, _ source: Texture) throws -> CGImage {
        guard let provider = CGDataProvider(data: pixels as CFData), let image = CGImage(
            width: source.width, height: source.height, bitsPerComponent: 8, bitsPerPixel: 32,
            bytesPerRow: source.width * 4, space: space,
            bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.premultipliedLast.rawValue).union(.byteOrder32Big),
            provider: provider, decode: nil, shouldInterpolate: false, intent: .defaultIntent) else {
            throw CanvasError(message: "Cannot transform image colors")
        }
        return image
    }

    private func numbers(_ value: Any?) throws -> [CGFloat] {
        guard let values = value as? [NSNumber] else { throw CanvasError(message: "Invalid drawing coordinates") }
        return values.map { CGFloat($0.doubleValue) }
    }

    private func rect(_ value: Any?) throws -> CGRect {
        let v = try numbers(value)
        guard v.count == 4 else { throw CanvasError(message: "Invalid drawing rectangle") }
        return CGRect(x: v[0], y: v[1], width: v[2], height: v[3])
    }

    private func image(_ op: [String: Any]) throws -> CGImage {
        guard let id = op["source"] as? Int else { throw CanvasError(message: "Missing drawing source") }
        return try image(id)
    }

    private func image(_ id: Int) throws -> CGImage {
        if let image = images[id] { return image }
        guard let node = drawings.removeValue(forKey: id) else { throw CanvasError(message: "Missing drawing source") }
        let image = try renderNode(node)
        images[id] = image
        return image
    }

    /// The source and smoothing of a node that only scales an image to its own size, while it is not an image yet.
    private func scaling(_ op: [String: Any]) -> (source: [String: Any], size: CGSize)? {
        guard let id = op["source"] as? Int, images[id] == nil, let node = drawings[id],
              let ops = node["ops"] as? [[String: Any]], ops.count == 1, ops[0]["kind"] as? String == "scale",
              ops[0]["clip"] == nil, ops[0]["color"] == nil, ops[0]["blend"] == nil,
              let size = node["size"] as? [NSNumber], size.count == 2 else { return nil }
        return (ops[0], CGSize(width: size[0].doubleValue, height: size[1].doubleValue))
    }

    private func drawImage(_ image: CGImage, _ rect: CGRect, _ context: CGContext) {
        context.saveGState()
        context.translateBy(x: rect.minX, y: rect.maxY)
        context.scaleBy(x: 1, y: -1)
        context.draw(image, in: CGRect(origin: .zero, size: rect.size))
        context.restoreGState()
    }

    private func renderNode(_ node: [String: Any]) throws -> CGImage {
        if let png = node["png"] as? String, let data = Data(base64Encoded: png),
           let source = CGImageSourceCreateWithData(data as CFData, nil),
           let result = CGImageSourceCreateImageAtIndex(source, 0, nil) { return result }
        let size = try numbers(node["size"])
        guard size.count == 2, size[0] > 0, size[1] > 0, size[0] <= 8192, size[1] <= 8192,
              let context = CGContext(data: nil, width: Int(size[0]), height: Int(size[1]), bitsPerComponent: 8,
                                      bytesPerRow: Int(size[0]) * 4, space: space,
                                      bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue),
              let ops = node["ops"] as? [[String: Any]] else {
            throw CanvasError(message: "Invalid drawing surface")
        }
        context.translateBy(x: 0, y: size[1])
        context.scaleBy(x: 1, y: -1)
        var depth: [Double] = []
        for op in ops {
            guard let kind = op["kind"] as? String else { throw CanvasError(message: "Missing drawing operation") }
            context.saveGState()
            defer { context.restoreGState() }
            context.setShouldAntialias(false)
            context.interpolationQuality = .none
            if let clip = op["clip"] { context.clip(to: try rect(clip)) }
            if let color = op["color"] {
                let values = try numbers(color).map { $0 / 255 }
                guard values.count == 4, let color = CGColor(colorSpace: space, components: values) else {
                    throw CanvasError(message: "Invalid drawing color")
                }
                context.setFillColor(color)
                context.setStrokeColor(color)
                context.setBlendMode(.copy)
            }
            // SDL's RGB multiply fill and additive blit over opaque pixels (drawing.py Surface.fill / blit: the HD
            // menus' fades, drawn every frame).
            switch op["blend"] as? String {
            case "multiply"?: context.setBlendMode(.multiply)
            case "add"?: context.setBlendMode(.plusLighter)
            case nil: break
            default: throw CanvasError(message: "Unsupported blend")
            }
            let width = (op["width"] as? NSNumber)?.doubleValue ?? 0
            context.setLineWidth(width)
            switch kind {
            case "fill":
                context.fill(try rect(op["rect"]))
            case "rect":
                let radius = (op["radius"] as? NSNumber)?.doubleValue ?? 0
                var bounds = try rect(op["rect"])
                if width > 0 { bounds = bounds.insetBy(dx: width / 2, dy: width / 2) }
                context.addPath(CGPath(roundedRect: bounds, cornerWidth: radius, cornerHeight: radius, transform: nil))
                context.drawPath(using: width > 0 ? .stroke : .fill)
            case "line", "polygon":
                guard let points = op["points"] as? [[NSNumber]], !points.isEmpty else {
                    throw CanvasError(message: "Invalid drawing path")
                }
                let offset = kind == "line" && Int(width) % 2 == 1 ? 0.5 : 0.0
                for (i, values) in points.enumerated() {
                    guard values.count == 2 else { throw CanvasError(message: "Invalid point") }
                    let point = CGPoint(x: values[0].doubleValue + offset, y: values[1].doubleValue + offset)
                    if i == 0 { context.move(to: point) } else { context.addLine(to: point) }
                }
                if kind == "polygon" { context.closePath() }
                context.setLineCap(.square)
                context.drawPath(using: width > 0 ? .stroke : .fill)
            case "circle":
                let center = try numbers(op["center"])
                let radius = (op["radius"] as? NSNumber)?.doubleValue ?? 0
                guard center.count == 2 else { throw CanvasError(message: "Invalid circle") }
                let bounds = CGRect(x: center[0] - radius, y: center[1] - radius, width: radius * 2, height: radius * 2)
                if width > 0 { context.strokeEllipse(in: bounds.insetBy(dx: width / 2, dy: width / 2)) }
                else { context.fillEllipse(in: bounds) }
            case "ellipse":
                var bounds = try rect(op["rect"])
                if width > 0 {
                    bounds = bounds.insetBy(dx: width / 2, dy: width / 2)
                    context.strokeEllipse(in: bounds)
                } else {
                    context.fillEllipse(in: bounds)
                }
            case "blit":
                let at = try numbers(op["at"])
                guard at.count == 2 else { throw CanvasError(message: "Invalid image position") }
                context.setAlpha(CGFloat((op["alpha"] as? NSNumber)?.doubleValue ?? 255) / 255)
                if let scaled = scaling(op) {
                    let source = try image(scaled.source)
                    context.interpolationQuality = (scaled.source["smooth"] as? Bool) == true ? .medium : .none
                    drawImage(source, CGRect(origin: CGPoint(x: at[0], y: at[1]), size: scaled.size), context)
                } else {
                    let source = try image(op)
                    drawImage(source, CGRect(x: at[0], y: at[1], width: CGFloat(source.width), height: CGFloat(source.height)), context)
                }
            case "scale":
                let source = try image(op)
                context.interpolationQuality = (op["smooth"] as? Bool) == true ? .medium : .none
                drawImage(source, CGRect(x: 0, y: 0, width: size[0], height: size[1]), context)
            case "color_matrix":
                drawImage(try colorMatrixImage(op), CGRect(x: 0, y: 0, width: size[0], height: size[1]), context)
            case "textured_quad", "depth_quad":
                let bounds = try rect(op["bounds"])
                let projected = try perspectiveImage(op, size: bounds.size, depth: &depth,
                    viewport: CGSize(width: size[0], height: size[1]), origin: bounds.origin)
                context.setAlpha(CGFloat((op["alpha"] as? NSNumber)?.doubleValue ?? 255) / 255)
                drawImage(projected, bounds, context)
            case "textured_rows":
                let source = try image(op)
                guard let rows = op["rows"] as? [[NSNumber]], !rows.isEmpty, rows.count <= 8192,
                      let top = op["top"] as? NSNumber,
                      let projected = CGContext(data: nil, width: source.width, height: rows.count,
                          bitsPerComponent: 8, bytesPerRow: source.width * 4, space: space,
                          bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue) else {
                    throw CanvasError(message: "Invalid textured rows")
                }
                // Match the shared two-pass scanline projection: resize the
                // source vertically, then stretch each row horizontally.
                projected.translateBy(x: 0, y: CGFloat(rows.count))
                projected.scaleBy(x: 1, y: -1)
                projected.interpolationQuality = .medium
                drawImage(source, CGRect(x: 0, y: 0, width: source.width, height: rows.count), projected)
                guard let scaled = projected.makeImage() else { throw CanvasError(message: "Cannot project image") }
                context.interpolationQuality = .medium
                context.setAlpha(CGFloat((op["alpha"] as? NSNumber)?.doubleValue ?? 255) / 255)
                for (y, row) in rows.enumerated() {
                    guard row.count == 2, row[1].intValue > 0, row[1].intValue <= 8192,
                          let strip = scaled.cropping(to: CGRect(x: 0, y: y, width: source.width, height: 1)) else {
                        throw CanvasError(message: "Invalid textured row")
                    }
                    drawImage(strip, CGRect(x: row[0].intValue, y: top.intValue + y, width: row[1].intValue, height: 1), context)
                }
            case "rotate":
                let source = try image(op)
                let angle = (op["angle"] as? NSNumber)?.doubleValue ?? 0
                let scale = (op["scale"] as? NSNumber)?.doubleValue ?? 1
                context.interpolationQuality = (op["smooth"] as? Bool) == true ? .medium : .none
                context.translateBy(x: size[0] / 2, y: size[1] / 2)
                context.rotate(by: -angle * .pi / 180)
                context.scaleBy(x: scale, y: scale)
                drawImage(source, CGRect(x: -CGFloat(source.width) / 2, y: -CGFloat(source.height) / 2,
                                         width: CGFloat(source.width), height: CGFloat(source.height)), context)
            case "flip":
                let source = try image(op)
                let h = op["horizontal"] as? Bool == true, v = op["vertical"] as? Bool == true
                context.translateBy(x: h ? size[0] : 0, y: v ? size[1] : 0)
                context.scaleBy(x: h ? -1 : 1, y: v ? -1 : 1)
                drawImage(source, CGRect(x: 0, y: 0, width: size[0], height: size[1]), context)
            default:
                throw CanvasError(message: "Unsupported drawing operation: \(kind)")
            }
        }
        guard let image = context.makeImage() else { throw CanvasError(message: "Cannot create drawing image") }
        return image
    }

    private func register(_ frame: [String: Any]) throws -> Int {
        guard let nodes = frame["nodes"] as? [[String: Any]], let root = frame["root"] as? Int else {
            throw CanvasError(message: "Invalid drawing frame")
        }
        for node in nodes {
            guard let id = node["id"] as? Int else { throw CanvasError(message: "Invalid drawing identifier") }
            if node["png"] != nil { images[id] = try renderNode(node) } else { drawings[id] = node }
        }
        return root
    }

    private func release(_ frame: [String: Any]) -> [Int] {
        let released = frame["release"] as? [Int] ?? []
        for id in released {
            images.removeValue(forKey: id)
            drawings.removeValue(forKey: id)
            textures.removeValue(forKey: id)
            composed.removeValue(forKey: id)
        }
        return released
    }

    func render(_ frame: [String: Any]) throws -> CGImage {
        let result = try image(try register(frame))
        _ = release(frame)
        return result
    }

    // -- Compositing on the GPU (phase 4): the frame's big layers that only stack other pictures become Core Animation
    // layers (LayerCompositor), so a moving piece no longer redraws every full-size layer above it on the CPU.

    /// Nodes this big or bigger whose ops are only blits, stretches and plain fills are composited, not drawn. A small
    /// one is cheaper as one picture, and so is one of many ops (a line of text is a blit a letter).
    var composeMinimumPixels: CGFloat = 250_000
    let composeMaximumOps = 64
    private var composed: [Int: ComposedNode] = [:]

    func compose(_ frame: [String: Any]) throws -> ComposedFrame {
        let root = try composedNode(try register(frame))
        return ComposedFrame(root: root, released: release(frame))
    }

    private func composedNode(_ id: Int) throws -> ComposedNode {
        if let done = composed[id] { return done }
        let result: ComposedNode
        if let node = drawings[id], let parts = try composedParts(node) {
            let size = try numbers(node["size"])
            result = ComposedNode(id: id, size: CGSize(width: size[0], height: size[1]), picture: nil, parts: parts)
        } else {
            let picture = try image(id)
            result = ComposedNode(id: id, size: CGSize(width: picture.width, height: picture.height), picture: picture, parts: [])
        }
        composed[id] = result
        return result
    }

    /// A `scale` op's source stretched: a composited node's own layers, scaled by Core Animation (the New Rules arena's
    /// 1956 x 2608 canvas, stretched to the window each frame, was drawn into a picture first: 70 ms a frame), or a
    /// picture's.
    private func stretch(_ op: [String: Any]) throws -> ComposedPart.Content {
        guard let id = op["source"] as? Int else { throw CanvasError(message: "Missing drawing source") }
        let smooth = (op["smooth"] as? Bool) == true
        // Nearest-neighbour stretches (pixel art: the arena's native 489 x 652 layer) stay pictures: a transformed
        // group's pictures would each be sampled with their own (linear) filter, and those sources are small.
        guard smooth else { return .stretched(try image(op), smooth: false) }
        let source = try composedNode(id)
        if let picture = source.picture { return .stretched(picture, smooth: true) }
        return .scaled(source, smooth: true)
    }

    /// A clip that cuts something off `frame`, or nil (every op carries one, mostly its whole surface).
    private func cutting(_ clip: CGRect?, _ frame: CGRect) -> CGRect? {
        guard let clip = clip, !clip.contains(frame) else { return nil }
        return clip
    }

    /// The node's ops as layers, or nil when one needs CoreGraphics (a blend, text, a shape, a part-transparent fill,
    /// which replaces what is under it: CGBlendMode.copy).
    private func composedParts(_ node: [String: Any]) throws -> [ComposedPart]? {
        guard let ops = node["ops"] as? [[String: Any]], ops.count <= composeMaximumOps else { return nil }
        let size = try numbers(node["size"])
        guard size.count == 2, size[0] * size[1] >= composeMinimumPixels else { return nil }
        var parts: [ComposedPart] = []
        for op in ops {
            guard op["blend"] == nil, let kind = op["kind"] as? String else { return nil }
            let clip = try op["clip"].map { try rect($0) }
            switch kind {
            case "fill":
                let values = try numbers(op["color"]).map { $0 / 255 }
                guard values.count == 4 else { return nil }
                var area = try rect(op["rect"])
                if let clip = clip { area = area.intersection(clip) }
                if values[3] == 0 && parts.isEmpty { continue }        // the clear a new surface starts with
                guard values[3] == 1, !area.isNull, let color = CGColor(colorSpace: space, components: values) else {
                    return nil
                }
                parts.append(ComposedPart(content: .color(color), frame: area, alpha: 1, clip: nil))
            case "blit":
                let at = try numbers(op["at"])
                guard at.count == 2, op["source"] is Int else { return nil }
                let alpha = Float((op["alpha"] as? NSNumber)?.doubleValue ?? 255) / 255
                let origin = CGPoint(x: at[0], y: at[1])
                if let scaled = scaling(op) {
                    let frame = CGRect(origin: origin, size: scaled.size)
                    parts.append(ComposedPart(content: try stretch(scaled.source), frame: frame, alpha: alpha,
                                              clip: cutting(clip, frame)))
                } else {
                    let child = try composedNode(op["source"] as! Int)
                    let frame = CGRect(origin: origin, size: child.size)
                    parts.append(ComposedPart(content: .node(child), frame: frame, alpha: alpha, clip: cutting(clip, frame)))
                }
            case "scale":
                let frame = CGRect(x: 0, y: 0, width: size[0], height: size[1])
                parts.append(ComposedPart(content: try stretch(op), frame: frame, alpha: 1, clip: cutting(clip, frame)))
            default:
                return nil
            }
        }
        return parts
    }

    static func verify(_ fixture: [String: Any]) throws {
        guard let frame = fixture["frame"] as? [String: Any], let samples = fixture["samples"] as? [[String: Any]] else {
            throw CanvasError(message: "Missing authored drawing fixture")
        }
        let image = try NativeCanvas().render(frame)
        guard let data = image.dataProvider?.data, let bytes = CFDataGetBytePtr(data) else {
            throw CanvasError(message: "Cannot inspect native drawing pixels")
        }
        for sample in samples {
            guard let point = sample["at"] as? [Int], let expected = sample["rgba"] as? [Int], point.count == 2, expected.count == 4 else {
                throw CanvasError(message: "Invalid authored drawing sample")
            }
            let offset = point[1] * image.bytesPerRow + point[0] * 4
            let actual = (0..<4).map { Int(bytes[offset + $0]) }
            guard zip(actual, expected).allSatisfy({ abs($0 - $1) <= 1 }) else {
                throw CanvasError(message: "Native drawing mismatch at \(point): \(actual), expected \(expected)")
            }
        }
    }
}

/// A frame node as the GPU composites it: a picture drawn on the CPU, or parts Core Animation stacks.
final class ComposedNode {
    let id: Int
    let size: CGSize
    let picture: CGImage?
    let parts: [ComposedPart]
    init(id: Int, size: CGSize, picture: CGImage?, parts: [ComposedPart]) {
        self.id = id
        self.size = size
        self.picture = picture
        self.parts = parts
    }
}

struct ComposedPart {
    enum Content {
        case node(ComposedNode)                       // a blit of another node, at its own size
        case stretched(CGImage, smooth: Bool)         // a picture scaled to `frame`
        case scaled(ComposedNode, smooth: Bool)       // a composited node's layers scaled to `frame`
        case color(CGColor)                           // an opaque fill
    }
    let content: Content
    let frame: CGRect                                 // in the parent node's pixels
    let alpha: Float
    let clip: CGRect?                                 // in the parent node's pixels
}

struct ComposedFrame {
    let root: ComposedNode
    let released: [Int]
}

/// Keeps a CALayer per composed node and part, by the node's identifier and how many times this frame has used it
/// already (a layer has one parent), so an unchanged subtree keeps its layers and Core Animation its textures. Main
/// thread only. Layers not used by a frame are dropped.
final class LayerCompositor {
    private struct Key: Hashable {
        let id: Int, use: Int, part: Int
    }
    private var layers: [Key: CALayer] = [:]
    private static let still: [String: CAAction] = [
        "contents": NSNull(), "bounds": NSNull(), "position": NSNull(), "frame": NSNull(), "opacity": NSNull(),
        "backgroundColor": NSNull(), "sublayers": NSNull(), "transform": NSNull(), "hidden": NSNull()]

    func update(_ frame: ComposedFrame) -> CALayer {
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        defer { CATransaction.commit() }
        var uses: [Int: Int] = [:]
        var kept: [Key: CALayer] = [:]
        func take(_ key: Key) -> CALayer {
            if let layer = kept[key] { return layer }
            let layer = layers[key] ?? {
                let made = CALayer()
                made.actions = LayerCompositor.still
                made.anchorPoint = .zero
                return made
            }()
            kept[key] = layer
            return layer
        }
        func place(_ layer: CALayer, _ frame: CGRect) {
            if layer.position != frame.origin { layer.position = frame.origin }
            let bounds = CGRect(origin: .zero, size: frame.size)
            if layer.bounds != bounds { layer.bounds = bounds }
        }
        func build(_ node: ComposedNode) -> CALayer {
            let use = uses[node.id, default: 0]
            uses[node.id] = use + 1
            let layer = take(Key(id: node.id, use: use, part: -1))
            place(layer, CGRect(origin: layer.position, size: node.size))
            if let picture = node.picture {
                if (layer.contents as AnyObject?) !== picture { layer.contents = picture }
                if layer.sublayers != nil { layer.sublayers = nil }
                return layer
            }
            if layer.contents != nil { layer.contents = nil }
            var children: [CALayer] = []
            for (index, part) in node.parts.enumerated() {
                let piece: CALayer
                var natural: CGSize?            // a scaled node's own size: its layer is stretched by a transform
                switch part.content {
                case .node(let child):
                    piece = build(child)
                case .scaled(let child, _):
                    piece = build(child)
                    natural = child.size
                case .stretched(let picture, let smooth):
                    piece = take(Key(id: node.id, use: use, part: index))
                    if (piece.contents as AnyObject?) !== picture { piece.contents = picture }
                    let filter: CALayerContentsFilter = smooth ? .linear : .nearest
                    if piece.magnificationFilter != filter { piece.magnificationFilter = filter; piece.minificationFilter = filter }
                case .color(let color):
                    piece = take(Key(id: node.id, use: use, part: index))
                    piece.backgroundColor = color
                }
                if piece.opacity != part.alpha { piece.opacity = part.alpha }
                func fit(_ frame: CGRect) {
                    var transform = CATransform3DIdentity
                    if let natural = natural, natural.width > 0, natural.height > 0 {
                        place(piece, CGRect(origin: frame.origin, size: natural))
                        transform = CATransform3DMakeScale(frame.width / natural.width, frame.height / natural.height, 1)
                    } else {
                        place(piece, frame)
                    }
                    if !CATransform3DEqualToTransform(piece.transform, transform) { piece.transform = transform }
                }
                if let clip = part.clip {
                    let wrapper = take(Key(id: node.id, use: use, part: 1_000_000 + index))
                    if !wrapper.masksToBounds { wrapper.masksToBounds = true }
                    place(wrapper, clip)
                    fit(part.frame.offsetBy(dx: -clip.minX, dy: -clip.minY))
                    if !(wrapper.sublayers ?? []).elementsEqual([piece], by: ===) { wrapper.sublayers = [piece] }
                    children.append(wrapper)
                } else {
                    fit(part.frame)
                    children.append(piece)
                }
            }
            if !(layer.sublayers ?? []).elementsEqual(children, by: ===) { layer.sublayers = children }
            return layer
        }
        let root = build(frame.root)
        if root.position != .zero { root.position = .zero }
        layers = kept
        return root
    }

    func clear() { layers.removeAll() }
}

extension NativeCanvas {
    /// The simulator check: the fixture frame composited as the device composites it, sampled as the CPU's picture
    /// is (`verify`), every node composited that can be.
    static func verifyComposed(_ fixture: [String: Any]) throws {
        guard let frame = fixture["frame"] as? [String: Any], let samples = fixture["samples"] as? [[String: Any]] else {
            throw CanvasError(message: "Missing authored drawing fixture")
        }
        let canvas = NativeCanvas()
        canvas.composeMinimumPixels = 0
        let composed = try canvas.compose(frame)
        let root = LayerCompositor().update(composed)
        let width = Int(composed.root.size.width), height = Int(composed.root.size.height)
        guard width > 0, height > 0,
              let context = CGContext(data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: width * 4,
                                      space: CGColorSpace(name: CGColorSpace.sRGB)!,
                                      bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue),
              let data = context.data else {
            throw CanvasError(message: "Cannot inspect composited pixels")
        }
        context.translateBy(x: 0, y: CGFloat(height))      // layers draw top-down, as UIKit's contexts are
        context.scaleBy(x: 1, y: -1)
        root.render(in: context)
        let bytes = data.assumingMemoryBound(to: UInt8.self)
        for sample in samples {
            guard let point = sample["at"] as? [Int], let expected = sample["rgba"] as? [Int], point.count == 2, expected.count == 4 else {
                throw CanvasError(message: "Invalid authored drawing sample")
            }
            let offset = point[1] * context.bytesPerRow + point[0] * 4
            let actual = (0..<4).map { Int(bytes[offset + $0]) }
            guard zip(actual, expected).allSatisfy({ abs($0 - $1) <= 3 }) else {
                throw CanvasError(message: "Composited drawing mismatch at \(point): \(actual), expected \(expected)")
            }
        }
    }
}
