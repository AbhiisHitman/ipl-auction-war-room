"""Normalise team logos for the dark web UI.

Source images (as supplied) live in web/logo-src/. For each one:
  1. If it has a flat light background (no alpha), flood-fill from the image
     border through near-white / light-grey pixels and make that region
     transparent. Interior whites (text, outlines) are kept because they are
     not connected to the border.
  2. Soften the cut edge and remove the white fringe (colour decontamination).
  3. Trim empty margins and fit the logo into a square canvas with even
     padding, so every logo has the same visual size.

    python -m src.prepare_logos
"""
from __future__ import annotations

from collections import deque

import numpy as np
from PIL import Image

from .config import ROOT

SRC = ROOT / "web" / "logo-src"
OUT = ROOT / "web" / "public" / "logos"
SIZE = 512
PAD = 0.06  # share of the canvas left empty on each side
# Source files that carry a fake "transparency" checkerboard plus a thin ring
# around the badge: the fill is allowed to bridge that ring.
BRIDGE = {"DC", "PBKS"}
RING_PX = 6


def dilate(mask: np.ndarray, r: int) -> np.ndarray:
    out = mask.copy()
    for _ in range(r):
        m = out.copy()
        m[1:, :] |= out[:-1, :]
        m[:-1, :] |= out[1:, :]
        m[:, 1:] |= out[:, :-1]
        m[:, :-1] |= out[:, 1:]
        out = m
    return out


def flood(cand: np.ndarray, seeds: np.ndarray) -> np.ndarray:
    """Pixels in `cand` connected (4-neighbour) to any seed pixel."""
    h, w = cand.shape
    bg = seeds & cand
    q = deque(zip(*np.nonzero(bg)))
    while q:
        y, x = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and cand[ny, nx] and not bg[ny, nx]:
                bg[ny, nx] = True
                q.append((ny, nx))
    return bg


def background_mask(rgb: np.ndarray, bridge: bool = False, min_light: int = 196,
                    max_chroma: int = 28) -> np.ndarray:
    """Border-connected region of light, low-saturation pixels. With `bridge`,
    the fill may also jump a thin ring (up to RING_PX) and the ring is cleared."""
    h, w, _ = rgb.shape
    mx, mn = rgb.max(axis=2).astype(int), rgb.min(axis=2).astype(int)
    cand = (mn >= min_light) & ((mx - mn) <= max_chroma)
    border = np.zeros((h, w), dtype=bool)
    border[0, :] = border[-1, :] = border[:, 0] = border[:, -1] = True
    outer = flood(cand, border)
    if not bridge:
        return outer
    inner = flood(cand, dilate(outer, RING_PX))
    ring = dilate(outer, RING_PX) & dilate(inner & ~outer, RING_PX) & ~inner
    return outer | inner | ring


def cut_background(img: Image.Image, bridge: bool = False) -> Image.Image:
    rgb = np.asarray(img.convert("RGB")).astype(np.float32)
    bg = background_mask(rgb.astype(np.uint8), bridge=bridge)
    alpha = np.where(bg, 0.0, 1.0)
    # Edge pixels next to the background: partial alpha by how light they are,
    # then remove the white they were blended with (decontamination).
    edge = np.zeros_like(bg)
    edge[1:, :] |= bg[:-1, :]
    edge[:-1, :] |= bg[1:, :]
    edge[:, 1:] |= bg[:, :-1]
    edge[:, :-1] |= bg[:, 1:]
    edge &= ~bg
    light = rgb.min(axis=2)
    a_edge = np.clip((255.0 - light) / (255.0 - 150.0), 0.15, 1.0)
    alpha = np.where(edge, a_edge, alpha)
    a3 = np.clip(alpha, 1e-3, 1)[..., None]
    rgb = np.where(edge[..., None], np.clip((rgb - (1 - a3) * 255.0) / a3, 0, 255), rgb)
    out = np.dstack([rgb, alpha * 255.0]).astype(np.uint8)
    if bridge:
        # Ring fragments can survive as separate pieces: keep only the badge,
        # i.e. the solid shape connected to the solid pixel nearest the centre.
        solid = out[..., 3] > 128
        ys, xs = np.nonzero(solid)
        h, w = solid.shape
        k = np.argmin((ys - h / 2) ** 2 + (xs - w / 2) ** 2)
        seed = np.zeros_like(solid)
        seed[ys[k], xs[k]] = True
        keep = dilate(flood(solid, seed), 2)
        out[~keep, 3] = 0
    return Image.fromarray(out, "RGBA")


def fit_square(img: Image.Image) -> Image.Image:
    arr = np.asarray(img).copy()
    arr[arr[..., 3] < 40, 3] = 0  # drop faint specks left from the background
    img = Image.fromarray(arr, "RGBA")
    a = arr[..., 3]
    ys, xs = np.where(a > 128)  # size the logo by its solid pixels
    crop = img.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    inner = int(SIZE * (1 - 2 * PAD))
    scale = inner / max(crop.width, crop.height)  # up- or down-scale to the same size
    crop = crop.resize((max(1, round(crop.width * scale)), max(1, round(crop.height * scale))), Image.LANCZOS)
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    canvas.paste(crop, ((SIZE - crop.width) // 2, (SIZE - crop.height) // 2), crop)
    return canvas


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for src in sorted(SRC.glob("*.png")):
        img = Image.open(src)
        has_alpha = img.mode in ("RGBA", "LA") and np.asarray(img.convert("RGBA"))[..., 3].min() < 250
        rgba = img.convert("RGBA") if has_alpha else cut_background(img, bridge=src.stem in BRIDGE)
        fit_square(rgba).save(OUT / src.name, optimize=True)
        print(f"{src.name}: {'kept alpha' if has_alpha else 'background removed'}")


if __name__ == "__main__":
    main()
