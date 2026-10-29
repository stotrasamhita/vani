#!/usr/bin/env python3
"""Crop the Kāñcī-pīṭha ācārya portraits (jyotisham/adyatithi, mahApuruSha/kAnchI-maTha/images)
to the painting alone (frame and bevel trimmed) -> work/kanchi/NN.jpg, plus a mosaic of all
of them (work/kanchi/mosaic.png) for the verses that praise the whole lineage.

    python3 pipeline/kanchi_portraits.py [--src /data1/karthik_data/adyatithi-kanchi/mahApuruSha/kAnchI-maTha/images]
"""
import argparse, glob, os
import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = f"{ROOT}/work/kanchi"


def crop(path):
    """The files are already cropped to the painting but keep a sepia frame and a white bevel. On each side, walk
    in from the edge (median over the middle half of the side) to the last bright bevel pixel and cut just past it."""
    im = Image.open(path).convert("RGB")
    g = np.asarray(im.convert("L")).astype(float); H, W = g.shape
    def inset(lines, limit):                      # lines: (n, length) profiles running from the edge inwards
        v = []
        for ln in lines:
            bright = np.where(ln[:limit] > 225)[0]
            v.append(bright.max() + 1 if len(bright) else 0)
        return int(np.median(v))
    q = lambda n: slice(n // 4, 3 * n // 4)
    l = inset(g[q(H)], int(0.2 * W)); r = inset(g[q(H), ::-1], int(0.2 * W))
    t = inset(g[:, q(W)].T, int(0.2 * H)); b = inset(g[::-1, q(W)].T, int(0.2 * H))
    m = int(0.004 * W)
    return im.crop((l + m, t + m, W - r - m, H - b - m))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="/data1/karthik_data/adyatithi-kanchi/mahApuruSha/kAnchI-maTha/images")
    ap.add_argument("--extra", default="/data1/karthik_data/kanchi-extra")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    ims = []
    for p in sorted(glob.glob(f"{a.src}/jagadguru-*.jpg")):
        n = int(os.path.basename(p)[10:12]); im = crop(p)
        im.thumbnail((1400, 1700)); im.save(f"{OUT}/{n:02d}.jpg", quality=92); ims.append(im)
    cols, rows, cw, ch, gap = 10, 7, 166, 187, 4          # 67 portraits into a 10 x 7 grid, the last row centred
    have = {int(os.path.basename(p)[10:12]) for p in glob.glob(f"{a.src}/jagadguru-*.jpg")}
    for p in sorted(glob.glob(f"{a.extra}/jagadguru-*.jpg")):          # later pontiffs' photographs: used as they are, only for numbers the repo lacks
        n = int(os.path.basename(p)[10:12])
        if n in have: print(f"skip extra {n:02d}: the repo already has it"); continue
        im = Image.open(p).convert("RGB"); im.thumbnail((1400, 1700)); im.save(f"{OUT}/{n:02d}.jpg", quality=92)
    sheet = Image.new("RGBA", (cols * (cw + gap) + gap, rows * (ch + gap) + gap), (0, 0, 0, 0))
    for k, im in enumerate(ims):
        r, c = divmod(k, cols); off = (cols - (len(ims) - r * cols)) * (cw + gap) // 2 if r == rows - 1 else 0
        t = im.resize((cw, ch), Image.LANCZOS); sheet.paste(t, (gap + c * (cw + gap) + off, gap + r * (ch + gap)))
    sheet.save(f"{OUT}/mosaic.png")
    print(len(ims), "portraits ->", OUT, sheet.size)


if __name__ == "__main__":
    main()
