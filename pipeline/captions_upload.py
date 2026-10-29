#!/usr/bin/env python3
"""Upload the subtitle tracks made by subtitles.py to a video (captions.insert, 400 quota units each).

    python3 pipeline/captions_upload.py stotras/shiva/shivamanasapuja [more stotras ...] [--scripts sa,en,te,...] [--lines] [--apply]

Uses the whole-verse tracks (subtitles_verse.py) unless --lines (subtitles.py). Stops at the first quota error.

Needs the youtube.force-ssl scope: run `youtube_apply.py --auth CLIENT_SECRET.json` once more.
Tracks already uploaded (work/youtube/captions.json) are skipped.
"""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import requests
import youtube_apply as Y
from subtitles import TRACKS

STATE = f"{Y.ROOT}/work/youtube/captions.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stotra", nargs="+"); ap.add_argument("--scripts", default=",".join(TRACKS)); ap.add_argument("--apply", action="store_true")
    ap.add_argument("--lines", action="store_true", help="line-timed tracks instead of whole-verse ones")
    a = ap.parse_args()
    state = json.load(open(STATE)) if os.path.exists(STATE) else {}
    jobs = []
    for stotra in a.stotra:
        slug = stotra.rsplit("/", 1)[1]
        vid = json.load(open(Y.STATE)).get(slug) or Y.die(f"{slug}: no video id in applied.json")
        todo = [c for c in a.scripts.split(",") if c not in state.get(slug, {})]
        print(f"{slug} -> {vid}: {len(todo)} tracks to upload ({400 * len(todo)} quota units): {','.join(todo)}")
        jobs += [(stotra, slug, vid, c) for c in todo]
    if not a.apply: return print(f"dry run: {len(jobs)} tracks, {400 * len(jobs)} units (use --apply)")
    api = Y.API()
    for stotra, slug, vid, code in jobs:
        lang, name, _ = TRACKS[code]
        path = f"{Y.ROOT}/out/subtitles/{stotra}/{'' if a.lines else 'verse/'}{slug}.{code}.srt"
        meta = json.dumps(dict(snippet=dict(videoId=vid, language=lang, name=name, isDraft=False)))
        files = {"metadata": ("metadata", meta, "application/json; charset=UTF-8"),
                 "media": ("captions.srt", open(path, "rb").read(), "application/octet-stream")}
        r = api.s.post("https://www.googleapis.com/upload/youtube/v3/captions",
                       params=dict(part="snippet", uploadType="multipart"), files=files, timeout=120)
        if r.status_code >= 400:
            print(f"  FAIL {slug} {code}: {r.status_code} {r.text[:300]}")
            if r.status_code == 403: break
            continue
        state.setdefault(slug, {})[code] = r.json()["id"]
        json.dump(state, open(STATE, "w"), indent=1); print(f"  ok {slug} {code} {name}")


if __name__ == "__main__":
    main()
