#!/usr/bin/env python3
"""Stage the final deliverables for copying to a laptop: hardlinks (no extra disk) in out/export/

    python3 pipeline/export_local.py            # then: rsync -av --delete <server>:.../vani/out/export/ ~/vani-videos/

    video/<collection>/<group>/<slug>.mp4
    mp3/<collection>/<group>/<slug>.mp3          the drone mix (_sruthi_m16), the one the video uses
    title-slides/<collection>/<group>/<slug>.png the video's title slide
    scratch/                                     hand-made trials (seed tries etc.); never deleted by this script
    upload_status.tsv                            the upload tracker (a copy, refreshed by upload_status.py too)
"""
import glob, os, re, shutil, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "out")
EXP = os.path.join(OUT, "export")
FLAGS = re.compile(r"_(FALLBACK|DETECTED|PROSE)$")
V2 = set()                      # work/v2.txt: ids of rebuilt replacements for uploaded videos -> exported as <slug>_v2.*
_v2 = os.path.join(ROOT, "work", "v2.txt")
if os.path.exists(_v2): V2 = {l.strip() for l in open(_v2) if l.strip() and not l.startswith("#")}


def v2(sid, slug):
    return slug + "_v2" if sid in V2 else slug


def link(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.exists(dst):
        if os.path.samefile(src, dst): return False
        os.remove(dst)
    os.link(src, dst)
    return True


def main():
    n = dict(video=0, mp3=0, slides=0)
    keep = set()
    for mp4 in sorted(glob.glob(f"{OUT}/video/**/*.mp4", recursive=True)):
        d = os.path.dirname(mp4)
        slug = os.path.basename(d)
        if os.path.basename(mp4) != slug + ".mp4": continue
        parent = os.path.relpath(os.path.dirname(d), f"{OUT}/video")
        for kind, src, ext in (("video", mp4, "mp4"), ("title-slides", os.path.join(d, "slides", "000_title.png"), "png")):
            if not os.path.exists(src): print("missing", kind, slug); continue
            dst = os.path.join(EXP, kind, parent, f"{v2(os.path.relpath(d, f'{OUT}/video'), slug)}.{ext}"); keep.add(dst); link(src, dst)
            n["video" if kind == "video" else "slides"] += 1
    for mp3 in sorted(glob.glob(f"{OUT}/mp3/**/*_sruthi_m16.mp3", recursive=True)):
        d = os.path.dirname(mp3)
        slug = FLAGS.sub("", os.path.basename(d))
        parent = os.path.relpath(os.path.dirname(d), f"{OUT}/mp3")
        dst = os.path.join(EXP, "mp3", parent, f"{v2(os.path.relpath(os.path.join(os.path.dirname(d), slug), f'{OUT}/mp3'), slug)}.mp3")
        assert dst not in keep, f"two mixes for {dst}"
        keep.add(dst); link(mp3, dst); n["mp3"] += 1
    tsv = os.path.join(ROOT, "work", "youtube", "upload_status.tsv")
    if os.path.exists(tsv):
        dst = os.path.join(EXP, "upload_status.tsv"); keep.add(dst)
        shutil.copyfile(tsv, dst + ".tmp"); os.replace(dst + ".tmp", dst)
    stale = [os.path.join(r, f) for r, _, fs in os.walk(EXP) for f in fs
             if os.path.join(r, f) not in keep and not os.path.relpath(r, EXP).startswith("scratch")]
    for s in stale: os.remove(s)
    print(n, f"removed {len(stale)} stale")


if __name__ == "__main__":
    sys.exit(main())
