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
        guard let id = op["source"] as? Int, let image = images[id] else {
            throw CanvasError(message: "Missing drawing source")
        }
        return image
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
            case "blit":
                let source = try image(op)
                let at = try numbers(op["at"])
                guard at.count == 2 else { throw CanvasError(message: "Invalid image position") }
                context.setAlpha(CGFloat((op["alpha"] as? NSNumber)?.doubleValue ?? 255) / 255)
                drawImage(source, CGRect(x: at[0], y: at[1], width: CGFloat(source.width), height: CGFloat(source.height)), context)
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

    func render(_ frame: [String: Any]) throws -> CGImage {
        guard let nodes = frame["nodes"] as? [[String: Any]], let root = frame["root"] as? Int else {
            throw CanvasError(message: "Invalid drawing frame")
        }
        for node in nodes {
            guard let id = node["id"] as? Int else { throw CanvasError(message: "Invalid drawing identifier") }
            images[id] = try renderNode(node)
        }
        for id in frame["release"] as? [Int] ?? [] {
            images.removeValue(forKey: id)
            textures.removeValue(forKey: id)
        }
        guard let result = images[root] else { throw CanvasError(message: "Missing drawing frame") }
        return result
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
