#!/usr/bin/env python3
"""Build a text's video: title slide + one slide per verse over its drone-mixed _full mp3.

    python3 pipeline/video.py stotras/ganesha/ganeshabhujangam [--audio _sruthi_m16]

Timeline (from the mix's timing sidecar and the exact cached verse durations):
  title slide during the drone's empty lead-in cycle; verse k's slide switches in 0.4 s before
  verse k starts (inside the 0.8 s pause), with 0.35 s fade-out/fade-in through black, so the
  new verse is fully visible as its chant begins. Boundaries are placed on whole frames of the
  global timeline, so there is no drift. The last slide fades out with the drone's tail.
Texts with a word split (Gītā chapters) show it on each verse slide (slides.split_verse_tex).
Palettes: title and colophon slides maroon, verse slides alternate aubergine / indigo. An uvāca
("X उवाच") is chanted before its verse and shown in gold above it on the same slide.
Outputs out/video/<stotra>/<slug>.mp4 and <slug>_chapters.txt (YouTube chapter list).
"""
import argparse, glob, json, os, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(os.path.dirname(HERE), "slides"))
from config import STOTRA_SANGRAHAH, FFMPEG                # noqa: E402
from build_shard import build, parse_meta, DECLARED        # noqa: E402
import slides as SL                                          # noqa: E402

STOTRAS = f"{STOTRA_SANGRAHAH}/stotras"
FPS, FADE, LEAD_SWITCH, PAUSE = 25, 0.35, 0.4, 0.8


def source_tex(stotra):
    coll, *rest = stotra.split("/")
    assert coll == "stotras", "only stotra-sangrahah texts for now"
    deity, slug = rest
    for p in glob.glob(f"{STOTRAS}/{deity}/*.tex"):
        if re.sub(r"[^a-z0-9]+", "", os.path.splitext(os.path.basename(p))[0].lower()) == slug:
            return p
    raise SystemExit(f"no source .tex for {stotra}")


def ts(t):
    return f"{int(t // 60)}:{int(t % 60):02d}"


def text_info(stotra, clips):
    """Everything the title slide (and the YouTube text) shows for one text, from the source
    file's heading/metadata, slides/names.tsv and the clips' detected metres."""
    src = clips[0].get("src") or source_tex(stotra)
    tex = open(src, encoding="utf-8").read()
    piece = dict(part=clips[0].get("part"), after=clips[0].get("after"))   # a piece of the file (Gītā chapter)
    shown = {c["seq"]: c.get("display") for c in build(src, 60, 24, **piece)}   # by position: ids depend on the corpus group; prose has none
    split = ({c["seq"]: c.get("display") for c in build(clips[0]["split_src"], 60, 24, **piece)}
             if clips[0].get("split_src") else {})             # word-split text, line-aligned with src (checked: same seqs)
    meta = parse_meta(tex)
    X = SL.TEXTS.get(stotra)                                  # texts.tsv: per-text presentation (Gītā set)
    if X:
        meta.update({k: X[v] for k, v in (("wiki_title", "english"), ("source", "source"), ("composer", "composer")) if X[v]})
    m = next((m for pat in (r"\\sect\{([^}]*)\}", r"\\chapt\{([^}]*)\}", r"\\dnsub\{([^}]*)\}")
              if (m := re.search(pat, tex))), None)          # heading macro varies across files
    title = X["title"] if X else m.group(1).strip() if m else None
    if stotra in SL.TITLES:                            # per-text override (e.g. heading is just "कथा")
        title, meta["wiki_title"] = SL.TITLES[stotra]
    if stotra in SL.TEXT_SOURCES: meta["source"] = SL.TEXT_SOURCES[stotra]
    if stotra.startswith("ekadashi/"): meta.setdefault("source", "Padma Puranam")   # all chapters are Padma Purāṇa
    if not title: raise SystemExit(f"{stotra}: no heading in {src}; add a 'title' row to slides/names.tsv")
    # the speaker (vakta) is credited when known -- the author (e.g. Vyāsa) was only reporting
    who, role = SL.COMPOSERS.get(meta.get("composer", ""), (None, None))
    vakta = SL.VAKTAS.get(meta.get("vakta", "")) or (who if role == "speaker" else None)
    speaker = SL.krta(vakta, title) if vakta else None
    composer = who if who and role != "speaker" and not vakta else None
    source = SL.SOURCES.get(meta.get("source", ""))
    decl = DECLARED.get(meta.get("chandas", "").lower(), "")
    dets = Counter(c["detected"] for c in clips if c["detected"] and c["flag"] not in ("COLOPHON", "UVACA"))
    dom, k = dets.most_common(1)[0] if dets else ("", 0)
    rom = SL.title_iast(title, meta.get("wiki_title", ""))
    above, below = (X["above"], X["below"]) if X else ("", "")
    # verse-slide header: title · chapter (e.g. साङ्ख्ययोगः · द्वितीयोऽध्यायः)
    head, head_rom = (f"{title} · {below}", f"{rom} · {SL.cap(SL.iast(below))}") if below else (title, rom)
    # metre line: the declared header; else the detected metres, most frequent first (<= 3)
    if decl in SL.CHANDAS: chandas = SL.CHANDAS[decl]
    else:
        verses = [c for c in clips if c["flag"] not in ("COLOPHON", "UVACA")]
        used = [m for m, _ in dets.most_common() if m in SL.CHANDAS]
        known = sum(1 for c in verses if c["detected"] in SL.CHANDAS)
        chandas = (" · ".join(SL.CHANDAS[m] for m in used)
                   if 0 < len(used) <= 3 and known >= 0.9 * len(verses) else None)   # don't show a partial list

    return dict(src=src, tex=tex, shown=shown, split=split, meta=meta, title=title, rom=rom,
                composer=above or composer, speaker=below or speaker, source=source, chandas=chandas,
                head=head, head_rom=head_rom)


def chapter_list(clips, shown, rom, lead, total):
    """YouTube chapters: title at 0:00, then each verse (an uvāca starts its verse's chapter) and
    the colophon; chapters shorter than 10 s are folded into the next (YouTube's minimum)."""
    chapters, t, uv = [(0.0, rom)], lead, None
    for c in clips:
        dur = sf.info(c["out"]).duration
        if c["flag"] == "UVACA":
            uv = (" ".join(shown[c["seq"]]), t); t += dur + PAUSE; continue
        m = re.search(r"v(\d+)$", c["id"]); num = int(m.group(1)) if m else None
        chapters.append((uv[1] if uv else t, "Iti (colophon)" if c["flag"] == "COLOPHON" else
                         f"Verse {num}" if num else SL.cap(SL.iast(uv[0])) if uv else "Verse"))
        uv = None; t += dur + PAUSE
    merged = []
    for i, (t_, name) in enumerate(chapters):
        nxt = chapters[i + 1][0] if i + 1 < len(chapters) else total
        if merged and merged[-1][2]:                     # previous was too short: fold into this one
            t_, name = merged[-1][0], f"{merged[-1][1]} · {name}"; merged.pop()
        merged.append((t_, name, nxt - t_ < 10))
    return [(t_, name) for t_, name, _ in merged]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stotra")
    ap.add_argument("--audio", default="_sruthi_m16", help="suffix of the drone mix to use")
    ap.add_argument("--shard", default="work/bulk.json")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--mp3root", default="out/mp3")
    ap.add_argument("--outroot", default="out/video")
    a = ap.parse_args()
    slug = a.stotra.rsplit("/", 1)[1]

    clips = sorted((c for c in json.load(open(a.shard, encoding="utf-8")) if c["stotra"] == a.stotra),
                   key=lambda c: c["seq"])
    T = text_info(a.stotra, clips)
    shown, title, rom = T["shown"], T["title"], T["rom"]
    composer, speaker, source, chandas = T["composer"], T["speaker"], T["source"], T["chandas"]
    head, head_rom = T["head"], T["head_rom"]
    SL.SOURCE_REPO = {"gita": "gita", "gita-padma": "gita", "kathas": "puja-vidhanam",
                      "ekadashi": "puja-vidhanam"}.get(a.stotra.split("/")[0], "stotra-sangrahah")

    mixdir = next(d for d in (f"{a.mp3root}/{a.stotra}", f"{a.mp3root}/{a.stotra}_FALLBACK") if os.path.isdir(d))
    audio = next(f for f in glob.glob(f"{mixdir}/*_full*{a.audio}.mp3"))
    timing = json.load(open(audio[:-4] + ".json"))
    lead, total = timing["lead_s"], timing["total_s"]

    # slide list: (png, start_s). Verse k starts at lead + sum(prev clip durations + pauses); an
    # uvāca clip gets no slide of its own: it is shown on (and starts) the following verse's slide.
    out = f"{a.outroot}/{a.stotra}"; work = f"{out}/slides"
    os.makedirs(work, exist_ok=True)
    frame, vpal = SL.FRAME_PALETTE, SL.VERSE_PALETTES
    jobs, starts, t, nv, uv = [], [], lead, 0, None
    jobs.append((f"{work}/000_title.png", SL.title_tex(frame, title, composer, chandas, rom, speaker=speaker, source=source))); starts.append(0.0)
    for i, c in enumerate(clips, 1):
        dur = sf.info(c["out"]).duration
        if c["flag"] == "UVACA":
            uv = (" ".join(shown[c["seq"]]), t); t += dur + PAUSE; continue
        m = re.search(r"v(\d+)$", c["id"]); num = int(m.group(1)) if m else None
        t0 = uv[1] if uv else t
        if c["flag"] == "COLOPHON":
            jobs.append((f"{work}/{i:03d}_{c['id']}.png", SL.colophon_tex(frame, head, " ".join(shown[c["seq"]]), head_rom)))
        elif T["split"].get(c["seq"]):
            jobs.append((f"{work}/{i:03d}_{c['id']}.png",
                         SL.split_verse_tex(vpal[nv % 2], head, head_rom, shown[c["seq"]], T["split"][c["seq"]], num,
                                            uvaca=uv[0] if uv else None)))
            nv += 1
        else:
            jobs.append((f"{work}/{i:03d}_{c['id']}.png",
                         SL.verse_tex(vpal[nv % 2], head, shown[c["seq"]], num, head_rom, uvaca=uv[0] if uv else None)))
            nv += 1
        starts.append(max(t0 - LEAD_SWITCH, 0.0))
        uv = None; t += dur + PAUSE
    with ThreadPoolExecutor(a.jobs) as ex:
        list(ex.map(lambda j: SL.render(j[1], j[0], work), jobs))

    # frame-exact segments, then concat + audio
    edges = [round(s * FPS) for s in starts] + [round(total * FPS)]
    fd = round(FADE * FPS)
    segs = []
    def seg(k):
        n = edges[k + 1] - edges[k]
        fin = round(0.8 * FPS) if k == 0 else fd
        fout = round(1.5 * FPS) if k == len(jobs) - 1 else fd
        dst = f"{work}/seg_{k:03d}.mp4"
        subprocess.run([FFMPEG, "-loglevel", "error", "-y", "-loop", "1", "-framerate", str(FPS), "-i", jobs[k][0],
                        "-frames:v", str(n), "-vf", f"fade=t=in:s=0:n={fin},fade=t=out:s={n - fout}:n={fout},format=yuv420p",
                        "-c:v", "libx264", "-preset", "medium", "-tune", "stillimage", "-crf", "18",
                        "-r", str(FPS), dst], check=True)
        return dst
    with ThreadPoolExecutor(a.jobs) as ex:
        segs = list(ex.map(seg, range(len(jobs))))
    lst = f"{work}/segments.txt"
    open(lst, "w").write("".join(f"file '{os.path.abspath(s)}'\n" for s in segs))
    mp4 = f"{out}/{slug}.mp4"
    subprocess.run([FFMPEG, "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-i", audio,
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-movflags", "+faststart", "-t", f"{total:.3f}", mp4], check=True)
    for s in segs: os.remove(s)
    os.remove(lst)
    chapters = chapter_list(clips, shown, rom, lead, total)
    with open(f"{out}/{slug}_chapters.txt", "w", encoding="utf-8") as f:
        f.writelines(f"{ts(t)} {name}\n" for t, name in chapters)
    print(f"{mp4}  ({total/60:.1f} min, {len(jobs)} slides)")


if __name__ == "__main__":
    main()
