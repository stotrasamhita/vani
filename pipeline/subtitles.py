#!/usr/bin/env python3
"""Subtitle tracks for a built video, one per script (the Sanskrit transliterated, not translated).

    python3 pipeline/subtitles.py stotras/shiva/shivamanasapuja [--scripts sa,en,te,kn,ta,ml,gu,bn]

Writes out/subtitles/<stotra>/<slug>.<code>.srt and out/export/subtitles/... (scratch-style, for review).
Cue timing: each verse's start comes from the same timeline as video.py; the padas (lines) inside a verse
are split at the longest pauses found in the verse's own audio, or proportionally if that fails.
"""
import argparse, json, os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import soundfile as sf
sys.path.insert(0, '/data1/karthik_data/vagdhenu/src')
import video as V                                           # also chdir()s to the repo
import slides as SL
from config import FFMPEG
from indic_transliteration import sanscript as S

# code -> (YouTube language code, track name, target scheme or None for the Devanagari original)
TRACKS = {
    "sa": ("sa", "संस्कृतम् (Devanagari)", None),
    "en": ("en", "Sanskrit in Roman (IAST)", "IAST"),
    "te": ("te", "తెలుగు లిపి (Telugu script)", S.TELUGU),
    "kn": ("kn", "ಕನ್ನಡ ಲಿಪಿ (Kannada script)", S.KANNADA),
    "ta": ("ta", "தமிழ் எழுத்து (Tamil script)", "TAMIL_SUP"),
    "ml": ("ml", "മലയാളം ലിപി (Malayalam script)", S.MALAYALAM),
    "gu": ("gu", "ગુજરાતી લિપિ (Gujarati script)", S.GUJARATI),
    "bn": ("bn", "বাংলা লিপি (Bengali script)", S.BENGALI),
    "or": ("or", "ଓଡ଼ିଆ ଲିପି (Odia script)", S.ORIYA),
    "ks": ("ks", "Sharada script (Kashmiri)", "AKS:Sharada"),
    "gr": ("sa", "Grantha script (Sanskrit)", "AKS:Grantha"),
    "pa": ("pa", "ਗੁਰਮੁਖੀ ਲਿਪੀ (Gurmukhi script)", S.GURMUKHI),
}


def srt_time(t):
    ms = round(t * 1000); h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def matras(line):
    from chandas_labeler import scan
    w, _ = scan(S.transliterate(line, S.DEVANAGARI, S.SLP1))
    return sum(2 if x == "G" else 1 for x in w) or 1


def pada_cuts(wav, lines, dur):
    """Times (s, within the clip) at which lines 2..n begin: the mora-proportional guess, snapped to the
    longest pause within 1.2 s of it (chanting has few clear pauses, so snapping is only a refinement)."""
    n = len(lines)
    if n < 2: return []
    wts = [matras(l) for l in lines]; tot = sum(wts)
    r = subprocess.run([FFMPEG, "-i", wav, "-af", "silencedetect=noise=-35dB:d=0.12", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    st = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r)]
    en = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r)]
    sil = [((a + b) / 2, b - a) for a, b in zip(st, en) if 0.15 < a and b < dur - 0.1]
    cuts, acc = [], 0
    for k in range(n - 1):
        acc += wts[k]; guess = dur * acc / tot
        near = [x for x in sil if abs(x[0] - guess) <= 1.2 and (not cuts or x[0] > cuts[-1] + 0.8)]
        cuts.append(max(near, key=lambda x: x[1])[0] if near else guess)
    return cuts


def cues(stotra, shard):
    clips = sorted((c for c in json.load(open(shard, encoding="utf-8")) if c["stotra"] == stotra), key=lambda c: c.get("order", c["seq"]))
    T = V.text_info(stotra, clips)
    mixdir = next(d for d in (f"out/mp3/{stotra}", f"out/mp3/{stotra}_FALLBACK") if os.path.isdir(d))
    audio = next(f for f in __import__("glob").glob(f"{mixdir}/*_full*_sruthi_m16.mp3"))
    t = json.load(open(audio[:-4] + ".json"))["lead_s"]
    out = []
    for c in clips:
        dur = sf.info(c["out"]).duration
        lines = [l for l in (T["shown"][c["seq"]] or []) if l.strip()]
        if c["flag"] != "UVACA" and lines:
            cut = [0.0] + pada_cuts(c["out"], lines, dur) + [dur]
            for i, l in enumerate(lines):
                a, b = t + cut[i], t + cut[i + 1] - (0.05 if i < len(lines) - 1 else 0)
                if len(l) > 70:                              # a long colophon: several shorter cues
                    ws = l.split(); k = -(-len(l) // 55); per = -(-len(ws) // k)
                    parts = [" ".join(ws[j:j + per]) for j in range(0, len(ws), per)]
                    tot = sum(len(x) for x in parts); u = a
                    for x in parts:
                        v = u + (b - a) * len(x) / tot; out.append((u, v - 0.05, x)); u = v
                else:
                    out.append((a, b, l))
        t += dur + V.PAUSE
    return out


def convert(text, scheme):
    if scheme is None: return text
    if scheme == "IAST": return SL.iast(text)
    if scheme.startswith("AKS:"):
        from aksharamukha import transliterate as AK
        return AK.process("Devanagari", scheme[4:], text)
    if scheme == "TAMIL_SUP":                   # Grantha-style Tamil: ka kha ga gha = க க² க³ க⁴
        t = S.transliterate(text, S.DEVANAGARI, S.TAMIL_SUP).replace("ʼ", "").replace("(அ)", "’")
        return re.sub(r"([\u0B95-\u0BB9])([²³⁴])([\u0BBE-\u0BCD]?)", r"\1\3\2", t)   # the digit follows the whole akshara
    return S.transliterate(text, S.DEVANAGARI, scheme)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stotra"); ap.add_argument("--shard", default="work/bulk.json")
    ap.add_argument("--scripts", default=",".join(TRACKS))
    a = ap.parse_args()
    slug = a.stotra.rsplit("/", 1)[1]
    cs = cues(a.stotra, a.shard)
    for code in a.scripts.split(","):
        scheme = TRACKS[code][2]
        d = f"out/subtitles/{a.stotra}"; os.makedirs(d, exist_ok=True)
        with open(f"{d}/{slug}.{code}.srt", "w", encoding="utf-8") as f:
            for i, (x, y, l) in enumerate(cs, 1):
                f.write(f"{i}\n{srt_time(x)} --> {srt_time(y)}\n{convert(l, scheme)}\n\n")
    print(f"{len(cs)} cues x {len(a.scripts.split(','))} scripts -> out/subtitles/{a.stotra}/")


if __name__ == "__main__":
    main()
