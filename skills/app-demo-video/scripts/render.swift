// Renders the still layers of the demo video (backgrounds, device bezels, title
// cards, captions, corner masks) as PNGs, using macOS's own text engine.
//
// Why not ffmpeg drawtext: Homebrew's ffmpeg has no drawtext, and drawtext
// without HarfBuzz shaping mis-stacks Thai vowel and tone marks anyway.
//
// Usage: swift render.swift <scene-spec.json>
// The spec is written by edit.py: {"fonts": [ttf paths], "scenes": [scene...]}
// Fonts in items may be PostScript names or .ttf/.otf paths.
// scene: {path, width, height, background?: {gradient: [hex, hex]} | {solid: hex},
//         items: [item...]}
// item:  {type: rect,  x, y, w, h, radius, color, shadow?: bool, stroke?: width (outline only)}
//        {type: text,  text, font, size, color, cx, cy}
//        {type: pill,  text, font, size, color, bg, cx, cy, padX, padY}
//        {type: image, path, x, y, w, h, radius?}
// Coordinates are pixels from the top-left.
import AppKit
import CoreText
import Foundation

func color(_ hex: String) -> NSColor {
    var s = hex.trimmingCharacters(in: .whitespaces)
    if s.hasPrefix("#") { s.removeFirst() }
    var v: UInt64 = 0
    Scanner(string: s).scanHexInt64(&v)
    let hasAlpha = s.count == 8
    let r = CGFloat((v >> (hasAlpha ? 24 : 16)) & 0xFF) / 255
    let g = CGFloat((v >> (hasAlpha ? 16 : 8)) & 0xFF) / 255
    let b = CGFloat((v >> (hasAlpha ? 8 : 0)) & 0xFF) / 255
    let a = hasAlpha ? CGFloat(v & 0xFF) / 255 : 1
    return NSColor(srgbRed: r, green: g, blue: b, alpha: a)
}

func num(_ any: Any?) -> CGFloat { CGFloat((any as? NSNumber)?.doubleValue ?? 0) }

let specPath = CommandLine.arguments[1]
let spec = try JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: specPath))) as! [String: Any]
for path in spec["fonts"] as? [String] ?? [] {
    CTFontManagerRegisterFontsForURL(URL(fileURLWithPath: path) as CFURL, .process, nil)
}

// A font may be given as a PostScript name or as a .ttf/.otf path; a path is
// registered and resolved to its PostScript name, so callers never need to know it.
var fontNameByPath: [String: String] = [:]
func font(_ name: String, _ size: CGFloat) -> NSFont {
    var resolved = name
    if name.hasSuffix(".ttf") || name.hasSuffix(".otf") {
        if let cached = fontNameByPath[name] {
            resolved = cached
        } else {
            let url = URL(fileURLWithPath: name) as CFURL
            CTFontManagerRegisterFontsForURL(url, .process, nil)
            if let descs = CTFontManagerCreateFontDescriptorsFromURL(url) as? [CTFontDescriptor],
               let first = descs.first,
               let ps = CTFontDescriptorCopyAttribute(first, kCTFontNameAttribute) as? String {
                resolved = ps
                fontNameByPath[name] = ps
            }
        }
    }
    // System font falls back per glyph (Thai, CJK, Arabic all render) when no font is given.
    return NSFont(name: resolved, size: size) ?? NSFont.systemFont(ofSize: size, weight: .semibold)
}

func attributed(_ item: [String: Any]) -> NSAttributedString {
    NSAttributedString(string: item["text"] as? String ?? "", attributes: [
        .font: font(item["font"] as? String ?? "", num(item["size"])),
        .foregroundColor: color(item["color"] as? String ?? "#000000"),
    ])
}

for scene in spec["scenes"] as! [[String: Any]] {
    let w = Int(num(scene["width"])), h = Int(num(scene["height"]))
    let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: w, pixelsHigh: h, bitsPerSample: 8,
                               samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                               colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    rep.size = NSSize(width: w, height: h)
    NSGraphicsContext.saveGraphicsState()
    let ctx = NSGraphicsContext(bitmapImageRep: rep)!
    NSGraphicsContext.current = ctx
    // Flip so the spec can speak top-left pixels like the video does.
    let cg = ctx.cgContext
    cg.translateBy(x: 0, y: CGFloat(h))
    cg.scaleBy(x: 1, y: -1)
    let flipped = NSGraphicsContext(cgContext: cg, flipped: true)
    NSGraphicsContext.current = flipped

    let full = NSRect(x: 0, y: 0, width: w, height: h)
    if let bg = scene["background"] as? [String: Any] {
        if let stops = bg["gradient"] as? [String] {
            NSGradient(colors: stops.map(color))!.draw(in: full, angle: 90)
        } else if let solid = bg["solid"] as? String {
            color(solid).setFill()
            full.fill()
        }
    }

    for item in scene["items"] as? [[String: Any]] ?? [] {
        switch item["type"] as? String {
        case "rect":
            let r = NSRect(x: num(item["x"]), y: num(item["y"]), width: num(item["w"]), height: num(item["h"]))
            let path = NSBezierPath(roundedRect: r, xRadius: num(item["radius"]), yRadius: num(item["radius"]))
            NSGraphicsContext.saveGraphicsState()
            if item["shadow"] as? Bool == true {
                let shadow = NSShadow()
                shadow.shadowColor = NSColor(white: 0, alpha: 0.28)
                shadow.shadowBlurRadius = 40
                shadow.shadowOffset = NSSize(width: 0, height: -18)
                shadow.set()
            }
            if let width = item["stroke"] as? NSNumber {
                color(item["color"] as? String ?? "#000000").setStroke()
                path.lineWidth = CGFloat(width.doubleValue)
                path.stroke()
            } else {
                color(item["color"] as? String ?? "#000000").setFill()
                path.fill()
            }
            NSGraphicsContext.restoreGraphicsState()
        case "text":
            let s = attributed(item)
            let size = s.size()
            s.draw(at: NSPoint(x: num(item["cx"]) - size.width / 2, y: num(item["cy"]) - size.height / 2))
        case "pill":
            let s = attributed(item)
            let size = s.size()
            let padX = num(item["padX"]), padY = num(item["padY"])
            let r = NSRect(x: num(item["cx"]) - size.width / 2 - padX, y: num(item["cy"]) - size.height / 2 - padY,
                           width: size.width + padX * 2, height: size.height + padY * 2)
            color(item["bg"] as? String ?? "#000000").setFill()
            NSBezierPath(roundedRect: r, xRadius: r.height / 2, yRadius: r.height / 2).fill()
            s.draw(at: NSPoint(x: r.minX + padX, y: r.minY + padY))
        case "image":
            if let img = NSImage(contentsOfFile: item["path"] as? String ?? "") {
                let r = NSRect(x: num(item["x"]), y: num(item["y"]), width: num(item["w"]), height: num(item["h"]))
                NSGraphicsContext.saveGraphicsState()
                NSBezierPath(roundedRect: r, xRadius: num(item["radius"]), yRadius: num(item["radius"])).addClip()
                img.draw(in: r, from: .zero, operation: .sourceOver, fraction: 1, respectFlipped: true, hints: nil)
                NSGraphicsContext.restoreGraphicsState()
            }
        default:
            break
        }
    }
    NSGraphicsContext.restoreGraphicsState()
    let png = rep.representation(using: .png, properties: [:])!
    try png.write(to: URL(fileURLWithPath: scene["path"] as! String))
}
