#!/usr/bin/env python3
"""Listening sheet for quality control: every distinct take of one kind of clip, in one mp3.

    python3 pipeline/qc_sheet.py [--flag UVACA] [--shard work/bulk.json] [-o work/qc_uvaca]

Writes <o>.mp3 (each distinct take once, separated by --gap s of silence) and <o>.tsv
(number, timestamp, text, IAST, uses, example texts, cache key). Note the numbers of bad
takes, then fix them in pipeline/overrides.tsv (text -> meter, seed) and rerun run.sh.
--flag matches any flag substring (UVACA, COLOPHON, FALLBACK, ...).
"""
import argparse, json, os, subprocess, sys, tempfile
from collections import OrderedDict
import numpy as np, soundfile as sf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import FFMPEG                                  # noqa: E402
from indic_transliteration import sanscript                # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--flag", default="UVACA")
    ap.add_argument("--shard", default="work/bulk.json")
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--gap", type=float, default=1.2)
    a = ap.parse_args()
    out = a.out or f"work/qc_{a.flag.lower()}"
    takes = OrderedDict()                                  # key -> [clips], in corpus order
    for c in json.load(open(a.shard, encoding="utf-8")):
        if a.flag in c.get("flag", ""):
            takes.setdefault(c["key"], []).append(c)
    parts, rows, t, sr = [], [], 0.0, None
    for i, (key, cs) in enumerate(takes.items(), 1):
        c = cs[0]
        if not os.path.exists(c["out"]):
            print(f"[missing] {c['id']}", file=sys.stderr); continue
        y, sr_ = sf.read(c["out"], dtype="float32"); sr = sr or sr_
        text = " | ".join(c["padas"])
        texts = sorted({x["stotra"].rsplit("/", 1)[1] for x in cs})
        rows.append([str(i), f"{int(t // 60)}:{t % 60:05.2f}", text,
                     sanscript.transliterate(text, sanscript.DEVANAGARI, sanscript.IAST),
                     str(len(cs)), ", ".join(texts[:4]) + (" …" if len(texts) > 4 else ""), key])
        parts += [y, np.zeros(int(a.gap * sr), np.float32)]
        t += len(y) / sr + a.gap
    with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
        sf.write(tmp.name, np.concatenate(parts), sr)
        subprocess.run([FFMPEG, "-loglevel", "error", "-y", "-i", tmp.name, "-b:a", "160k", out + ".mp3"], check=True)
    with open(out + ".tsv", "w", encoding="utf-8") as f:
        f.write("n\tat\ttext\tiast\tuses\ttexts\tkey\n")
        f.writelines("\t".join(r) + "\n" for r in rows)
    print(f"{out}.mp3  ({len(rows)} takes, {t / 60:.1f} min)  +  {out}.tsv")


if __name__ == "__main__":
    main()
