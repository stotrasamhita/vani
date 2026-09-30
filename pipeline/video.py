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
    h, m = divmod(int(t // 60), 60)
    return f"{h}:{m:02d}:{int(t % 60):02d}" if h else f"{m}:{int(t % 60):02d}"


def text_info(stotra, clips):
    """Everything the title slide (and the YouTube text) shows for one text, from the source
    file's heading/metadata, slides/names.tsv and the clips' detected metres."""
    src = clips[0].get("src") or source_tex(stotra)
    tex = open(src, encoding="utf-8").read()
    piece = dict(part=clips[0].get("part"), after=clips[0].get("after"), **clips[0].get("opts", {}))   # a piece of the file (Gītā chapter)
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
    dets = Counter(c["detected"] for c in clips if c["detected"] and c["flag"] not in ("COLOPHON", "UVACA", "HEADING"))
    dom, k = dets.most_common(1)[0] if dets else ("", 0)
    rom = SL.title_iast(title, meta.get("wiki_title", ""))
    above, below = (X["above"], X["below"]) if X else ("", "")
    # verse-slide header: title · chapter (e.g. साङ्ख्ययोगः · द्वितीयोऽध्यायः)
    head, head_rom = (f"{title} · {below}", f"{rom} · {SL.cap(SL.iast(below))}") if below else (title, rom)
    # metre line: the declared header; else the detected metres, most frequent first (<= 3)
    if decl in SL.CHANDAS: chandas = SL.CHANDAS[decl]
    else:
        verses = [c for c in clips if c["flag"] not in ("COLOPHON", "UVACA", "HEADING")]
        used = [m for m, _ in dets.most_common() if m in SL.CHANDAS]
        known = sum(1 for c in verses if c["detected"] in SL.CHANDAS)
        chandas = (" · ".join(SL.CHANDAS[m] for m in used)
                   if 0 < len(used) <= 3 and known >= 0.9 * len(verses) else None)   # don't show a partial list

    if X: chandas = None                                      # Gītā set: no metre line (user, 2026-09-29)
    return dict(src=src, tex=tex, shown=shown, split=split, meta=meta, title=title, rom=rom,
                composer=above or composer, speaker=below or speaker, source=source, chandas=chandas,
                head=head, head_rom=head_rom)


def fold_short(chapters, total):
    """Fold chapters shorter than 10 s (YouTube's minimum) into the next one."""
    merged = []
    for i, (t_, name) in enumerate(chapters):
        nxt = chapters[i + 1][0] if i + 1 < len(chapters) else total
        if merged and merged[-1][2]:                     # previous was too short: fold into this one
            t_, name = merged[-1][0], f"{merged[-1][1]} · {name}"; merged.pop()
        merged.append((t_, name, nxt - t_ < 10))
    return [(t_, name) for t_, name, _ in merged]


def chapter_list(clips, shown, rom, lead, total):
    """YouTube chapters: title at 0:00, then each verse (an uvāca starts its verse's chapter) and the
    colophon. Texts with dhyāna/maṅgala zones get one chapter per zone run, and the chapter heading
    ("Atha …") or first main verse is named "Māhātmyam begins". Chapters shorter than 10 s are
    folded into the next (YouTube's minimum)."""
    zoned = any(c.get("zone") for c in clips)
    chapters, t, uv, zone, main = [(0.0, rom)], lead, None, None, False
    for c in clips:
        dur = sf.info(c["out"]).duration
        z = c.get("zone") or ""
        if c["flag"] == "UVACA":
            uv = (" ".join(shown[c["seq"]]), t); t += dur + PAUSE; continue
        m = re.search(r"v(\d+)$", c["id"]); num = int(m.group(1)) if m else None
        t0 = uv[1] if uv else t
        if z:
            if z != zone: chapters.append((t0, SL.cap(SL.iast(z))))
        elif zoned and not main:                          # first clip of the māhātmyam proper
            chapters.append((t0, "Māhātmyam begins")); main = True
        if z or (c["flag"] == "HEADING" and not zoned):
            pass                                          # zone runs are one chapter; Gītā chapter headings stay in the title chapter
        elif c["flag"] == "COLOPHON":
            chapters.append((t0, "Iti (colophon)"))
        elif c["flag"] != "HEADING" and num:
            chapters.append((t0, f"Verse {num}"))
        elif c["flag"] != "HEADING" and not (zoned and chapters[-1][0] == t0):
            chapters.append((t0, SL.cap(SL.iast(uv[0])) if uv else "Verse"))
        zone = z; uv = None; t += dur + PAUSE
    return fold_short(chapters, total)


def slide_jobs(clips, T, work, t, base=0, nosplit=False):
    """Slides for one text's clips, chant time starting at t: ([(png, tex)], [start_s], end time).
    An uvāca clip gets no slide of its own: it is shown on (and starts) the following verse's slide."""
    shown, head, head_rom = T["shown"], T["head"], T["head_rom"]
    frame, vpal = SL.FRAME_PALETTE, SL.VERSE_PALETTES
    jobs, starts, nv, uv = [], [], 0, None
    for i, c in enumerate(clips, 1):
        dur = sf.info(c["out"]).duration
        if c["flag"] == "UVACA":
            uv = (" ".join(shown[c["seq"]]), t); t += dur + PAUSE; continue
        m = re.search(r"v(\d+)$", c["id"]); num = int(m.group(1)) if m else None
        t0 = uv[1] if uv else t
        png = f"{work}/{base + i:03d}_{c['id']}.png"
        if c["flag"] == "HEADING":                    # "अथ प्रथमोऽध्यायः …": opens the chapter, no verse number
            jobs.append((png, SL.colophon_tex(frame, head, " ".join(shown[c["seq"]]), head_rom, end=False)))
        elif c["flag"] == "COLOPHON":
            jobs.append((png, SL.colophon_tex(frame, head, " ".join(shown[c["seq"]]), head_rom)))
        elif T["split"].get(c["seq"]) and not nosplit:
            jobs.append((png, SL.split_verse_tex(vpal[nv % 2], head, head_rom, shown[c["seq"]], T["split"][c["seq"]], num,
                                                 uvaca=uv[0] if uv else None)))
            nv += 1
        else:
            jobs.append((png, SL.verse_tex(vpal[nv % 2], head, shown[c["seq"]], num, head_rom, uvaca=uv[0] if uv else None)))
            nv += 1
        starts.append(max(t0 - LEAD_SWITCH, 0.0))
        uv = None; t += dur + PAUSE
    return jobs, starts, t


def encode(jobs, starts, total, audio, out, slug, njobs):
    """Frame-exact still segments (one per slide), concatenated over the audio -> <out>/<slug>.mp4."""
    work = f"{out}/slides"
    edges = [round(s * FPS) for s in starts] + [round(total * FPS)]
    fd = round(FADE * FPS)
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
    with ThreadPoolExecutor(njobs) as ex:
        segs = list(ex.map(seg, range(len(jobs))))
    lst = f"{work}/segments.txt"
    open(lst, "w").write("".join(f"file '{os.path.abspath(s)}'\n" for s in segs))
    mp4 = f"{out}/{slug}.mp4"
    subprocess.run([FFMPEG, "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-i", audio,
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-movflags", "+faststart", "-t", f"{total:.3f}", mp4], check=True)
    for s in segs: os.remove(s)
    os.remove(lst)
    return mp4


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
    frame = SL.FRAME_PALETTE
    jobs = [(f"{work}/000_title.png", SL.title_tex(frame, title, composer, chandas, rom, speaker=speaker, source=source))]
    starts = [0.0]
    sj, ss, _ = slide_jobs(clips, T, work, lead)
    jobs += sj; starts += ss
    with ThreadPoolExecutor(a.jobs) as ex:
        list(ex.map(lambda j: SL.render(j[1], j[0], work), jobs))

    mp4 = encode(jobs, starts, total, audio, out, slug, a.jobs)
    chapters = chapter_list(clips, shown, rom, lead, total)
    with open(f"{out}/{slug}_chapters.txt", "w", encoding="utf-8") as f:
        f.writelines(f"{ts(t)} {name}\n" for t, name in chapters)
    print(f"{mp4}  ({total/60:.1f} min, {len(jobs)} slides)")


if __name__ == "__main__":
    main()
