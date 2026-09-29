#!/usr/bin/env python3
"""YouTube upload text for built videos: title, description (with chapters), tags, playlist.

    python3 pipeline/youtube_meta.py stotras/ganesha/ganeshabhujangam [...]    # or --all

Writes work/youtube/<slug>.txt (copy-paste blocks) and work/youtube/metadata.tsv (one row per
video; descriptions quoted so spreadsheets keep the line breaks). Title-slide facts come from
video.text_info, so the upload text always matches the video. Per-text introductions come from
pipeline/youtube_blurbs.tsv (stotra id <TAB> text).
"""
import argparse, csv, glob, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import video                                               # noqa: E402  (also chdir()s to the repo)
from config import STOTRA_SANGRAHAH, PUJA_VIDHANAM          # noqa: E402
from video import SL                                       # noqa: E402

TITLE_MAX, DESC_MAX, TAGS_MAX = 100, 5000, 500
CREDITS = """Text: Stotra Saṁhitā — https://stotrasamhita.github.io
Source files: {srcurl}
Chant: AI-generated with Vāgdhenu (https://github.com/prathoshap/vagdhenu), laukika (non-Vedic) chanting. \
Occasional slips in pronunciation or metre are possible — corrections are welcome in the comments.
Production: https://github.com/stotrasamhita/vani
Śruti drone: https://shanmukhapriya.com/tambura-sruthi"""
BLURBS = {r[0]: r[1] for r in (l.rstrip("\n").split("\t", 1) for l in
          open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "youtube_blurbs.tsv"), encoding="utf-8"))
          if len(r) == 2 and r[0] != "stotra"}   # hand-written introductions, one per text
PLAYLISTS = {"stotras": "Stotras — {deity}", "kathas": "Vrata kathās", "ekadashi": "Ekādaśī māhātmyam"}


def plain(s):
    """IAST -> plain ASCII for search-friendly titles/tags (Gaṇeśa -> Ganesha)."""
    for a, b in [("ā", "a"), ("ī", "i"), ("ū", "u"), ("ṛ", "ri"), ("ṝ", "ri"), ("ḷ", "l"), ("ṃ", "m"), ("ṁ", "m"),
                 ("ḥ", "h"), ("ṅ", "n"), ("ñ", "n"), ("ṭ", "t"), ("ḍ", "d"), ("ṇ", "n"), ("ś", "sh"), ("ṣ", "sh"),
                 ("Ā", "A"), ("Ī", "I"), ("Ū", "U"), ("Ś", "Sh"), ("Ṣ", "Sh"), ("Ṛ", "Ri")]:
        s = s.replace(a, b)
    return s


def meta_for(stotra, shard):
    clips = sorted((c for c in shard if c["stotra"] == stotra), key=lambda c: c["seq"])
    T = video.text_info(stotra, clips)
    slug = stotra.rsplit("/", 1)[1]
    coll = stotra.split("/")[0]
    mp4 = f"out/video/{stotra}/{slug}.mp4"
    chf = f"out/video/{stotra}/{slug}_chapters.txt"
    if os.path.exists(chf):
        chapters = open(chf, encoding="utf-8").read().splitlines()
    else:                                                  # no video yet: same timeline from the mix
        mix = (glob.glob(f"out/mp3/{stotra}/*_sruthi_m16.json") + glob.glob(f"out/mp3/{stotra}_FALLBACK/*_sruthi_m16.json"))[0]
        tm = json.load(open(mix))
        chapters = [f"{video.ts(t)} {n}" for t, n in
                    video.chapter_list(clips, T["shown"], T["rom"], tm["lead_s"], tm["total_s"])]
    en = T["meta"].get("wiki_title") or plain(T["rom"])
    if coll == "ekadashi":                                 # search-friendly: "Nirjala Ekadashi Mahatmyam (Jyeshtha Shukla)"
        name = re.sub(r"^\d+", "", slug)
        special = {"unmilani": "Unmilani Vrata", "pakshavardhini": "Pakshavardhini Ekadashi Mahatmyam",
                   "jagaranamahima": "Ekadashi Jagarana Mahima", "dvadashi": "Shravana Dvadashi Vrata"}
        parts = [plain(x).capitalize() for x in T["rom"].split("-")[:2]]
        en = special.get(name) or f"{name.capitalize()} Ekadashi Mahatmyam ({' '.join(parts)})"
    comp_en = T["meta"].get("composer", "") if T["composer"] else ""
    iast = lambda d: SL.cap(SL.iast(d))

    # title: search-friendly English, Devanāgarī, composer; drop parts if too long
    for parts in ([en, T["title"], comp_en, "Sanskrit chant with lyrics"], [en, T["title"], "Sanskrit chant with lyrics"],
                  [en, T["title"]]):
        head = " · ".join(p for p in parts[:2] if p)
        title = head + (f" – {parts[2]}" if len(parts) > 3 and parts[2] else "") + (f" | {parts[-1]}" if len(parts) > 2 else "")
        if len(title) <= TITLE_MAX: break

    # layout (user, 2026-09-28): introduction, what the video is, title/composer/metre, chapters, credits
    lines = ([BLURBS[stotra], ""] if stotra in BLURBS else []) + \
            ["Chanted verse by verse, with the text on screen in Devanāgarī and IAST.", "",
             f"{T['title']} · {T['rom']}"]
    if T["composer"]: lines.append(f"{T['composer']} · {iast(T['composer'])}")
    if T["speaker"]: lines.append(f"{T['speaker']} · {iast(T['speaker'])}")
    if T["chandas"]:
        lines.append(f"छन्दः — {T['chandas']} · Chandaḥ — " + " · ".join(iast(m) for m in T["chandas"].split(" · ")))
    if T["source"]: lines.append(f"मूलम् — {T['source']} · Mūlam — {iast(T['source'])}")
    lines += [""]
    repo = "stotra-sangrahah" if coll == "stotras" else "puja-vidhanam"
    root = STOTRA_SANGRAHAH if coll == "stotras" else PUJA_VIDHANAM
    srcurl = f"https://github.com/stotrasamhita/{repo}/blob/master/" + os.path.relpath(T["src"], root)
    deity = T["meta"].get("deity", "")
    tail = ["", CREDITS.format(srcurl=srcurl), "",
            " ".join(f"#{h}" for h in dict.fromkeys(["Sanskrit", plain(deity).replace(" ", "") if deity else "",
                                                       {"stotras": "Stotra", "ekadashi": "Ekadashi"}.get(coll, "Katha")]) if h)]
    # chapters: thin them if the description would be too long (YouTube needs >= 3, each >= 10 s)
    step = 1
    while True:
        ch = [chapters[0]] + chapters[1:][step - 1::step]
        desc = "\n".join(lines + ["Chapters:"] + ch + tail)
        if len(desc) <= DESC_MAX or step > 50: break
        step += 1

    tags, n = [], 0
    for t in dict.fromkeys([en, T["title"], plain(T["rom"]), T["rom"], comp_en, plain(deity) if deity else "",
                            "Sanskrit", {"stotras": "stotra", "ekadashi": "Ekadashi"}.get(coll, "vrata katha"),
                            "Padma Purana" if coll == "ekadashi" else "", "Sanskrit chanting",
                            "lyrics", "IAST"] +
                           [plain(iast(m)) for m in (T["chandas"] or "").split(" · ") if m]):
        if t and n + len(t) + 1 <= TAGS_MAX: tags.append(t); n += len(t) + 1
    playlist = PLAYLISTS.get(coll, coll).format(deity=plain(deity) or "other")
    return dict(stotra=stotra, file=os.path.abspath(mp4), title=title, description=desc, tags=", ".join(tags),
                playlist=playlist, category="Music", language="Sanskrit",
                notes="Altered or synthetic content: Yes (AI-generated voice). Made for kids: No."
                      + (f" Chapters thinned to every {step}th verse." if step > 1 else ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stotras", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--shard", default="work/bulk.json")
    a = ap.parse_args()
    shard = json.load(open(a.shard, encoding="utf-8"))
    todo = a.stotras or sorted({c["stotra"] for c in shard})           # videos not built yet included
    os.makedirs("work/youtube", exist_ok=True)
    rows = [meta_for(s, shard) for s in todo]
    for r in rows:
        slug = r["stotra"].rsplit("/", 1)[1]
        with open(f"work/youtube/{slug}.txt", "w", encoding="utf-8") as f:
            f.write(f"FILE{'' if os.path.exists(r['file']) else ' (video not built yet)'}\n{r['file']}\n\nTITLE ({len(r['title'])}/100)\n{r['title']}\n\n"
                    f"DESCRIPTION ({len(r['description'])}/5000)\n{r['description']}\n\n"
                    f"TAGS ({len(r['tags'])}/500)\n{r['tags']}\n\nPLAYLIST\n{r['playlist']}\n\n"
                    f"CATEGORY / LANGUAGE\n{r['category']} / {r['language']}\n\nNOTES\n{r['notes']}\n")
    with open("work/youtube/metadata.tsv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter="\t", quoting=csv.QUOTE_MINIMAL)
        w.writeheader(); w.writerows(rows)
    print(f"{len(rows)} videos -> work/youtube/<slug>.txt + work/youtube/metadata.tsv")


if __name__ == "__main__":
    main()
