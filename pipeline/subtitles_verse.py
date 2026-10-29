#!/usr/bin/env python3
"""Whole-verse subtitle tracks that stay up exactly as long as the verse's slide (no line-by-line timing).

    python3 pipeline/subtitles_verse.py stotras/shiva/shivamanasapuja [--scripts sa,en,te,...]

Writes out/subtitles/<stotra>/verse/<slug>.<code>.srt. Cue k runs from slide k's switch-in to slide k+1's.
Same scripts and transliteration as subtitles.py.
"""
import argparse, glob, json, os, sys, textwrap
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/data1/karthik_data/vagdhenu/src")
import video as V                                           # also chdir()s to the repo
from subtitles import TRACKS, convert, srt_time


def slide_cues(stotra, shard):
    clips = sorted((c for c in json.load(open(shard, encoding="utf-8")) if c["stotra"] == stotra), key=lambda c: c.get("order", c["seq"]))
    T = V.text_info(stotra, clips)
    mixdir = next(d for d in (f"out/mp3/{stotra}", f"out/mp3/{stotra}_FALLBACK") if os.path.isdir(d))
    audio = next(glob.glob(f"{mixdir}/*_full*_sruthi_m16.mp3").__iter__())
    timing = json.load(open(audio[:-4] + ".json"))
    _, starts, _ = V.slide_jobs(clips, T, "/nonexistent", timing["lead_s"])
    texts, uv = [], []
    for c in clips:                                          # same slide rule as slide_jobs
        lines = [l for l in (T["shown"][c["seq"]] or []) if l.strip()]
        if c["flag"] == "UVACA": uv = [" ".join(lines)]; continue
        texts.append(uv + lines); uv = []
    assert len(texts) == len(starts), (len(texts), len(starts))
    ends = starts[1:] + [timing["total_s"]]
    return [(a, b, t) for a, b, t in zip(starts, ends, texts)]


def wrap(lines):
    return [w for l in lines for w in (textwrap.wrap(l, 56) if len(l) > 70 else [l])]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stotra"); ap.add_argument("--shard", default="work/bulk.json")
    ap.add_argument("--scripts", default=",".join(TRACKS))
    a = ap.parse_args()
    slug = a.stotra.rsplit("/", 1)[1]
    cs = slide_cues(a.stotra, a.shard)
    d = f"out/subtitles/{a.stotra}/verse"; os.makedirs(d, exist_ok=True)
    for code in a.scripts.split(","):
        with open(f"{d}/{slug}.{code}.srt", "w", encoding="utf-8") as f:
            for i, (x, y, lines) in enumerate(cs, 1):
                body = "\n".join(convert(l, TRACKS[code][2]) for l in wrap(lines))
                f.write(f"{i}\n{srt_time(x)} --> {srt_time(y)}\n{body}\n\n")
    print(f"{len(cs)} cues x {len(a.scripts.split(','))} scripts -> {d}/")


if __name__ == "__main__":
    main()
