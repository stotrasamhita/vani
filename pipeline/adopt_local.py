#!/usr/bin/env python3
"""Reuse an old local download in the new vani-videos layout, so rsync only fetches what differs.

    python3 adopt_local.py vagdhenu vani-videos              # copies; run from the folder that holds both
    rsync -avc --info=progress2 <server>:/data1/karthik_data/vani/out/export/ vani-videos/

Old   out/video/<coll>/<group>/<slug>/<slug>.mp4                  ->  video/<coll>/<group>/<slug>.mp4
Old   out/mp3/<coll>/<group>/<slug>[_FALLBACK..]/*_sruthi_m16.mp3  ->  mp3/<coll>/<group>/<slug>.mp3
The old folder is left untouched. rsync -c compares checksums, so files that were rebuilt since are re-sent
and replaced.
"""
import argparse, os, re, shutil, sys

FLAGS = re.compile(r"_(FALLBACK|DETECTED|PROSE)$")


def target(old, rel):
    p = rel.split(os.sep)
    if p[0] == "out" and p[1] == "video" and p[-1].endswith(".mp4") and len(p) >= 4 and p[-1] == p[-2] + ".mp4":
        return os.path.join("video", *p[2:-2], p[-2] + ".mp4")
    if p[0] == "out" and p[1] == "mp3" and p[-1].endswith("_sruthi_m16.mp3") and len(p) >= 4:
        return os.path.join("mp3", *p[2:-2], FLAGS.sub("", p[-2]) + ".mp3")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("old"); ap.add_argument("new")
    a = ap.parse_args()
    old, new = os.path.abspath(os.path.expanduser(a.old)), os.path.abspath(os.path.expanduser(a.new))
    n = dict(video=0, mp3=0, skipped=0); seen = {}
    for r, _, fs in os.walk(os.path.join(old, "out")):
        for f in fs:
            src = os.path.join(r, f); t = target(old, os.path.relpath(src, old))
            if not t: continue
            if t in seen: print("duplicate source for", t, "-", src, "ignored"); continue
            seen[t] = src
            dst = os.path.join(new, t)
            if os.path.exists(dst): n["skipped"] += 1; continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            n[t.split(os.sep)[0]] += 1
    print(n)


if __name__ == "__main__":
    sys.exit(main())
