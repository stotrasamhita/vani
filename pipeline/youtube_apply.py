#!/usr/bin/env python3
"""Apply work/youtube/<slug>.txt to videos already uploaded (drag-dropped) to YouTube Studio.

    python3 pipeline/youtube_apply.py --auth CLIENT_SECRET.json        # once: sign in, saves a token
    python3 pipeline/youtube_apply.py --set gita                        # dry run: which upload matches which text
    python3 pipeline/youtube_apply.py --set gita --apply                # update title/description/tags, add to playlists

An upload is matched by its Studio title, which Studio sets from the file name (chapter02.mp4 ->
"chapter02"). Applied matches are remembered in work/youtube/applied.json (slug -> video id), so the run
can be repeated after a quota stop or a fix. Privacy is never changed: private videos stay private.
Only needs `requests` (no google client libraries).
"""
import argparse, glob, json, os, re, sys, threading, time, urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
YT = "https://www.googleapis.com/youtube/v3"
TOKEN_DIR = os.path.expanduser("~/.config/vagdhenu-youtube")
TOKEN = f"{TOKEN_DIR}/token.json"
SCOPE = "https://www.googleapis.com/auth/youtube"
STATE = f"{ROOT}/work/youtube/applied.json"
CATEGORY_MUSIC = "10"
SETS = {
    "gita": ["00dhyanam", "chapter??", "19mahatmyam", "20varahamahatmyam", "21gitarthasangraha", "mahatmyam??"],
    "compilations": ["gita-sampurna", "gita-padma-sampurna"],
}


def die(msg):
    sys.exit(f"error: {msg}")


# ---------------------------------------------------------------- OAuth (installed-app loopback flow)
def auth(secret_path):
    cfg = json.load(open(secret_path))
    cfg = cfg.get("installed") or cfg.get("web") or die("not an OAuth client file")
    port = 8765
    redirect = f"http://localhost:{port}/"
    url = cfg["auth_uri"] + "?" + urllib.parse.urlencode(dict(
        client_id=cfg["client_id"], redirect_uri=redirect, response_type="code", scope=SCOPE,
        access_type="offline", prompt="consent"))
    got = {}

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            got["code"] = (q.get("code") or [None])[0]
            self.send_response(200); self.send_header("Content-Type", "text/plain"); self.end_headers()
            self.wfile.write(b"Signed in. You can close this tab.")
        def log_message(self, *a): pass

    srv = HTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print("Open this URL in your browser and sign in with the YouTube channel's account:\n\n" + url + "\n")
    print("If the browser is on another machine, the redirect to localhost will fail: copy that failed address "
          "from the address bar and paste it here (or just the code=... value).")
    print("Waiting... (paste here, or finish in the browser)", flush=True)
    t0 = time.time()
    import select
    while not got.get("code") and time.time() - t0 < 600:
        if select.select([sys.stdin], [], [], 1)[0]:
            s = sys.stdin.readline().strip()
            if s:
                m = re.search(r"code=([^&\s]+)", s)
                got["code"] = urllib.parse.unquote(m.group(1)) if m else s
    srv.shutdown()
    if not got.get("code"): die("no authorisation code received")
    r = requests.post(cfg["token_uri"], data=dict(code=got["code"], client_id=cfg["client_id"],
                      client_secret=cfg["client_secret"], redirect_uri=redirect, grant_type="authorization_code"))
    r.raise_for_status()
    tok = r.json()
    tok.update(client_id=cfg["client_id"], client_secret=cfg["client_secret"], token_uri=cfg["token_uri"])
    os.makedirs(TOKEN_DIR, exist_ok=True)
    with open(TOKEN, "w") as f: json.dump(tok, f)
    os.chmod(TOKEN, 0o600)
    print("saved", TOKEN)


class API:
    def __init__(self):
        if not os.path.exists(TOKEN): die(f"not signed in: run with --auth CLIENT_SECRET.json first")
        self.tok = json.load(open(TOKEN))
        self.s = requests.Session()
        self.refresh()

    def refresh(self):
        r = requests.post(self.tok["token_uri"], data=dict(
            client_id=self.tok["client_id"], client_secret=self.tok["client_secret"],
            refresh_token=self.tok["refresh_token"], grant_type="refresh_token"))
        if r.status_code != 200: die(f"token refresh failed ({r.text[:200]}); run --auth again")
        self.s.headers["Authorization"] = "Bearer " + r.json()["access_token"]

    def call(self, method, path, **kw):
        for attempt in range(3):
            r = self.s.request(method, f"{YT}/{path}", timeout=60, **kw)
            if r.status_code == 401 and attempt == 0: self.refresh(); continue
            if r.status_code in (500, 503): time.sleep(2 ** attempt); continue
            break
        if r.status_code >= 400:
            try: err = r.json()["error"]
            except Exception: err = {"message": r.text[:300]}
            reason = (err.get("errors") or [{}])[0].get("reason", "")
            raise RuntimeError(f"{r.status_code} {reason}: {err.get('message')}")
        return r.json()

    def paged(self, path, **params):
        params["maxResults"] = 50
        while True:
            d = self.call("GET", path, params=params)
            yield from d.get("items", [])
            if not d.get("nextPageToken"): return
            params["pageToken"] = d["nextPageToken"]


# ---------------------------------------------------------------- the text files
HEADS = ["FILE", "TITLE", "DESCRIPTION", "TAGS", "PLAYLIST", "CATEGORY / LANGUAGE", "NOTES"]


def parse(path):
    lines = open(path, encoding="utf-8").read().split("\n")
    out, cur, i = {}, None, 0
    for ln in lines:
        name = next((h for h in HEADS[i:] if re.fullmatch(re.escape(h) + r"( \(.*\))?", ln)), None)
        if name:
            cur, i = name, HEADS.index(name) + 1
            out[cur] = []
        elif cur:
            out[cur].append(ln)
    if any(h not in out for h in HEADS): die(f"{path}: missing section")
    g = lambda h: "\n".join(out[h]).strip()
    return dict(file=g("FILE"), title=g("TITLE"), description=g("DESCRIPTION"), tags=[t.strip() for t in g("TAGS").split(",") if t.strip()],
                playlist=g("PLAYLIST"), language=g("CATEGORY / LANGUAGE").split("/")[-1].strip())


def check(m, slug):
    bad = [f for f in ("title", "description") if re.search(r"[<>]", m[f])]
    if bad: die(f"{slug}: '<' or '>' in {bad} (YouTube rejects them)")
    if len(m["title"]) > 100 or len(m["description"].encode()) > 5000: die(f"{slug}: title/description too long")
    if sum(len(t) + 1 for t in m["tags"]) > 500: die(f"{slug}: tags too long")


def slugs_for(sets):
    pats = [p for s in sets for p in SETS[s]]
    found = []
    for p in pats:
        found += sorted(os.path.basename(x)[:-4] for x in glob.glob(f"{ROOT}/work/youtube/{p}.txt"))
    return list(dict.fromkeys(found))


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--auth", metavar="CLIENT_SECRET.json")
    ap.add_argument("--set", action="append", choices=list(SETS), help="which videos (repeatable)")
    ap.add_argument("--slug", action="append", help="a single text slug")
    ap.add_argument("--apply", action="store_true", help="make the changes (default: dry run)")
    ap.add_argument("--playlist-privacy", default="private", choices=["private", "unlisted", "public"],
                    help="for playlists that have to be created")
    ap.add_argument("--no-synthetic-flag", action="store_true", help="don't set the altered/synthetic content flag")
    a = ap.parse_args()
    if a.auth: return auth(a.auth)
    slugs = a.slug or slugs_for(a.set or die("give --set or --slug"))
    if not slugs: die("no text files matched")
    texts = {s: parse(f"{ROOT}/work/youtube/{s}.txt") for s in slugs}
    for s, m in texts.items(): check(m, s)
    state = json.load(open(STATE)) if os.path.exists(STATE) else {}

    api = API()
    ch = api.call("GET", "channels", params=dict(part="contentDetails,snippet", mine="true"))["items"][0]
    print(f"channel: {ch['snippet']['title']}")
    uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    by_title = {}
    for it in api.paged("playlistItems", part="snippet", playlistId=uploads):
        by_title.setdefault(it["snippet"]["title"].strip().lower(), []).append(it["snippet"]["resourceId"]["videoId"])

    plan, problems = [], []
    for s in slugs:
        vid = state.get(s)
        if not vid:
            cands = by_title.get(s.lower(), [])
            if len(cands) == 1: vid = cands[0]
            elif not cands: problems.append(f"{s}: no upload titled '{s}'"); continue
            else: problems.append(f"{s}: {len(cands)} uploads titled '{s}': {cands}"); continue
        plan.append((s, vid))
    print(f"{len(plan)}/{len(slugs)} matched")
    for p in problems: print("  !", p)
    if not a.apply:
        for s, vid in plan: print(f"  {s:24s} -> {vid}  {texts[s]['title'][:60]}  [{texts[s]['playlist']}]")
        print("dry run: nothing changed (use --apply)")
        return

    plists = {p["snippet"]["title"]: p["id"] for p in api.paged("playlists", part="snippet", mine="true")}
    members = {}
    done = 0
    for s, vid in plan:
        m = texts[s]
        try:
            cur = api.call("GET", "videos", params=dict(part="snippet,status", id=vid))["items"][0]
            sn, st = cur["snippet"], cur["status"]
            sn.update(title=m["title"], description=m["description"], tags=m["tags"], categoryId=CATEGORY_MUSIC,
                      defaultLanguage="sa", defaultAudioLanguage="sa")
            st["selfDeclaredMadeForKids"] = False
            if not a.no_synthetic_flag: st["containsSyntheticMedia"] = True
            try:
                api.call("PUT", "videos", params=dict(part="snippet,status"), json=dict(id=vid, snippet=sn, status=st))
            except RuntimeError as e:
                if "containsSyntheticMedia" in str(e) or "400" in str(e) and not a.no_synthetic_flag:
                    st.pop("containsSyntheticMedia", None)
                    print(f"  (synthetic-content flag rejected by the API: {e}; set it in Studio)")
                    api.call("PUT", "videos", params=dict(part="snippet,status"), json=dict(id=vid, snippet=sn, status=st))
                else:
                    raise
            pl = m["playlist"]
            if pl:
                if pl not in plists:
                    r = api.call("POST", "playlists", params=dict(part="snippet,status"), json=dict(
                        snippet=dict(title=pl, defaultLanguage="sa"), status=dict(privacyStatus=a.playlist_privacy)))
                    plists[pl] = r["id"]; print(f"  created playlist '{pl}' ({a.playlist_privacy})")
                if pl not in members:
                    members[pl] = {i["snippet"]["resourceId"]["videoId"] for i in
                                   api.paged("playlistItems", part="snippet", playlistId=plists[pl])}
                if vid not in members[pl]:
                    api.call("POST", "playlistItems", params=dict(part="snippet"), json=dict(snippet=dict(
                        playlistId=plists[pl], resourceId=dict(kind="youtube#video", videoId=vid))))
                    members[pl].add(vid)
            state[s] = vid
            os.makedirs(os.path.dirname(STATE), exist_ok=True)
            json.dump(state, open(STATE, "w"), indent=1)
            done += 1
            print(f"  ok  {s:24s} {vid}  {cur['status']['privacyStatus']}", flush=True)
        except RuntimeError as e:
            print(f"  FAIL {s}: {e}")
            if "quota" in str(e).lower(): print("quota exhausted; rerun tomorrow, finished ones are remembered"); break
    print(f"{done}/{len(plan)} updated")


if __name__ == "__main__":
    main()
