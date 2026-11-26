"""Turn one mascot image into animation-ready parts.

Usage:
  python pipeline/import_mascot.py channels/swify

Reads  <channel>/mascot.json  (source image + cut settings) and the source image.
Writes <channel>/mascot/body.png, wing_l.png, wing_r.png (or just card.png in card mode),
       <channel>/mascot/rig.json (part files, pivots, eyes, size) and preview.jpg (rest + flap poses).

Cut-out: the mascot is separated from a pale or plain background by colour saturation, keeping the largest
shape, so baked-in circles, gradients and text bubbles are dropped. Works best on a character that is clearly
more colourful than its background; otherwise supply a PNG that already has a transparent background.

Parts (optional "parts" block in mascot.json): the body is an ellipse (cx, cy, rx, ry in source pixels) plus
everything below "band_bottom"; whatever lies outside it above that line becomes the left or right wing (or arm).
A thin ring of overlap at the shoulder keeps the seam closed when a wing rotates. No "parts" block = card mode:
the whole image moves as one piece.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage as ndi


def cut_out(img: Image.Image, sat_min: float) -> np.ndarray:
    """RGBA array with the mascot kept and the background made transparent."""
    rgb = np.asarray(img.convert("RGB")).astype(np.float32) / 255
    if img.mode == "RGBA" and np.asarray(img)[..., 3].min() < 250:  # already transparent: keep its alpha
        return np.asarray(img).copy()
    mx, mn = rgb.max(2), rgb.min(2)
    m = (mx - mn) / (mx + 1e-6) > sat_min
    m = ndi.binary_opening(m, iterations=1)
    lab, n = ndi.label(m)
    if n == 0:
        raise SystemExit("No mascot found: try a lower cut.saturation or a transparent PNG.")
    sizes = ndi.sum(m, lab, range(1, n + 1))
    m = lab == (int(np.argmax(sizes)) + 1)
    m = ndi.binary_fill_holes(ndi.binary_closing(m, iterations=3))
    m = ndi.binary_erosion(m, iterations=1)  # drop the pale fringe left by the old background
    alpha = Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.0))
    out = np.asarray(img.convert("RGBA")).copy()
    out[..., 3] = np.asarray(alpha)
    return out


def main(channel: Path):
    cfg = json.loads((channel / "mascot.json").read_text(encoding="utf-8"))
    src = Image.open(channel / cfg["source"])
    rgba = cut_out(src, cfg.get("cut", {}).get("saturation", 0.30))
    H, W = rgba.shape[:2]
    ys, xs = np.where(rgba[..., 3] > 128)
    pad = cfg.get("cut", {}).get("pad", 40)
    x0, y0 = int(max(0, xs.min() - pad)), int(max(0, ys.min() - pad))
    x1, y1 = int(min(W, xs.max() + pad)), int(min(H, ys.max() + pad))

    out = channel / "mascot"
    out.mkdir(exist_ok=True)
    crop = lambda a: Image.fromarray(a[y0:y1, x0:x1])
    rig = {"name": cfg["name"], "width": int(x1 - x0), "height": int(y1 - y0), "mode": "card", "parts": []}

    parts = cfg.get("parts")
    if parts:
        yy, xx = np.mgrid[0:H, 0:W]
        b = parts["body"]

        def ell(rx, ry):
            return ((xx - b["cx"]) / rx) ** 2 + ((yy - b["cy"]) / ry) ** 2 <= 1

        band = yy < parts["band_bottom"]
        inside = ell(b["rx"], b["ry"])
        ring = inside & ~ell(b["rx"] - 16, b["ry"] - 10) & (yy > parts["ring_y"][0]) & (yy < parts["ring_y"][1])
        sel = {
            "body": ~band | inside,
            "wing_l": band & (xx < b["cx"]) & (~inside | ring),
            "wing_r": band & (xx >= b["cx"]) & (~inside | ring),
        }
        for name, s in sel.items():
            a = rgba.copy()
            a[..., 3] = np.where(s, a[..., 3], 0)
            crop(a).save(out / f"{name}.png")
        rig["mode"] = "parts"
        rig["parts"] = [
            {"name": "wing_l", "file": "wing_l.png", "pivot": [parts["pivots"]["wing_l"][0] - x0, parts["pivots"]["wing_l"][1] - y0], "z": 0},
            {"name": "wing_r", "file": "wing_r.png", "pivot": [parts["pivots"]["wing_r"][0] - x0, parts["pivots"]["wing_r"][1] - y0], "z": 0},
            {"name": "body", "file": "body.png", "pivot": [b["cx"] - x0, parts["band_bottom"] - y0], "z": 1},
        ]
    else:
        crop(rgba).save(out / "card.png")
        rig["parts"] = [{"name": "card", "file": "card.png", "pivot": [(x1 - x0) / 2, y1 - y0], "z": 1}]

    face = cfg.get("face", {})
    rig["eyes"] = [{"cx": e["cx"] - x0, "cy": e["cy"] - y0, "rx": e["rx"], "ry": e["ry"]} for e in face.get("eyes", [])]
    rig["lid_color"] = face.get("lid_color", "#000000")
    rig["lash_color"] = face.get("lash_color", "#3a2216")
    (out / "rig.json").write_text(json.dumps(rig, indent=2), encoding="utf-8")

    # preview: rest and both flap extremes on the channel background
    bg = tuple(int(cfg.get("preview_bg", "#FBF3E6")[i:i + 2], 16) for i in (1, 3, 5)) + (255,)
    tiles = []
    for ang in (-10, 0, 10):
        c = Image.new("RGBA", (rig["width"], rig["height"]), bg)
        for p in sorted(rig["parts"], key=lambda p: p["z"]):
            im = Image.open(out / p["file"])
            a = ang if p["name"] == "wing_r" else -ang if p["name"] == "wing_l" else 0
            c.alpha_composite(im.rotate(a, center=tuple(p["pivot"]), resample=Image.BICUBIC))
        tiles.append(c.convert("RGB"))
    sheet = Image.new("RGB", (rig["width"] * 3, rig["height"]))
    for i, t in enumerate(tiles):
        sheet.paste(t, (i * rig["width"], 0))
    sheet.save(out / "preview.jpg", quality=90)
    rest = Image.new("RGBA", (rig["width"], rig["height"]), (0, 0, 0, 0))
    for p in sorted(rig["parts"], key=lambda p: p["z"]):
        rest.alpha_composite(Image.open(out / p["file"]))
    rest.crop(rest.getbbox()).save(out / "avatar.png")
    print(f"{cfg['name']}: {rig['mode']} mode, {len(rig['parts'])} part(s), {rig['width']}x{rig['height']} -> {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
