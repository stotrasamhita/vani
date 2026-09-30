#!/usr/bin/env python3
"""Compilation videos: several texts chanted as one, assembled from the already-rendered clips.

    python3 pipeline/compile.py gita-sampurna | gita-padma-sampurna  [--jobs 6] [--mp3-only]

gita-sampurna        dhyānam, the 18 chapters, the closing māhātmyam and the Varāha-purāṇa māhātmyam
                     (everything but the Gītārtha-saṅgraha); verse slides without the word split.
gita-padma-sampurna  the Padma-purāṇa māhātmyam: the dhyāna verses once, the 18 chapters' māhātmyam
                     (heading, verses, colophon), the maṅgala verses once.

Writes out/mp3/compilations/<name>/<name>_full.mp3 and its drone mix (_sruthi_m16), then
out/video/compilations/<name>/<name>.mp4 + _chapters.txt, and work/youtube/<name>.txt.
Slides and timing come from video.py's own functions, so a compilation looks like the per-text videos.
"""
import argparse, json, os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
import numpy as np, soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import video                                                # noqa: E402  (chdirs to the repo)
from video import SL, PAUSE, ts, slide_jobs, encode, fold_short, text_info   # noqa: E402
from to_mp3 import enc                                      # noqa: E402

PART_GAP = 1.2         # extra silence (s) between parts, on top of the usual pause
PURANA_CH0 = 174       # Padma-purāṇa (Uttara-khaṇḍa) chapter of the Gītā's adhyāya k is 174 + k
SPEAKER = "सम्पूर्णपारायणम्"


def shard_clips(shard, stotra):
    return sorted((c for c in shard if c["stotra"] == stotra), key=lambda c: c["seq"])


def part(shard, stotra, label, pick=None, title_only=False, nosplit=False):
    clips = shard_clips(shard, stotra)
    T = text_info(stotra, clips)
    if pick: clips = pick(clips)
    if title_only: T = dict(T, head=T["title"], head_rom=T["rom"])
    return dict(clips=clips, T=T, label=label, nosplit=nosplit)


def gita_sampurna(shard):
    parts = [part(shard, "gita/00dhyanam", "Gītā dhyānam", nosplit=True)]
    for k in range(1, 19):
        s = f"gita/chapter{k:02d}"
        parts.append(part(shard, s, f"Chapter {k} · {SL.cap(SL.iast(SL.TEXTS[s]['title']))}", nosplit=True))
    parts += [part(shard, "gita/19mahatmyam", "Gītā māhātmyam (closing verses)", nosplit=True),
              part(shard, "gita/20varahamahatmyam", "Gītā māhātmyam (Varāha Purāṇa)", nosplit=True)]
    title = "श्रीमद्भगवद्गीता"
    return dict(parts=parts, title=title, rom="Śrīmad Bhagavad Gītā", speaker=SPEAKER, source=None,
                repo="gita", en="Bhagavad Gita – Complete Chanting (Sampurna Parayanam)",
                playlist="Śrīmad Bhagavad Gītā (complete)")


def padma_sampurna(shard):
    first = lambda cl: [c for c in cl[:next(i for i, c in enumerate(cl) if not c.get("zone"))]]
    last = lambda cl: [c for c in cl[len(cl) - next(i for i, c in enumerate(reversed(cl)) if not c.get("zone")):]]
    main = lambda cl: [c for c in cl if not c.get("zone")]
    parts = [part(shard, "gita-padma/mahatmyam01", "Dhyāna verses", first, title_only=True)]
    for k in range(1, 19):
        parts.append(part(shard, f"gita-padma/mahatmyam{k:02d}", f"Adhyāya {k} māhātmyam (Purāṇa chapter {PURANA_CH0 + k})", main))
    parts.append(part(shard, "gita-padma/mahatmyam18", "Maṅgala verses", last, title_only=True))
    T0 = parts[1]["T"]
    return dict(parts=parts, title=T0["title"], rom=T0["rom"], speaker=SPEAKER, source=T0["source"],
                repo="gita", en="Gita Mahatmyam (Padma Purana) – Complete, All 18 Chapters",
                playlist="Gītā-māhātmyam (Padma Purāṇa)")


DEFS = {"gita-sampurna": gita_sampurna, "gita-padma-sampurna": padma_sampurna}


def build_audio(C, name):
    d = f"out/mp3/compilations/{name}"; os.makedirs(d, exist_ok=True)
    full = f"{d}/{name}_full.mp3"
    clips = [c for p in C["parts"] for c in p["clips"]]
    if os.path.exists(full) and all(os.path.getmtime(c["out"]) < os.path.getmtime(full) for c in clips):
        return d
    chunks, sr = [], None
    for p in C["parts"]:
        for j, c in enumerate(p["clips"]):
            y, sr_ = sf.read(c["out"], dtype="float32")
            assert sr in (None, sr_); sr = sr_
            gap = PAUSE + (PART_GAP if j == len(p["clips"]) - 1 else 0)
            chunks += [y, np.zeros(int(gap * sr), np.float32)]
    tmp = full[:-4] + ".part.wav"
    sf.write(tmp, np.concatenate(chunks[:-1]), sr)
    enc(tmp, full, "192k"); os.remove(tmp)
    for f in os.listdir(d):                                  # stale mix: rebuilt below
        if "_sruthi" in f: os.remove(os.path.join(d, f))
    return d


def timeline(C, lead):
    """Chant start time of each part, and the end of the chant (before the final gap)."""
    t, starts = lead, []
    for p in C["parts"]:
        starts.append(t)
        t += sum(sf.info(c["out"]).duration + PAUSE for c in p["clips"]) + PART_GAP
    return starts, t - PART_GAP - PAUSE


def youtube_text(C, name, chapters, total):
    import youtube_meta as YM
    plain = YM.plain
    title = f"{C['en']} · {C['title']} | Sanskrit chant with lyrics"
    if len(title) > YM.TITLE_MAX: title = f"{C['en']} · {C['title']}"
    lines = ["Chanted verse by verse, with the text on screen in Devanāgarī and IAST.", "",
             f"{C['title']} · {C['rom']}", f"{C['speaker']} · {SL.cap(SL.iast(C['speaker']))}"]
    if C["source"]: lines.append(f"मूलम् — {C['source']} · Mūlam — {SL.cap(SL.iast(C['source']))}")
    if name == "gita-padma-sampurna":
        lines += ["", "The traditional dhyāna verses once at the start, then the māhātmyam of all eighteen chapters "
                      "(Padma Purāṇa, Uttara-khaṇḍa, chapters 175–192), then the maṅgala verses once at the end."]
    else:
        lines += ["", "The Gītā-dhyānam, all eighteen chapters, the closing Gītā-māhātmyam and the Varāha-purāṇa "
                      "Gītā-māhātmyam. (The Gītārtha-saṅgraha is a separate video.) Each chapter opens with its "
                      "\"atha … adhyāyaḥ\" heading."]
    srcurl = f"https://github.com/stotrasamhita/{C['repo']}"
    tail = ["", YM.CREDITS.format(srcurl=srcurl), "", "#Sanskrit #BhagavadGita"]
    desc = "\n".join(lines + ["", "Chapters:"] + chapters + tail)
    assert len(desc) <= YM.DESC_MAX, len(desc)
    tags = ", ".join(dict.fromkeys(["Bhagavad Gita", "Gita chanting", "Sampurna parayanam", C["en"].split(" – ")[0],
                                    C["title"], plain(C["rom"]), "Sanskrit", "Sanskrit chanting", "Krishna", "Arjuna",
                                    "Sanskrit shlokas", "lyrics", "IAST"] +
                                   (["Padma Purana", "Gita Mahatmya"] if name == "gita-padma-sampurna" else [])))
    os.makedirs("work/youtube", exist_ok=True)
    mp4 = os.path.abspath(f"out/video/compilations/{name}/{name}.mp4")
    with open(f"work/youtube/{name}.txt", "w", encoding="utf-8") as f:
        f.write(f"FILE\n{mp4}\n\nTITLE ({len(title)}/100)\n{title}\n\nDESCRIPTION ({len(desc)}/5000)\n{desc}\n\n"
                f"TAGS ({len(tags)}/500)\n{tags}\n\nPLAYLIST\n{C['playlist']}\n\nCATEGORY / LANGUAGE\nMusic / Sanskrit\n\n"
                "NOTES\nAltered or synthetic content: Yes (AI-generated voice). Made for kids: No.\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name", choices=list(DEFS))
    ap.add_argument("--shard", default="work/bulk.json")
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--mp3-only", action="store_true")
    a = ap.parse_args()
    name = a.name
    C = DEFS[name](json.load(open(a.shard, encoding="utf-8")))
    SL.SOURCE_REPO = C["repo"]
    missing = [c["id"] for p in C["parts"] for c in p["clips"] if not os.path.exists(c["out"])]
    assert not missing, f"{len(missing)} clips not rendered, e.g. {missing[:3]}"
    n = sum(len(p["clips"]) for p in C["parts"])
    print(f"{name}: {len(C['parts'])} parts, {n} clips", flush=True)

    d = build_audio(C, name)
    if not [f for f in os.listdir(d) if f.endswith("_sruthi_m16.mp3")]:
        subprocess.run([sys.executable, os.path.join(HERE, "tanpura.py"), d], check=True)
    audio = f"{d}/{name}_full_sruthi_m16.mp3"
    timing = json.load(open(audio[:-4] + ".json"))
    lead, total = timing["lead_s"], timing["total_s"]
    print(f"audio: {total / 60:.1f} min", flush=True)
    if a.mp3_only: return

    out = f"out/video/compilations/{name}"; work = f"{out}/slides"
    os.makedirs(work, exist_ok=True)
    jobs = [(f"{work}/000_title.png", SL.title_tex(SL.FRAME_PALETTE, C["title"], None, None, C["rom"],
                                                   speaker=C["speaker"], source=C["source"]))]
    starts = [0.0]
    pstarts, end = timeline(C, lead)
    base = 0
    for p, t0 in zip(C["parts"], pstarts):
        sj, ss, _ = slide_jobs(p["clips"], p["T"], work, t0, base=base, nosplit=p["nosplit"])
        jobs += sj; starts += ss; base += len(p["clips"])
    assert abs(end - (total - timing["tail_s"])) < 0.5, (end, total, timing["tail_s"])   # chant length agrees with the mix
    print(f"{len(jobs)} slides", flush=True)
    with ThreadPoolExecutor(a.jobs) as ex:
        list(ex.map(lambda j: SL.render(j[1], j[0], work), jobs))
    mp4 = encode(jobs, starts, total, audio, out, name, a.jobs)
    ch = fold_short([(0.0, C["rom"])] + [(t, p["label"]) for p, t in zip(C["parts"], pstarts)], total)
    chapters = [f"{ts(t)} {label}" for t, label in ch]
    open(f"{out}/{name}_chapters.txt", "w", encoding="utf-8").write("\n".join(chapters) + "\n")
    youtube_text(C, name, chapters, total)
    print(f"{mp4}  ({total / 60:.1f} min, {len(jobs)} slides)")


if __name__ == "__main__":
    main()
