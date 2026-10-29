#!/usr/bin/env python3
"""The upload tracker: one row per built video -> work/youtube/upload_status.tsv (open it as a sheet).

    python3 pipeline/upload_status.py             # offline: from out/video, applied.json, thumbs.json
    python3 pipeline/upload_status.py --refresh   # also ask YouTube which videos are uploaded and their privacy

Columns: collection group slug title playlists built size_mb uploaded video_id applied thumbnail privacy
         flags uploaded_on notes
`uploaded` (type Y), `uploaded_on` and `notes` are yours to edit: rerunning keeps what you typed. Everything
else is recomputed. A video counts as uploaded once it has a video id or you mark it Y.
`applied` = youtube_apply.py has set title/description/playlists; `thumbnail` = title slide set as thumbnail.
--refresh reads the channel's uploads (about 15 quota units) and so needs the OAuth token and some quota.
"""
import csv, glob, json, os, re, sys, time, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)
YTD = f"{ROOT}/work/youtube"
OUT = f"{YTD}/upload_status.tsv"
COLS = ["collection", "group", "slug", "title", "playlists", "built", "size_mb", "uploaded", "video_id",
        "applied", "thumbnail", "privacy", "flags", "uploaded_on", "notes"]
MANUAL = ("uploaded_on", "notes")


def load(p, default):
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else default


def text_fields(slug):
    p = f"{YTD}/{slug}.txt"
    if not os.path.exists(p): return "", ""
    t = open(p, encoding="utf-8").read().split("\n")
    def sec(h):
        i = next((k for k, l in enumerate(t) if l == h or l.startswith(h + " (")), None)
        return t[i + 1].strip() if i is not None else ""
    return sec("TITLE"), sec("PLAYLIST")


def live(api, slugs, titles):
    """slug -> (video_id, privacy) from the channel's uploads, matched like youtube_apply (by Studio title)."""
    import youtube_apply as Y
    ch = api.call("GET", "channels", params=dict(part="contentDetails", mine="true"))["items"][0]
    by = collections.defaultdict(list)
    for it in api.paged("playlistItems", part="snippet", playlistId=ch["contentDetails"]["relatedPlaylists"]["uploads"]):
        by[Y.norm(it["snippet"]["title"])].append(it["snippet"]["resourceId"]["videoId"])
    found = {}
    for s in slugs:
        c = list(dict.fromkeys(by.get(Y.norm(s)) or (by.get(Y.norm(titles[s])) if titles.get(s) else None) or []))
        if len(c) == 1: found[s] = c[0]
        elif len(c) > 1: found[s] = "MULTIPLE:" + ",".join(c)
    ids = [v for v in found.values() if not v.startswith("MULTIPLE")]
    priv = {}
    for i in range(0, len(ids), 50):
        for v in api.call("GET", "videos", params=dict(part="status", id=",".join(ids[i:i + 50])))["items"]:
            priv[v["id"]] = v["status"]["privacyStatus"]
    return {s: (v, priv.get(v, "")) for s, v in found.items()}


def main():
    refresh = "--refresh" in sys.argv
    applied, thumbs = load(f"{YTD}/applied.json", {}), load(f"{YTD}/thumbs.json", {})
    old = {}
    if os.path.exists(OUT):
        for r in csv.DictReader(open(OUT, encoding="utf-8"), delimiter="\t"):
            old[(r["group"], r["slug"])] = r
    rows = []
    for mp4 in sorted(glob.glob(f"{ROOT}/out/video/**/*.mp4", recursive=True)):
        d = os.path.dirname(mp4); slug = os.path.basename(d)
        if os.path.basename(mp4) != slug + ".mp4": continue
        rel = os.path.relpath(os.path.dirname(d), f"{ROOT}/out/video").split(os.sep)
        title, pls = text_fields(slug)
        rows.append(dict(collection=rel[0], group="/".join(rel[1:]), slug=slug, title=title, playlists=pls,
                         built=time.strftime("%Y-%m-%d", time.localtime(os.path.getmtime(mp4))),
                         size_mb=round(os.path.getsize(mp4) / 1e6)))
    dup = collections.Counter(r["slug"] for r in rows)
    lv = {}
    if refresh:
        import youtube_apply as Y
        slugs = [r["slug"] for r in rows]
        lv = live(Y.API(), slugs, {r["slug"]: r["title"] for r in rows})
    for r in rows:
        prev = old.get((r["group"], r["slug"]), {})
        s = r["slug"]
        vid = lv.get(s, ("", ""))[0] or applied.get(s, "") or prev.get("video_id", "")
        r["video_id"] = vid
        r["privacy"] = lv.get(s, ("", ""))[1] or prev.get("privacy", "")
        r["applied"] = "Y" if s in applied else ""
        r["thumbnail"] = "Y" if s in thumbs else ""
        r["uploaded"] = "Y" if (vid and not vid.startswith("MULTIPLE")) or prev.get("uploaded") == "Y" else ""
        r["flags"] = ("slug shared with another text; upload only one; " if dup[s] > 1 else "") + \
                     ("several uploads with this title" if vid.startswith("MULTIPLE") else "")
        for k in MANUAL: r[k] = prev.get(k, "")
        if r["uploaded"] and not r["uploaded_on"]: r["uploaded_on"] = prev.get("uploaded_on", "")
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, COLS, delimiter="\t", extrasaction="ignore"); w.writeheader(); w.writerows(rows)
    os.replace(tmp, OUT)
    if os.path.isdir(f"{ROOT}/out/export"):
        import shutil
        shutil.copyfile(OUT, f"{ROOT}/out/export/upload_status.tsv.tmp")
        os.replace(f"{ROOT}/out/export/upload_status.tsv.tmp", f"{ROOT}/out/export/upload_status.tsv")
    n = len(rows); up = sum(1 for r in rows if r["uploaded"]); ap = sum(1 for r in rows if r["applied"])
    print(f"{n} videos: {up} uploaded, {ap} applied, {sum(1 for r in rows if r['thumbnail'])} with thumbnail, "
          f"{n - up} still to upload -> {OUT}")
    by = collections.Counter((r["collection"], bool(r["uploaded"])) for r in rows)
    for c in sorted({k[0] for k in by}): print(f"  {c:14s} {by[(c, True)]:4d} uploaded  {by[(c, False)]:4d} to do")


if __name__ == "__main__":
    main()
