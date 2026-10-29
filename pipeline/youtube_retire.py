#!/usr/bin/env python3
"""Retire replaced videos: put each new video into the playlists its old one was in, take the old one
out of them, and make the old one unlisted (never deletes; a private old video is left private).

    python3 pipeline/youtube_retire.py OLD_ID:NEW_ID [OLD_ID:NEW_ID ...] [--apply]

Dry run by default. Playlist changes cost 50 quota units each.
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import youtube_apply as Y


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pairs", nargs="+", metavar="OLD:NEW"); ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    pairs = dict(p.split(":") for p in a.pairs)
    api = Y.API()
    for pid, p in {p["id"]: p for p in api.paged("playlists", part="snippet", mine="true")}.items():
        items = {i["snippet"]["resourceId"]["videoId"]: i for i in api.paged("playlistItems", part="snippet", playlistId=pid)}
        for old, new in pairs.items():
            if old not in items: continue
            print(f"playlist '{p['snippet']['title']}': old {old} present; new {'present' if new in items else 'MISSING'}")
            if not a.apply: continue
            if new not in items:
                api.call("POST", "playlistItems", params=dict(part="snippet"), json=dict(snippet=dict(
                    playlistId=pid, resourceId=dict(kind="youtube#video", videoId=new))))
                print("   added new")
            print("   removed old", api.s.delete(f"{Y.YT}/playlistItems", params=dict(id=items[old]["id"]), timeout=60).status_code)
    for old in pairs:
        found = api.call("GET", "videos", params=dict(part="status", id=old))["items"]
        if not found: print(old, "not found"); continue
        st = found[0]["status"]["privacyStatus"]
        print(old, "privacy", st)
        if a.apply and st == "public":
            found[0]["status"]["privacyStatus"] = "unlisted"
            api.call("PUT", "videos", params=dict(part="status"), json=dict(id=old, status=found[0]["status"]))
            print("   -> unlisted")


if __name__ == "__main__":
    main()
