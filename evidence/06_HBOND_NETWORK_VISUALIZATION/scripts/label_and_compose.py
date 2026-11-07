"""Caption + compose step for the presentation repair.

Caption: "<T> — frame <i>, t = <t> ps — Whole-frame H-bonds: <N>"
Footer on every panel and the side-by-side:
"Illustrative local snapshots; quantitative conclusions use all 100 frames."
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent.parent
RENDERS = HERE / "renders"
FONT_PATH = "C:/Windows/Fonts/arial.ttf"
FOOTER = "Illustrative local snapshots; quantitative conclusions use all 100 frames."


def caption_for(tag: str, sel: dict) -> str:
    b = sel["branches"][tag]
    return (f"{tag.replace('K', ' K')} — frame {b['frame_index']}, "
            f"t = {b['time_ps']:.3f} ps — "
            f"Whole-frame H-bonds: {b['recomputed_hbond_count']}")


def frame(img: Image.Image, caption: str, bar_h: int = 90, foot_h: int = 64) -> Image.Image:
    w, h = img.size
    out = Image.new("RGB", (w, h + bar_h + foot_h), "white")
    out.paste(img, (0, bar_h))
    d = ImageDraw.Draw(out)
    try:
        font = ImageFont.truetype(FONT_PATH, 44)
        ffont = ImageFont.truetype(FONT_PATH, 30)
    except OSError:
        font = ffont = ImageFont.load_default()
    d.rectangle([0, 0, w, bar_h], fill="white", outline="black", width=2)
    bbox = d.textbbox((0, 0), caption, font=font)
    d.text(((w - (bbox[2] - bbox[0])) / 2, (bar_h - (bbox[3] - bbox[1])) / 2 - bbox[1]),
           caption, fill="black", font=font)
    y0 = bar_h + h
    d.rectangle([0, y0, w, y0 + foot_h], fill="white", outline="black", width=2)
    bbox = d.textbbox((0, 0), FOOTER, font=ffont)
    d.text(((w - (bbox[2] - bbox[0])) / 2, y0 + (foot_h - (bbox[3] - bbox[1])) / 2 - bbox[1]),
           FOOTER, fill="black", font=ffont)
    return out


def main() -> None:
    sel = json.loads((HERE / "analysis" / "selection_results.json").read_text())
    labeled = {}
    for tag in ("300K", "273K"):
        img = Image.open(RENDERS / f"hbond_network_{tag}.png").convert("RGB")
        lab = frame(img, caption_for(tag, sel))
        labeled[tag] = lab
        lab.save(RENDERS / f"hbond_network_{tag}_labeled.png")
        print(f"wrote labeled panel {tag}: {lab.size}")
    a, b = labeled["300K"], labeled["273K"]
    div = 8
    comp = Image.new("RGB", (a.size[0] + b.size[0] + div, a.size[1]), "white")
    comp.paste(a, (0, 0))
    comp.paste(b, (a.size[0] + div, 0))
    d = ImageDraw.Draw(comp)
    d.rectangle([a.size[0], 0, a.size[0] + div, a.size[1]], fill="black")
    comp.save(RENDERS / "hbond_network_comparison_sidebyside.png")
    print(f"wrote comparison: {comp.size}")


if __name__ == "__main__":
    main()
