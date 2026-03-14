#!/usr/bin/env python3
"""
Generate icon.icns for Song Renamer.

Design: dark rounded square • vinyl record • waveform bars with purple→blue gradient • glow
"""
import os, math, subprocess
from PIL import Image, ImageDraw, ImageFilter

# App palette
BG     = (30,  30,  46)
PANEL  = (42,  42,  62)
RING   = (55,  55,  80)
PURPLE = (203, 166, 247)
BLUE   = (137, 180, 250)
GREEN  = (166, 227, 161)


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_color(c1, c2, t):
    return tuple(int(lerp(a, b, t)) for a, b in zip(c1, c2))


def make_icon(size: int) -> Image.Image:
    img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = cy = size / 2

    # ── Background: dark rounded square ──────────────────────────────────────
    corner = size * 0.22
    draw.rounded_rectangle([0, 0, size - 1, size - 1],
                           radius=corner, fill=(*BG, 255))

    # ── Vinyl circle ─────────────────────────────────────────────────────────
    vr = size * 0.40
    draw.ellipse([cx - vr, cy - vr, cx + vr, cy + vr],
                 fill=(*PANEL, 255))

    # Groove rings
    for frac in [0.88, 0.72, 0.55, 0.38]:
        rr = vr * frac
        lw = max(1, round(size * 0.0025))
        draw.ellipse([cx - rr, cy - rr, cx + rr, cy + rr],
                     outline=(*RING, 90), width=lw)

    # Center hole — accent colour
    hr = vr * 0.085
    draw.ellipse([cx - hr, cy - hr, cx + hr, cy + hr],
                 fill=(*PURPLE, 255))

    # ── Waveform bars ─────────────────────────────────────────────────────────
    # Heights create a realistic-looking audio waveform
    n       = 11
    heights = [0.38, 0.60, 0.76, 0.88, 0.96, 1.00,
               0.96, 0.88, 0.76, 0.60, 0.38]

    span   = size * 0.70
    bar_w  = span / (n * 1.55)
    gap    = bar_w * 0.55
    x0     = cx - span / 2 + bar_w / 2
    max_h  = size * 0.56
    brad   = bar_w * 0.45

    # Pass 1 — blurred glow
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gd   = ImageDraw.Draw(glow)
    for i, h in enumerate(heights):
        t   = i / (n - 1)
        col = lerp_color(PURPLE, BLUE, t)
        x   = x0 + i * (bar_w + gap)
        bh  = max_h * h
        gd.rounded_rectangle(
            [x - bar_w / 2, cy - bh / 2, x + bar_w / 2, cy + bh / 2],
            radius=brad, fill=(*col, 140))
    blur_r = max(1, size * 0.025)
    glow   = glow.filter(ImageFilter.GaussianBlur(radius=blur_r))
    img    = Image.alpha_composite(img, glow)

    # Pass 2 — sharp bars
    draw2 = ImageDraw.Draw(img)
    for i, h in enumerate(heights):
        t   = i / (n - 1)
        col = lerp_color(PURPLE, BLUE, t)
        x   = x0 + i * (bar_w + gap)
        bh  = max_h * h
        draw2.rounded_rectangle(
            [x - bar_w / 2, cy - bh / 2, x + bar_w / 2, cy + bh / 2],
            radius=brad, fill=(*col, 245))

    # ── Subtle inner highlight (top edge of bg) ───────────────────────────────
    if size >= 128:
        hi = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        hd = ImageDraw.Draw(hi)
        hd.rounded_rectangle([0, 0, size - 1, size * 0.5],
                             radius=corner, fill=(255, 255, 255, 12))
        img = Image.alpha_composite(img, hi)

    return img


def build_icns(out_dir: str) -> str:
    iconset = os.path.join(out_dir, "icon.iconset")
    os.makedirs(iconset, exist_ok=True)

    specs = [
        ("icon_16x16.png",       16),
        ("icon_16x16@2x.png",    32),
        ("icon_32x32.png",       32),
        ("icon_32x32@2x.png",    64),
        ("icon_128x128.png",    128),
        ("icon_128x128@2x.png", 256),
        ("icon_256x256.png",    256),
        ("icon_256x256@2x.png", 512),
        ("icon_512x512.png",    512),
        ("icon_512x512@2x.png", 1024),
    ]

    print("Rendering icon sizes...")
    for fname, sz in specs:
        icon = make_icon(sz)
        icon.save(os.path.join(iconset, fname))
        print(f"  {sz:>5}px  {fname}")

    icns_path = os.path.join(out_dir, "icon.icns")
    subprocess.run(["iconutil", "-c", "icns", iconset, "-o", icns_path], check=True)
    print(f"\nSaved: {icns_path}")

    # Also save a 1024px preview PNG
    preview = os.path.join(out_dir, "icon_preview.png")
    make_icon(1024).save(preview)
    print(f"Preview: {preview}")

    return icns_path


if __name__ == "__main__":
    build_icns(os.path.dirname(os.path.abspath(__file__)))
