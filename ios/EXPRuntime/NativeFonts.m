#import "NativeFonts.h"
#import <UIKit/UIKit.h>
#import <CoreText/CoreText.h>
#import <ImageIO/ImageIO.h>

static CTFontRef makeFont(NSDictionary *request, BOOL *nativeFace) {
    CGFloat size = [request[@"size"] doubleValue];
    NSString *encoded = request[@"data"];
    if (encoded) {
        NSData *data = [[NSData alloc] initWithBase64EncodedString:encoded options:0];
        CGDataProviderRef provider = CGDataProviderCreateWithCFData((__bridge CFDataRef)data);
        CGFontRef graphics = CGFontCreateWithDataProvider(provider);
        CGDataProviderRelease(provider);
        if (!graphics) return NULL;
        CTFontRef font = CTFontCreateWithGraphicsFont(graphics, size, NULL, NULL);
        CGFontRelease(graphics);
        *nativeFace = YES;
        return font;
    }
    NSString *face = request[@"face"];
    if (![face isKindOfClass:NSString.class]) face = nil;
    face = [face stringByReplacingOccurrencesOfString:@"_" withString:@"-"];
    if ([face isEqual:@"VerdanaBoldItalic"]) face = @"Verdana-BoldItalic";
    UIFont *font = face ? [UIFont fontWithName:face size:size] : nil;
    if (!font) {
        *nativeFace = NO;
        CTFontRef system = CTFontCreateUIFontForLanguage(kCTFontUIFontSystem, size, NULL);
        CTFontSymbolicTraits traits = 0;
        if ([face containsString:@"Bold"]) traits |= kCTFontBoldTrait;
        if ([face containsString:@"Italic"]) traits |= kCTFontItalicTrait;
        if (traits) {
            CTFontRef styled = CTFontCreateCopyWithSymbolicTraits(system, size, NULL, traits, traits);
            if (styled) { CFRelease(system); system = styled; }
        }
        return system;
    }
    *nativeFace = YES;
    return CTFontCreateWithName((__bridge CFStringRef)font.fontName, size, NULL);
}

static CGContextRef bitmap(size_t width, size_t height) {
    CGColorSpaceRef space = CGColorSpaceCreateWithName(kCGColorSpaceSRGB);
    CGContextRef context = CGBitmapContextCreate(NULL, width, height, 8, width * 4, space,
                                                kCGImageAlphaPremultipliedLast | kCGBitmapByteOrder32Big);
    CGColorSpaceRelease(space);
    return context;
}

static NSString *png(CGContextRef context) {
    CGImageRef image = CGBitmapContextCreateImage(context);
    NSMutableData *data = [NSMutableData data];
    CGImageDestinationRef destination = CGImageDestinationCreateWithData((__bridge CFMutableDataRef)data,
                                                                        CFSTR("public.png"), 1, NULL);
    CGImageDestinationAddImage(destination, image, NULL);
    BOOL success = CGImageDestinationFinalize(destination);
    CFRelease(destination);
    CGImageRelease(image);
    return success ? [data base64EncodedStringWithOptions:0] : nil;
}

static CGColorRef color(NSArray *values) {
    if (values.count != 4) values = @[@255, @255, @255, @255];
    CGFloat components[4];
    for (int i = 0; i < 4; ++i) components[i] = [values[i] doubleValue] / 255.;
    CGColorSpaceRef space = CGColorSpaceCreateWithName(kCGColorSpaceSRGB);
    CGColorRef result = CGColorCreate(space, components);
    CGColorSpaceRelease(space);
    return result;
}

NSString *EXPFontRequest(NSString *json, NSError **error) {
    NSDictionary *request = [NSJSONSerialization JSONObjectWithData:[json dataUsingEncoding:NSUTF8StringEncoding]
                                                           options:0 error:error];
    if (!request) return nil;
    if ([request[@"operation"] isEqual:@"register"]) {
        // A font file's bytes (the HD app's Pajama Hip, a library's fonts/ folder) registered for this process, so
        // later requests name it by its PostScript name instead of sending the bytes again.
        NSData *data = [[NSData alloc] initWithBase64EncodedString:request[@"data"] ?: @"" options:0];
        CGDataProviderRef provider = data ? CGDataProviderCreateWithCFData((__bridge CFDataRef)data) : NULL;
        CGFontRef graphics = provider ? CGFontCreateWithDataProvider(provider) : NULL;
        if (provider) CGDataProviderRelease(provider);
        if (!graphics) {
            if (error) *error = [NSError errorWithDomain:@"org.expruntime.font" code:1
                                              userInfo:@{NSLocalizedDescriptionKey: @"Cannot decode supplied font"}];
            return nil;
        }
        CFErrorRef failure = NULL;
        if (!CTFontManagerRegisterGraphicsFont(graphics, &failure) && failure) {
            CFIndex code = CFErrorGetCode(failure);
            CFRelease(failure);
            // Registered by this process already, or a face of the same PostScript name is installed (iOS ships
            // Arial Rounded MT Bold, which a library's fonts/ folder also supplies): either way the name resolves.
            if (code != kCTFontManagerErrorAlreadyRegistered && code != kCTFontManagerErrorDuplicatedName) {
                CGFontRelease(graphics);
                NSString *message = [NSString stringWithFormat:@"Cannot register supplied font (Core Text error %ld)",
                                     (long)code];
                if (error) *error = [NSError errorWithDomain:@"org.expruntime.font" code:3
                                                  userInfo:@{NSLocalizedDescriptionKey: message}];
                return nil;
            }
        }
        NSString *name = CFBridgingRelease(CGFontCopyPostScriptName(graphics));
        CGFontRelease(graphics);
        NSData *reply = [NSJSONSerialization dataWithJSONObject:@{@"face": name ?: @""} options:0 error:error];
        return reply ? [[NSString alloc] initWithData:reply encoding:NSUTF8StringEncoding] : nil;
    }
    BOOL nativeFace = NO;
    CTFontRef font = makeFont(request, &nativeFace);
    if (!font) {
        if (error) *error = [NSError errorWithDomain:@"org.expruntime.font" code:1
                                          userInfo:@{NSLocalizedDescriptionKey: @"Cannot decode supplied font"}];
        return nil;
    }
    NSMutableDictionary *result = [NSMutableDictionary dictionary];
    CGColorRef foreground = color(request[@"color"]);
    if ([request[@"operation"] isEqual:@"atlas"]) {
        int size = [request[@"size"] intValue];
        CGFloat stroke = [request[@"stroke"] doubleValue];
        int padding = ceil(stroke);
        int cell = (size + padding * 2) * 3, edge = cell * 16;
        CGContextRef context = bitmap(edge, edge);
        NSMutableArray *glyphs = [NSMutableArray array];
        for (UniChar code = 32; code < 256; ++code) {
            if (code >= 127 && code < 160) continue;
            CGGlyph glyph;
            CTFontGetGlyphsForCharacters(font, &code, &glyph, 1);
            CGRect bounds;
            CGSize advance;
            CTFontGetBoundingRectsForGlyphs(font, kCTFontOrientationHorizontal, &glyph, &bounds, 1);
            CTFontGetAdvancesForGlyphs(font, kCTFontOrientationHorizontal, &glyph, &advance, 1);
            int left = 0, top = 0, width = 0, height = 0;
            if (!CGRectIsEmpty(bounds)) {
                left = floor(CGRectGetMinX(bounds)) - padding;
                top = -ceil(CGRectGetMaxY(bounds)) - padding;
                width = ceil(CGRectGetMaxX(bounds)) + padding - left;
                height = -floor(CGRectGetMinY(bounds)) + padding - top;
            }
            if (width > cell || height > cell) {
                CGColorRelease(foreground); CFRelease(font); CGContextRelease(context);
                if (error) *error = [NSError errorWithDomain:@"org.expruntime.font" code:2
                                                  userInfo:@{NSLocalizedDescriptionKey: @"Font glyph exceeds atlas cell"}];
                return nil;
            }
            int x = code % 16 * cell, y = code / 16 * cell;
            CGPoint origin = CGPointMake(x - left, edge - y + top);
            if (stroke) {
                CGContextSetRGBStrokeColor(context, 1, 1, 1, 1);
                CGContextSetLineWidth(context, stroke * 2);
                CGContextSetLineJoin(context, kCGLineJoinRound);
                CGContextSetTextDrawingMode(context, kCGTextStroke);
                CTFontDrawGlyphs(font, &glyph, &origin, 1, context);
            }
            CGContextSetFillColorWithColor(context, foreground);
            CGContextSetTextDrawingMode(context, kCGTextFill);
            CTFontDrawGlyphs(font, &glyph, &origin, 1, context);
            [glyphs addObject:@[@(code), @(x), @(y), @(width), @(height), @(left), @(size + top), @(advance.width)]];
        }
        result[@"glyphs"] = glyphs;
        result[@"cap"] = @(CTFontGetCapHeight(font));
        result[@"descent"] = @(CTFontGetDescent(font));
        result[@"native_face"] = @(nativeFace);
        result[@"png"] = png(context);
        CGContextRelease(context);
    } else if ([request[@"operation"] isEqual:@"glyphs"]) {
        // pygame's Font.metrics: per character (min x, max x, min y, max y, advance), y up from the baseline.
        NSString *text = request[@"text"] ?: @"";
        NSMutableArray *glyphs = [NSMutableArray array];
        for (NSUInteger i = 0; i < text.length; ++i) {
            UniChar code = [text characterAtIndex:i];
            CGGlyph glyph = 0;
            CTFontGetGlyphsForCharacters(font, &code, &glyph, 1);
            CGRect bounds;
            CGSize advance;
            CTFontGetBoundingRectsForGlyphs(font, kCTFontOrientationHorizontal, &glyph, &bounds, 1);
            CTFontGetAdvancesForGlyphs(font, kCTFontOrientationHorizontal, &glyph, &advance, 1);
            if (CGRectIsEmpty(bounds)) bounds = CGRectZero;
            [glyphs addObject:@[@(floor(CGRectGetMinX(bounds))), @(ceil(CGRectGetMaxX(bounds))),
                                @(floor(CGRectGetMinY(bounds))), @(ceil(CGRectGetMaxY(bounds))),
                                @(round(advance.width))]];
        }
        result[@"glyphs"] = glyphs;
    } else if ([request[@"operation"] isEqual:@"stroked"]) {
        // vector_text's fill-and-stroke glyph for a system face (no outline file for Python to read): each layer the
        // glyph filled and/or stroked with a mitered line of `width` pixels (`CSFont::setStroke`, kCGTextFillStroke),
        // drawn in order. `left`/`top` place the image from the pen on the baseline, y down.
        NSString *text = request[@"text"] ?: @"";
        NSArray *layers = request[@"layers"] ?: @[];
        UniChar code = text.length ? [text characterAtIndex:0] : ' ';
        CGGlyph glyph = 0;
        CTFontGetGlyphsForCharacters(font, &code, &glyph, 1);
        CGRect bounds;
        CTFontGetBoundingRectsForGlyphs(font, kCTFontOrientationHorizontal, &glyph, &bounds, 1);
        if (CGRectIsEmpty(bounds)) bounds = CGRectZero;
        CGFloat widest = 0;
        for (NSDictionary *layer in layers) widest = MAX(widest, [layer[@"width"] doubleValue]);
        int padding = (int)ceil(widest / 2) + 2;
        int left = (int)floor(CGRectGetMinX(bounds)) - padding, top = -(int)ceil(CGRectGetMaxY(bounds)) - padding;
        int w = MAX(1, (int)ceil(CGRectGetMaxX(bounds)) + padding - left);
        int h = MAX(1, -(int)floor(CGRectGetMinY(bounds)) + padding - top);
        CGContextRef context = bitmap(w, h);
        CGPoint origin = CGPointMake(-left, h + top);
        CGContextSetLineJoin(context, kCGLineJoinMiter);
        for (NSDictionary *layer in layers) {
            CGColorRef paint = color(layer[@"color"]);
            CGFloat width = [layer[@"width"] doubleValue];
            BOOL fill = [layer[@"fill"] boolValue];
            CGContextSetFillColorWithColor(context, paint);
            CGContextSetStrokeColorWithColor(context, paint);
            CGContextSetLineWidth(context, width);
            CGContextSetTextDrawingMode(context, width > 0 ? (fill ? kCGTextFillStroke : kCGTextStroke) : kCGTextFill);
            CTFontDrawGlyphs(font, &glyph, &origin, 1, context);
            CGColorRelease(paint);
        }
        result[@"left"] = @(left);
        result[@"top"] = @(top);
        result[@"png"] = png(context);
        CGContextRelease(context);
    } else {
        NSAttributedString *text = [[NSAttributedString alloc] initWithString:request[@"text"] ?: @""
            attributes:@{(__bridge NSString *)kCTFontAttributeName: (__bridge id)font,
                         (__bridge NSString *)kCTForegroundColorAttributeName: (__bridge id)foreground}];
        CTLineRef line = CTLineCreateWithAttributedString((__bridge CFAttributedStringRef)text);
        CGFloat ascent = CTFontGetAscent(font), descent = CTFontGetDescent(font);
        CGFloat width = CTLineGetTypographicBounds(line, NULL, NULL, NULL);
        // `left`: the pen starts this far in, so a first glyph whose ink begins left of it (a negative bearing) is
        // kept whole, as SDL_ttf's images start at the leftmost ink.
        CGFloat left = MAX(0, [request[@"left"] doubleValue]);
        result[@"width"] = @(ceil(width + left));
        result[@"height"] = @(ceil(ascent + descent + CTFontGetLeading(font)));
        result[@"ascent"] = @(ceil(ascent));
        result[@"descent"] = @(ceil(descent));
        // Unrounded, for vector_text's cap height and descent of a system face (no font file to read tables from).
        result[@"cap"] = @(CTFontGetCapHeight(font));
        result[@"descender"] = @(descent);
        if (![request[@"measure"] boolValue]) {
            int w = MAX(1, [result[@"width"] intValue]), h = MAX(1, [result[@"height"] intValue]);
            CGContextRef context = bitmap(w, h);
            CGContextSetTextPosition(context, left, h - ceil(ascent));
            CTLineDraw(line, context);
            result[@"png"] = png(context);
            CGContextRelease(context);
        }
        CFRelease(line);
    }
    CGColorRelease(foreground);
    CFRelease(font);
    NSData *data = [NSJSONSerialization dataWithJSONObject:result options:0 error:error];
    return data ? [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding] : nil;
}
