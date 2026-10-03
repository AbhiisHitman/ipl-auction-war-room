"""Publish per-team downloads for the web app (web/public/downloads/).

For each franchise:
  deck .pptx, deck .pdf (rendered by Microsoft PowerPoint on macOS),
  slide images for the in-site viewer, the team's Excel Solver workbook,
  the franchise P&L model and the team's recommendations CSV.
Writes web/public/data/downloads.json (manifest the app reads).

    python -m src.publish_downloads            # render PDFs with PowerPoint
    python -m src.publish_downloads --no-pdf   # reuse existing PDFs
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess

import pandas as pd
import pymupdf

from .config import EXCEL_DIR, OUTPUTS_DIR, PROCESSED_DIR, ROOT
from .teams import active_codes

DECK_DIR = OUTPUTS_DIR / "deck"
WEB_DL = ROOT / "web" / "public" / "downloads"
MANIFEST = ROOT / "web" / "public" / "data" / "downloads.json"


def render_pdfs(teams: list[str]) -> None:
    """Ask PowerPoint to save each deck as PDF (same renderer the client uses)."""
    lines = ['tell application "Microsoft PowerPoint"']
    for t in teams:
        src = DECK_DIR / f"auction_war_room_{t}.pptx"
        dst = DECK_DIR / f"auction_war_room_{t}.pdf"
        lines += [f'  open POSIX file "{src}"', "  delay 2",
                  f'  save active presentation in POSIX file "{dst}" as save as PDF',
                  "  close active presentation saving no"]
    lines.append("end tell")
    subprocess.run(["osascript", "-e", "\n".join(lines)], check=True)


def slide_images(pdf, out_dir, dpi: int = 120) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("slide-*.jpg"):
        old.unlink()
    doc = pymupdf.open(pdf)
    for i, page in enumerate(doc, start=1):
        page.get_pixmap(dpi=dpi).save(out_dir / f"slide-{i:02d}.jpg", jpg_quality=82)
    return len(doc)


def main(render: bool = True) -> None:
    teams = active_codes()
    if render:
        render_pdfs(teams)
    recs = pd.read_csv(PROCESSED_DIR / "recommendations.csv")
    manifest = {}
    for t in teams:
        d = WEB_DL / t
        d.mkdir(parents=True, exist_ok=True)
        pptx = DECK_DIR / f"auction_war_room_{t}.pptx"
        pdf = DECK_DIR / f"auction_war_room_{t}.pdf"
        shutil.copy2(pptx, d / pptx.name)
        files = [{"label": "Strategy deck", "type": "PowerPoint", "file": f"/downloads/{t}/{pptx.name}"}]
        n = 0
        if pdf.exists():
            shutil.copy2(pdf, d / pdf.name)
            files.append({"label": "Strategy deck", "type": "PDF", "file": f"/downloads/{t}/{pdf.name}"})
            n = slide_images(pdf, d / "slides")
        solver = EXCEL_DIR / f"squad_optimiser_{t}.xlsx"
        if solver.exists():
            shutil.copy2(solver, d / solver.name)
            files.append({"label": "Squad optimiser (Excel Solver)", "type": "Excel", "file": f"/downloads/{t}/{solver.name}"})
        model = EXCEL_DIR / "franchise_model.xlsx"
        if model.exists():
            shutil.copy2(model, d / model.name)
            files.append({"label": "Franchise P&L model", "type": "Excel", "file": f"/downloads/{t}/{model.name}"})
        csv = d / f"recommendations_{t}.csv"
        recs[recs["team"] == t].to_csv(csv, index=False)
        files.append({"label": "Buy / Retain / Release table", "type": "CSV", "file": f"/downloads/{t}/{csv.name}"})
        for f in files:
            f["bytes"] = (ROOT / "web" / "public" / f["file"].lstrip("/")).stat().st_size
        manifest[t] = {"files": files, "slides": [f"/downloads/{t}/slides/slide-{i:02d}.jpg" for i in range(1, n + 1)]}
        print(t, len(files), "files,", n, "slides")
    MANIFEST.write_text(json.dumps(manifest, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-pdf", action="store_true", help="skip PowerPoint rendering")
    main(render=not ap.parse_args().no_pdf)
