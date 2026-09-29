#!/usr/bin/env python3
"""Publish rendered verses from the cache as mp3s, one folder per text.

    python3 pipeline/to_mp3.py SHARD.json [--root out/mp3] [--pause 0.8] [--prune]

For each text (`stotra` field) writes <root>/<stotra>/:
    <id>.mp3           one per verse, re-encoded only when its render key changed
    <slug>_full.mp3    all verses in `seq` order joined with --pause s of silence;
                       rebuilt whenever any verse in the text changed
    <slug>.tsv         QC sheet: id, key, meter, detected, declared, flag, duration, text
Verse mp3s whose id is no longer in the shard are deleted. Verses without a render yet are
reported and left out (the text is marked incomplete). --prune also deletes folders of texts
that have dropped out of the shard. Safe to rerun at any time.

--complete_only publishes only texts whose every verse is rendered. --watch SEC repeats that
every SEC seconds while renders run, so each text's mp3s appear as soon as its last verse
lands; it exits once no render.py is running and a final full pass is done.
"""
import argparse, fcntl, json, os, re, shutil, subprocess, sys, time
from collections import defaultdict
import numpy as np, soundfile as sf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import FFMPEG                                  # noqa: E402

COLS = ["id", "key", "meter", "detected", "declared", "flag", "dur_s", "text"]
VARIANTS = ("", "_FALLBACK", "_INCOMPLETE")
FALLBACK_LABEL = 0.10     # texts with more fallback-meter verses than this publish as <slug>_FALLBACK


def enc(src, dst, bitrate):
    subprocess.run([FFMPEG, "-loglevel", "error", "-y", "-i", src, "-b:a", bitrate, dst + ".part.mp3"], check=True)
    os.replace(dst + ".part.mp3", dst)


def old_keys(tsv):
    if not os.path.exists(tsv): return {}
    lines = open(tsv, encoding="utf-8").read().splitlines()
    hdr = lines[0].split("\t")
    if "key" not in hdr: return {}
    i, k = hdr.index("id"), hdr.index("key")
    return {r.split("\t")[i]: r.split("\t")[k] for r in lines[1:]}


def publish(stotra, clips, root, pause, bitrate):
    fb = sum("FALLBACK" in c.get("flag", "") for c in clips) / len(clips)
    sfx = "_FALLBACK" if fb > FALLBACK_LABEL else ""
    base = os.path.join(root, stotra); d = base + sfx
    for v in VARIANTS:                               # a text's status changed: drop the old variant
        if v != sfx and os.path.isdir(base + v): shutil.rmtree(base + v)
    os.makedirs(d, exist_ok=True)
    slug = os.path.basename(stotra)
    tsv, full = os.path.join(d, slug + ".tsv"), os.path.join(d, slug + "_full" + sfx + ".mp3")
    prev = old_keys(tsv)
    clips.sort(key=lambda c: c["seq"])
    if prev == {c["id"]: c["key"] for c in clips} and os.path.exists(full) \
            and all(os.path.exists(os.path.join(d, c["id"] + ".mp3")) for c in clips):
        return "unchanged", []                       # fast path: published copy matches the shard
    ids = {c["id"] for c in clips}
    changed, missing, rows = 0, [], []
    for f in os.listdir(d):                          # verses that no longer exist
        if f.endswith(".mp3") and f != os.path.basename(full) and f[:-4] not in ids \
                and "_full" not in f:                     # drone mixes (_full*_tanpura etc.) belong to tanpura.py
            os.remove(os.path.join(d, f)); changed += 1
    for c in clips:
        mp3 = os.path.join(d, c["id"] + ".mp3")
        if not os.path.exists(c["out"]):
            missing.append(c["id"])
            if os.path.exists(mp3): os.remove(mp3); changed += 1
            continue
        if prev.get(c["id"]) != c["key"] or not os.path.exists(mp3):
            enc(c["out"], mp3, bitrate); changed += 1
        rows.append([c["id"], c["key"], c["meter"], c.get("detected", ""), c.get("declared", ""),
                     c.get("flag", ""), f"{sf.info(c['out']).duration:.2f}", " | ".join(c["padas"])])
    if not rows: return "empty", missing
    if changed or not os.path.exists(full) or set(prev) != {r[0] for r in rows}:
        parts, sr = [], None
        for c in clips:
            if c["id"] in missing: continue
            y, sr_ = sf.read(c["out"], dtype="float32")
            assert sr in (None, sr_); sr = sr_
            parts += [y, np.zeros(int(pause * sr), np.float32)]
        tmp = full[:-4] + ".part.wav"
        sf.write(tmp, np.concatenate(parts[:-1]), sr)
        enc(tmp, full, bitrate); os.remove(tmp)
        status = "rebuilt"
    else:
        status = "unchanged"
    with open(tsv + ".part", "w", encoding="utf-8") as f:     # written last: a crash leaves old keys -> redo
        f.write("\t".join(COLS) + "\n")
        f.writelines("\t".join(r) + "\n" for r in rows)
    os.replace(tsv + ".part", tsv)
    return status, missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("shard")
    ap.add_argument("--root", default="out/mp3")
    ap.add_argument("--pause", type=float, default=0.8)
    ap.add_argument("--bitrate", default="192k")
    ap.add_argument("--prune", action="store_true", help="delete folders of texts no longer in the shard")
    ap.add_argument("--complete_only", action="store_true", help="skip texts with unrendered verses")
    ap.add_argument("--watch", type=int, default=0, metavar="SEC", help="repeat while render.py runs")
    a = ap.parse_args()
    groups = defaultdict(list)
    for c in json.load(open(a.shard, encoding="utf-8")):
        groups[c["stotra"]].append(c)
    if a.watch:
        while subprocess.run(["pgrep", "-f", "src/render.py"], capture_output=True).returncode == 0:
            run_pass(a, groups, complete_only=True, quiet=True)
            time.sleep(a.watch)
        print(f"[watch] {time.strftime('%H:%M')} no render running; final pass", flush=True)
    run_pass(a, groups, a.complete_only)


def run_pass(a, groups, complete_only, quiet=False):
    os.makedirs(a.root, exist_ok=True)
    with open(os.path.join(a.root, ".lock"), "w") as lk:   # one publisher at a time (watcher vs run.sh)
        fcntl.flock(lk, fcntl.LOCK_EX)
        _run_pass(a, groups, complete_only, quiet)


def _run_pass(a, groups, complete_only, quiet):
    tally = defaultdict(int)
    for stotra, clips in sorted(groups.items()):
        if complete_only and not all(os.path.exists(c["out"]) for c in clips):
            tally["waiting"] += 1; continue
        status, missing = publish(stotra, clips, a.root, a.pause, a.bitrate)
        if missing: status += f", incomplete ({len(missing)}/{len(clips)} not rendered)"
        tally[status.split(",")[0]] += 1
        if status != "unchanged": print(f"{time.strftime('%H:%M')} {stotra}: {status}", flush=True)
    for dp, dn, fn in os.walk(a.root):                          # texts that left the shard
        rel = os.path.relpath(dp, a.root)
        if any(f.endswith(".tsv") for f in fn) and not rel.endswith("_INCOMPLETE") \
                and re.sub(r"_FALLBACK$", "", rel) not in groups:
            if a.prune: shutil.rmtree(dp); print(f"{rel}: pruned")
            else: print(f"{rel}: no longer in shard (use --prune to delete)", file=sys.stderr)
    if not quiet: print(f"[mp3] {dict(tally)}", flush=True)


if __name__ == "__main__":
    main()
