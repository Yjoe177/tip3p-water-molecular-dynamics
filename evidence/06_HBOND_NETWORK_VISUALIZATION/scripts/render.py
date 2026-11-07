"""Presentation repair renderer: H-bond dashes connect donor-H to acceptor-O.

Identical visual style/scale policy as the original branch (white bg, sticks,
O red, H grey40, marine dashes, ray-traced 2000x1500 dpi 300), with two
presentation changes:
  - dashes run donor-H -> acceptor-O (analysis/hbonds_<tag>_HtoO.txt)
  - tighter framing of the cluster (zoom buffer 0.1, complete=1) for better
    canvas utilization; identical policy for both panels.

Run with the original branch venv:
  ../15_HBOND_NETWORK_VISUALIZATION_20260922_104453/venv/Scripts/python.exe scripts/render.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path

_DLL_DIR = Path(__file__).resolve().parent.parent.parent / "15_HBOND_NETWORK_VISUALIZATION_20260922_104453" / "venv" / "pymol_dlls"
os.add_dll_directory(str(_DLL_DIR))

import pymol
from pymol import cmd

HERE = Path(__file__).resolve().parent.parent
RENDERS = HERE / "renders"
RENDERS.mkdir(exist_ok=True)

CENTRAL_O_SERIAL = 1


def render(tag: str, zoom: bool = False) -> str:
    cmd.delete("all")
    obj = f"cluster_{tag}"
    cmd.load(str(HERE / "analysis" / f"cluster_{tag}.pdb"), obj)
    cmd.bg_color("white")
    cmd.hide("everything")
    cmd.show("sticks", obj)
    cmd.color("red", f"{obj} and elem O")
    cmd.color("grey40", f"{obj} and elem H")
    cmd.set("stick_radius", 0.15, obj)
    cmd.set("stick_quality", 24)
    cmd.set("ray_shadows", 0)
    cmd.set("antialias", 2)
    cmd.set("ambient", 0.45)
    cmd.set("specular", 0.25)

    pairs = []
    for line in (HERE / "analysis" / f"hbonds_{tag}_HtoO.txt").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            a, b = line.split()
            pairs.append((int(a), int(b)))

    dname = f"hbonds_{tag}"
    for a, b in pairs:
        cmd.distance(dname, f"{obj} and id {a}", f"{obj} and id {b}", mode=0)
    cmd.hide("labels", dname)
    cmd.color("marine", dname)
    cmd.set("dash_width", 5, dname)
    cmd.set("dash_radius", 0.07, dname)
    cmd.set("dash_color", "marine", dname)

    # Consistent orientation policy for both panels: orient whole cluster,
    # fixed rotation, center on central O, tight zoom.
    if zoom:
        cmd.orient(f"{obj} and (id {CENTRAL_O_SERIAL} around 4.5)")
    else:
        cmd.orient(obj)
    cmd.turn("x", 20)
    cmd.turn("y", -15)
    cmd.center(f"{obj} and id {CENTRAL_O_SERIAL}")
    if zoom:
        cmd.zoom(f"{obj} and (id {CENTRAL_O_SERIAL} around 4.5)", buffer=1.5, complete=1)
    else:
        cmd.zoom(obj, buffer=0.1)

    out = RENDERS / (f"hbond_network_{tag}_zoom.png" if zoom else f"hbond_network_{tag}.png")
    cmd.ray(2000, 1500)
    cmd.png(str(out), dpi=300)
    print(f"wrote {out}")
    return str(out)


def main() -> None:
    pymol.finish_launching(["pymol", "-cq"])
    made = []
    for tag in ("300K", "273K"):
        made.append(render(tag))
        made.append(render(tag, zoom=True))
    (RENDERS / "render_manifest.json").write_text(json.dumps({"pngs": made}, indent=2) + "\n")
    cmd.quit()


if __name__ == "__main__":
    main()
