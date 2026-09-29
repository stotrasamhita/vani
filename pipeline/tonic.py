#!/usr/bin/env python3
"""Estimate the tonic (Sa) of chant recordings relative to a target Sa.

    python3 pipeline/tonic.py WAV [WAV ...] [--sa 175] [--tsv out.tsv]

pYIN f0 on voiced frames -> cents relative to --sa, folded to one octave (-600..+600) ->
duration-weighted histogram (25-cent bins, smoothed). The histogram peak is the most-sung
pitch class, taken as the tonic estimate; the median and the share of frames within ±50 c
of the target are reported too. Laukika chant sits mostly on Sa with excursions to Re/Ni,
so a peak near 0 c means the recording is on the target Sa.
"""
import argparse, os, sys
import numpy as np, librosa


def tonic(path, sa):
    y, sr = librosa.load(path, sr=16000, mono=True)
    f0, voiced, prob = librosa.pyin(y, fmin=70, fmax=500, sr=sr, frame_length=1024)
    f = f0[voiced & (prob > 0.5)]
    if len(f) < 20: return None
    c = 1200 * np.log2(f / sa)
    fold = (c + 600) % 1200 - 600                            # pitch class vs Sa, -600..600
    h, edges = np.histogram(fold, bins=48, range=(-600, 600))
    hs = np.convolve(np.r_[h[-2:], h, h[:2]], [1, 2, 3, 2, 1], "valid")   # circular smooth
    peak = (edges[np.argmax(hs)] + edges[np.argmax(hs) + 1]) / 2
    # refine: mean of frames within ±50 c of the peak
    near = fold[np.abs((fold - peak + 600) % 1200 - 600) < 50]
    peak = float(np.mean(near)) if len(near) else peak
    return dict(peak_c=peak, peak_hz=sa * 2 ** (peak / 1200), median_hz=float(np.median(f)),
                on_sa=float(np.mean(np.abs(fold) < 50)), voiced_s=len(f) * 512 / sr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("wav", nargs="+"); ap.add_argument("--sa", type=float, default=175.0)
    ap.add_argument("--tsv")
    a = ap.parse_args()
    rows = []
    print(f"{'file':<34} {'tonic Hz':>8} {'vs Sa':>7} {'median Hz':>9} {'on Sa':>6}")
    for p in a.wav:
        r = tonic(p, a.sa)
        if not r: print(f"{os.path.basename(p):<34} (too little voiced audio)"); continue
        rows.append((p, r))
        print(f"{os.path.basename(p):<34} {r['peak_hz']:8.1f} {r['peak_c']:+6.0f}c {r['median_hz']:9.1f} {r['on_sa']:6.0%}",
              flush=True)
    if a.tsv:
        with open(a.tsv, "w") as f:
            f.write("file\ttonic_hz\tcents_vs_sa\tmedian_hz\ton_sa\n")
            for p, r in rows:
                f.write(f"{p}\t{r['peak_hz']:.1f}\t{r['peak_c']:.0f}\t{r['median_hz']:.1f}\t{r['on_sa']:.3f}\n")


if __name__ == "__main__":
    main()
