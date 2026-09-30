#!/usr/bin/env python3
"""Build the full render shard from the source repos.

    python3 pipeline/make_shard.py [-o work/bulk.json]

The corpus definition (sources, exclusions, rules) lives in corpora.py. Only complete texts are rendered. Prose
(never rendered) counts as missing content; colophon/label lines ("इति ...", < 12 syll.) don't.
A text whose recited verses are >= FALLBACK_MIN_CLEAN clean is completed by rendering its flagged
verses anyway, with the builder's fallback meter (detected meter if in the bank, else the
header's, else vasantatilaka), flagged FALLBACK in the TSVs. Any other text with a flagged
verse waits: its cached renders are kept and it returns once enough verses are renderable. Writes the shard (renderable clips
only) plus <shard>_all.tsv listing every clip, including the excluded ones and why, and
reports how many clips have no cached render yet (= what render.py will actually do).
"""
import argparse, collections, glob, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_shard import build, n_ak                            # noqa: E402

from corpora import SOURCES, PIECES, EXCLUDE_DIRS, EXCLUDE_STOTRAS, RENDER_FLAGS, PROSE_MAX   # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default="work/bulk.json")
    ap.add_argument("--cache", default="out/cache")
    a = ap.parse_args()
    keep, rows = [], []
    jobs = [(path, coll, group, {}) for pattern, coll, group in SOURCES
            for path in sorted(glob.glob(pattern, recursive=True)) if not any(d in path for d in EXCLUDE_DIRS)]
    jobs += [(path, coll, group, dict(slug=slug, **opt)) for path, coll, group, slug, opt in PIECES]
    for path, coll, group, opt in jobs:
            split = opt.pop("split", None)
            for c in build(path, 60, 24, group, coll, a.cache, **opt):
                if split: c["split_src"] = split
                text = " ".join(c["padas"])
                why = ("excluded stotra" if c["stotra"] in EXCLUDE_STOTRAS else "") \
                    if c["flag"] in ("COLOPHON", "UVACA", "HEADING") else \
                      ("label" if c["meter"] == "gadya" and (re.match(r"इति|इत्य", text) or n_ak(text) < 12) else
                       "prose" if c["meter"] == "gadya" else
                       "excluded stotra" if c["stotra"] in EXCLUDE_STOTRAS else
                       "" if c["flag"] in RENDER_FLAGS else "flag")
                rows.append((c, why))
    n, prose = collections.Counter(), collections.Counter()   # prose is recited content we don't render
    for c, why in rows:
        if why in ("", "flag", "prose"): n[c["stotra"]] += 1; prose[c["stotra"]] += why == "prose"
    partial = {t for t in n if prose[t] / n[t] > PROSE_MAX}
    rescued = {t for t, why in ((c["stotra"], w) for c, w in rows) if why == "flag"} - partial
    for i, (c, why) in enumerate(rows):
        if why == "flag" and c["stotra"] not in partial:
            c["flag"] += ",DETECTED" if c["flag"] == "MISMATCH" else ",FALLBACK"; rows[i] = (c, "")
        elif not why and c["stotra"] in partial:
            rows[i] = (c, "incomplete text")
    keep = [c for c, why in rows if not why]
    ids = collections.Counter(c["id"] for c in keep)
    dup = [k for k, v in ids.items() if v > 1]
    if dup: sys.exit(f"duplicate clip ids: {dup[:10]}")
    json.dump(keep, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open(a.out[:-5] + "_all.tsv", "w", encoding="utf-8") as f:
        f.write("stotra\tid\tkey\tmeter\tdetected\tdeclared\tflag\texcluded\ttext\n")
        for c, why in rows:
            f.write("\t".join([c["stotra"], c["id"], c["key"], c["meter"], c["detected"], c["declared"],
                               c["flag"], why, " | ".join(c["padas"])]) + "\n")
    todo = sum(not os.path.exists(c["out"]) for c in keep)
    print(f"{len(keep)} clips in {len({c['stotra'] for c in keep})} texts -> {a.out}")
    print(f"excluded: {dict(collections.Counter(w for _, w in rows if w))}; "
          f"{len(partial - EXCLUDE_STOTRAS)} mostly-prose texts held back; "
          f"{sum('FALLBACK' in c['flag'] for c in keep)} FALLBACK + "
          f"{sum('DETECTED' in c['flag'] for c in keep)} DETECTED verses in {len(rescued)} texts")
    print(f"to render (not in cache): {todo}")


if __name__ == "__main__":
    main()
