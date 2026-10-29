#!/usr/bin/env python3
"""Apply work/youtube/<slug>.txt to videos already uploaded (drag-dropped) to YouTube Studio.

    python3 pipeline/youtube_apply.py --auth CLIENT_SECRET.json        # once: sign in, saves a token
    python3 pipeline/youtube_apply.py --set gita                        # dry run: which upload matches which text
    python3 pipeline/youtube_apply.py --set gita --apply                # update title/description/tags (add --playlists to also add to playlists)

An upload is matched by its Studio title, which Studio sets from the file name (chapter02.mp4 ->
"chapter02"). Applied matches are remembered in work/youtube/applied.json (slug -> video id), so the run
can be repeated after a quota stop or a fix. Privacy is left alone unless --public is given.
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
SCOPE = "https://www.googleapis.com/auth/youtube https://www.googleapis.com/auth/youtube.force-ssl"   # force-ssl: captions
STATE = f"{ROOT}/work/youtube/applied.json"
THUMBS = f"{ROOT}/work/youtube/thumbs.json"   # slug -> hash of the thumbnail already set
CATEGORY_MUSIC = "10"
EXTRA_PLAYLISTS = [(r"chapter\d\d|gita-sampurna", "Mahabharatam"), (r"mahatmyam\d\d|gita-padma-sampurna", "Padma Puranam")]   # besides the text's own playlist
PLAYLIST_ALIAS = {"Gītā-māhātmyam (Padma Purāṇa)": "Padma Puranam",
                  **{f"{g} Stotram": "Navagraha Stotram" for g in
                     ("Rahu", "Ketu", "Budha", "Brihaspati", "Shukra", "Shanaishchara", "Angaraka", "Chandra")}}   # one playlist for the grahas   # one playlist for the Padma māhātmyam, chapters and compilation
TAIL = ("Sanskrit chanting with the text on screen in Devanāgarī and IAST. AI-generated with Vāgdhenu (laukika, non-Vedic). "
        "Text: https://stotrasamhita.github.io")
PLAYLIST_DESC = {
    "Śrīmad Bhagavad Gītā (complete)":
        "The Śrīmad Bhagavad Gītā chanted verse by verse: the dhyānam, all eighteen chapters, the closing māhātmyam, the Varāha-purāṇa "
        "Gītā-māhātmyam and the Gītārtha-saṅgraha, plus the complete parāyaṇam in one video.\n\n" + TAIL,
    "Mahabharatam":
        "Texts from the Mahābhārata: the Bhagavad Gītā chapters (Bhīṣma-parva) and the complete Gītā as one video, the Mahābhārata "
        "dhyānam and the pativratā-māhātmya (Satyavān–Sāvitrī) story.\n\n" + TAIL,
    "Padma Puranam":
        "The Gītā-māhātmyam from the Padma Purāṇa (Uttara-khaṇḍa, chapters 175–192): one video for the māhātmyam of each of the "
        "eighteen chapters of the Gītā, and the complete māhātmyam as one video.\n\n" + TAIL,
    "Skanda Puranam": "Stories and vratas from the Skanda Purāṇa, chanted in Sanskrit.\n\n" + TAIL,
    "Valmiki Ramayanam": "Texts from Vālmīki's Rāmāyaṇa, chanted in Sanskrit.\n\n" + TAIL,
    "Ramayanam": "Rāmāyaṇa texts and stotras, chanted in Sanskrit.\n\n" + TAIL,
    "Surya Stotram": "Hymns to Sūrya, chanted in Sanskrit.\n\n" + TAIL,
    "Ashtottara Shatanama Stotram": "Stotras of a hundred and eight names (aṣṭottaraśatanāma) and the aṣṭottaraśata divyasthāna-nāmas, chanted in Sanskrit.\n\n" + TAIL,
    "Nadi Stotram": "Hymns to the sacred rivers (Gaṅgā, Yamunā, Narmadā, Kāverī, Godāvarī, Triveṇī), chanted in Sanskrit.\n\n" + TAIL,
    "Other Stotras": "Stotras to various deities and sages, chanted in Sanskrit.\n\n" + TAIL,
    "Adhyatma Ramayana Stotram": "The stotras, saṃvādas and upadeśas of the Adhyātma Rāmāyaṇa (Brahmāṇḍa Purāṇa), chanted in Sanskrit.\n\n" + TAIL,
    "Shatanama Stotram": "Stotras of a hundred and eight names (aṣṭottaraśatanāma), chanted in Sanskrit.\n\n" + TAIL,
    "Rama Stotram": "Hymns to Śrī Rāma, chanted in Sanskrit.\n\n" + TAIL,
    "Shakti Stotram": "Hymns to the Goddess, chanted in Sanskrit.\n\n" + TAIL,
    "Vrata Katha": "Vrata kathās and upākhyānas, chanted in Sanskrit.\n\n" + TAIL,
    "Ganesha Stotram": "Hymns to Gaṇeśa, chanted in Sanskrit.\n\n" + TAIL,
    "Bhujangam": "Stotras in the bhujaṅgaprayāta metre, chanted in Sanskrit.\n\n" + TAIL,
    "Navagraha Stotram": "Hymns to the nine grahas (Sūrya, Candra, Aṅgāraka, Budha, Bṛhaspati, Śukra, Śani, Rāhu, Ketu), chanted in Sanskrit.\n\n" + TAIL,
    "Sahasranama Stotram": "Sahasranāma stotras, the thousand names of a deity, chanted in Sanskrit.\n\n" + TAIL,
    "Srimad Bhagavatam": "Stotras and episodes from the Śrīmad Bhāgavatam, chanted in Sanskrit.\n\n" + TAIL,
    "Adi Shankara Kriti": "Stotras composed by Ādi Śaṅkarācārya, chanted in Sanskrit.\n\n" + TAIL,
    "Ekādaśī māhātmyam": "The māhātmyam of the Ekādaśī vratas, chanted in Sanskrit.\n\n" + TAIL,
}
def playlist_desc(t):
    if t in PLAYLIST_DESC: return PLAYLIST_DESC[t]
    if t.endswith(" Stotram"): return f"Hymns to {t[:-8]}, chanted in Sanskrit.\n\n" + TAIL


THUMB_MAX = 2 * 1024 * 1024
SETS = {
    "gita": ["00dhyanam", "chapter??", "19mahatmyam", "20varahamahatmyam", "21gitarthasangraha", "mahatmyam??"],
    "compilations": ["gita-sampurna", "gita-padma-sampurna"],
    "stotras": ["*"],                                  # everything else
}


def die(msg):
    sys.exit(f"error: {msg}")


# ---------------------------------------------------------------- OAuth (installed-app loopback flow)
def auth(secret_path):
    cfg = json.load(open(secret_path))
    cfg = cfg.get("installed") or cfg.get("web") or die("not an OAuth client file")
    port = int(os.environ.get("AUTH_PORT", 8765))
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
        for attempt in range(8):
            try:
                r = requests.post(self.tok["token_uri"], timeout=15, data=dict(
                    client_id=self.tok["client_id"], client_secret=self.tok["client_secret"],
                    refresh_token=self.tok["refresh_token"], grant_type="refresh_token"))
                break
            except requests.RequestException:
                if attempt == 7: raise
                time.sleep(3)
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
    skip = {os.path.basename(x)[:-4] for g in ("gita", "compilations") for p in SETS[g] for x in glob.glob(f"{ROOT}/work/youtube/{p}.txt")}
    for p in pats:
        found += sorted(os.path.basename(x)[:-4] for x in glob.glob(f"{ROOT}/work/youtube/{p}.txt")
                        if p != "*" or os.path.basename(x)[:-4] not in skip)
    return list(dict.fromkeys(found))


def fingerprint(sn, st):
    """What matters for 'is an update needed': tags as a set; the synthetic flag is write-only in practice."""
    sn = dict(sn, tags=sorted(sn.get("tags", [])))
    st = {k: v for k, v in st.items() if k != "containsSyntheticMedia"}
    return json.dumps([sn, st], sort_keys=True)


def norm(t):
    return re.sub(r"[\s_-]+", "", t.strip().lower())


def title_slide(slug):
    own = f"{ROOT}/work/youtube/thumb_{slug}.png"          # a hand-made thumbnail wins over the title slide
    if os.path.exists(own): return own
    hit = sorted(glob.glob(f"{ROOT}/out/video/**/{slug}/slides/000_title.png", recursive=True))
    return hit[0] if hit else None


def thumbnail_bytes(png):
    from PIL import Image
    import io
    im = Image.open(png).convert("RGB").resize((1280, 720), Image.LANCZOS)
    for q in (95, 90, 85, 75):
        buf = io.BytesIO(); im.save(buf, "JPEG", quality=q, optimize=True)
        if buf.tell() < THUMB_MAX: return buf.getvalue()
    die(f"{png}: thumbnail over 2 MB")


def set_thumbnail(api, vid, slug):
    import hashlib
    png = title_slide(slug)
    if not png: raise RuntimeError(f"no title slide for {slug}")
    done = json.load(open(THUMBS)) if os.path.exists(THUMBS) else {}
    key = hashlib.sha1(open(png, "rb").read()).hexdigest() + ":" + vid
    if done.get(slug) == key: return False
    r = api.s.post("https://www.googleapis.com/upload/youtube/v3/thumbnails/set", params=dict(videoId=vid),
                   data=thumbnail_bytes(png), headers={"Content-Type": "image/jpeg"}, timeout=120)
    if r.status_code >= 400: raise RuntimeError(f"thumbnail {r.status_code}: {r.text[:300]}")
    done[slug] = key
    json.dump(done, open(THUMBS, "w"), indent=1)
    return True


def set_playlist_descriptions(api, plists, only=None):
    for p in api.paged("playlists", part="snippet", mine="true"):
        t = p["snippet"]["title"]
        d = playlist_desc(t)
        if d and (only is None or t in only) and p["snippet"].get("description") != d:
            sn = dict(title=t, description=d)
            api.call("PUT", "playlists", params=dict(part="snippet"), json=dict(id=p["id"], snippet=sn))
            print(f"  described playlist '{t}'")


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--auth", metavar="CLIENT_SECRET.json")
    ap.add_argument("--set", action="append", choices=list(SETS), help="which videos (repeatable)")
    ap.add_argument("--slug", action="append", help="a single text slug")
    ap.add_argument("--apply", action="store_true", help="make the changes (default: dry run)")
    ap.add_argument("--playlist-privacy", default="private", choices=["private", "unlisted", "public"],
                    help="for playlists that have to be created (the channel's existing ones are public)")
    ap.add_argument("--playlists", action="store_true",
                    help="also add each video to its playlists (50 quota units per video per playlist; off by default -- add them in Studio, or catch up later with this flag)")
    ap.add_argument("--only-playlists", help="with --playlists: only these playlists (comma-separated titles); others are neither created nor filled")
    ap.add_argument("--public", action="store_true", help="make private videos public (unlisted ones are left alone; default: privacy untouched)")
    ap.add_argument("--thumbnails", action="store_true", help="set each video's thumbnail to its title slide (1280x720 JPEG)")
    ap.add_argument("--playlist-descriptions", action="store_true", help="set the descriptions of the channel's playlists (PLAYLIST_DESC)")
    ap.add_argument("--v2", action="store_true", help="match uploads titled '<slug>_v2' (rebuilt replacements), ignoring the recorded id; the old id is kept as '<slug>@old'")
    ap.add_argument("--no-synthetic-flag", action="store_true", help="don't set the altered/synthetic content flag")
    a = ap.parse_args()
    if a.auth: return auth(a.auth)
    if a.playlist_descriptions and not (a.set or a.slug):
        return set_playlist_descriptions(API(), None)
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
        by_title.setdefault(norm(it["snippet"]["title"]), []).append(it["snippet"]["resourceId"]["videoId"])

    plan, problems = [], []
    for s in slugs:
        vid = None if a.v2 else state.get(s)
        if a.v2:
            cands = by_title.get(norm(s + "_v2"), [])
            if len(cands) == 1: vid = cands[0]
            else: problems.append(f"{s}: {len(cands)} uploads titled '{s}_v2'"); continue
        elif not vid:
            cands = by_title.get(norm(s)) or by_title.get(norm(texts[s]["title"]), [])   # or already retitled
            if len(cands) == 1: vid = cands[0]
            elif not cands: problems.append(f"{s}: no upload titled '{s}'"); continue
            else: problems.append(f"{s}: {len(cands)} uploads titled '{s}': {cands}"); continue
        plan.append((s, vid))
    print(f"{len(plan)}/{len(slugs)} matched")
    for p in problems: print("  !", p)
    if not a.apply:
        for s, vid in plan:
            if a.thumbnails: print(f"  thumbnail {s}: {title_slide(s)}")
            pls = [PLAYLIST_ALIAS.get(x, x) for x in texts[s]["playlist"].split(" | ") + [n for pat, n in EXTRA_PLAYLISTS if re.fullmatch(pat, s)]]
            print(f"  {s:24s} -> {vid}  {texts[s]['title'][:50]}  [{' + '.join(pls) if a.playlists else 'playlists skipped'}]")
        print("dry run: nothing changed (use --apply)")
        return

    plists = {p["snippet"]["title"]: p["id"] for p in api.paged("playlists", part="snippet", mine="true")}
    members = {}
    done = 0
    for s, vid in plan:
        m = texts[s]
        try:
            items = api.call("GET", "videos", params=dict(part="snippet,status", id=vid))["items"]
            if not items:
                print(f"  ! {s}: video {vid} no longer exists on the channel; skipped"); continue
            cur = items[0]
            sn, st = cur["snippet"], cur["status"]
            before = fingerprint(sn, st)
            sn.update(title=m["title"], description=m["description"], tags=m["tags"], categoryId=CATEGORY_MUSIC,
                      defaultLanguage="sa", defaultAudioLanguage="sa")
            st["selfDeclaredMadeForKids"] = False
            if a.public and st["privacyStatus"] == "private": st["privacyStatus"] = "public"   # unlisted stays unlisted
            if not a.no_synthetic_flag: st["containsSyntheticMedia"] = True
            try:
                if fingerprint(sn, st) != before or s not in state:
                    api.call("PUT", "videos", params=dict(part="snippet,status"), json=dict(id=vid, snippet=sn, status=st))
            except RuntimeError as e:
                if "containsSyntheticMedia" in str(e) or "400" in str(e) and not a.no_synthetic_flag:
                    st.pop("containsSyntheticMedia", None)
                    print(f"  (synthetic-content flag rejected by the API: {e}; set it in Studio)")
                    api.call("PUT", "videos", params=dict(part="snippet,status"), json=dict(id=vid, snippet=sn, status=st))
                else:
                    raise
            if a.v2 and state.get(s) not in (None, vid): state[s + "@old"] = state[s]
            state[s] = vid
            os.makedirs(os.path.dirname(STATE), exist_ok=True)
            json.dump(state, open(STATE, "w"), indent=1)
            pls = [PLAYLIST_ALIAS.get(x, x) for x in m["playlist"].split(" | ") + [n for pat, n in EXTRA_PLAYLISTS if re.fullmatch(pat, s)]]
            only = set(a.only_playlists.split(",")) if a.only_playlists else None
            for pl in (dict.fromkeys(x for x in pls if x and (only is None or x in only)) if a.playlists else ()):
                if pl not in plists:
                    r = api.call("POST", "playlists", params=dict(part="snippet,status"), json=dict(
                        snippet=dict(title=pl), status=dict(privacyStatus=a.playlist_privacy)))
                    plists[pl] = r["id"]; print(f"  created playlist '{pl}' ({a.playlist_privacy})"); members[pl] = set()
                    if playlist_desc(pl):
                        time.sleep(3)
                        try: set_playlist_descriptions(api, plists, only={pl})
                        except RuntimeError as e: print(f"  (description of '{pl}' not set: {e})")
                if pl not in members:
                    members[pl] = {i["snippet"]["resourceId"]["videoId"] for i in
                                   api.paged("playlistItems", part="snippet", playlistId=plists[pl])}
                if vid not in members[pl]:
                    for attempt in range(5):                      # a new playlist is not found for a few seconds
                        try:
                            api.call("POST", "playlistItems", params=dict(part="snippet"), json=dict(snippet=dict(
                                playlistId=plists[pl], resourceId=dict(kind="youtube#video", videoId=vid))))
                            break
                        except RuntimeError as e:
                            if "playlistNotFound" not in str(e) or attempt == 4: raise
                            time.sleep(4)
                    members[pl].add(vid)
            if a.thumbnails: set_thumbnail(api, vid, s)
            state[s] = vid
            os.makedirs(os.path.dirname(STATE), exist_ok=True)
            json.dump(state, open(STATE, "w"), indent=1)
            done += 1
            print(f"  ok  {s:24s} {vid}  {cur['status']['privacyStatus']}", flush=True)
        except RuntimeError as e:
            print(f"  FAIL {s}: {e}")
            if "quota" in str(e).lower(): print("quota exhausted; rerun tomorrow, finished ones are remembered"); break
    if a.playlist_descriptions: set_playlist_descriptions(api, plists)
    print(f"{done}/{len(plan)} updated")


if __name__ == "__main__":
    main()
