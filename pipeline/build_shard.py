#!/usr/bin/env python3
"""Build a Vāgdhenu render shard from stotra-sangrahah LaTeX sources.

    python3 pipeline/build_shard.py STOTRA.tex [...] -o pilot.json [--qc pilot_qc.tsv]

One clip per verse; `padas` holds one hemistich per piece (the bank references are
hemistich-length, "half" mode). Prose (e.g. a daṇḍakam body) becomes `gadya` clips,
one per '-delimited segment, chunked to <= --gadya_max akṣaras per piece.

Meter is auto-detected per verse with the same detector the web demo uses
(tts_meter.detect_meter), plus templates for bank meters that detector lacks.
Outputs are content-addressed: `out` is <cache>/<kk>/<key>.wav where `key` hashes everything
that determines the audio (RENDER_VERSION, meter, padas, seed, no_sandhi). An edited verse
gets a new key and is re-rendered by `render.py --skip_existing`; an unchanged verse that was
merely renumbered keeps its key and reuses its audio. `stotra` names the publish folder
(<collection>/[<deity>/]<slug>) that to_mp3.py assembles from the cache.

Every clip carries QC fields that render.py ignores:
    detected  what the scansion says ('' = no match)
    declared  the `% chandas:` header of the .tex, normalised ('' = none)
    flag      '' when detected meter is in the bank and agrees with the header;
              otherwise why this clip needs a listen (see FLAGS below).
"""
import argparse, hashlib, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import VAGDHENU_SRC, BANK                      # noqa: E402
sys.path.insert(0, VAGDHENU_SRC)
import prep_text as PT                                     # noqa: E402
from indic_transliteration import sanscript                # noqa: E402
from tts_syllabify import syllabify                        # noqa: E402
from tts_weight import tag_weights                         # noqa: E402
from tts_meter import detect_meter, _match_meter           # noqa: E402

# Bump to force a full re-render (new weights, changed render.py defaults, prep_text fixes, ...).
RENDER_VERSION = "v1"

# render.py resolves meters by bank key or wav stem; we emit wav stems (ASCII).
BANK_STEMS = {v["wav"][:-4] for k, v in json.load(open(BANK, encoding="utf-8")).items()
              if not k.startswith("_") and isinstance(v, dict) and "wav" in v}

# Meters tts_meter.METERS cannot detect (last syllable of each pāda is anceps).
EXTRA_METERS = [
    ("pramanika",       8, ["LGLGLGLG"]),
    ("shalini",        11, ["GGGGLGGLGGG"]),
    ("rathoddhata",    11, ["GLGLLLGLGLG"]),
    ("bhujangaprayata", 12, ["LGGLGGLGGLGG"]),
    ("drutavilambita", 12, ["LLLGLLGLLGLG"]),
    ("totaka",         12, ["LLGLLGLLGLLG"]),
    ("sragvini",       12, ["GLGGLGGLGGLG"]),
    ("panchachamara",  16, ["LGLGLGLGLGLGLGLG"]),
]

# `% chandas:` header spellings -> detector names
DECLARED = {
    "anushtup": "anushtubh", "vasantatilaka": "vasantatilaka", "bhujanga prayatam": "bhujangaprayata",
    "shardulavikriditam": "shardulavikridita", "shikharini": "shikharini", "sragdhara": "sragdhara",
    "upajati": "upajati", "totakam": "totaka", "pramanika": "pramanika", "sragvini": "sragvini",
    "panchachamara": "panchachamara",
}

FLAGS = {
    "NO_REF":    "detected meter has no reference clip in the bank -> rendered with fallback",
    "UNDETECTED": "scansion matched no meter -> used header/fallback",
    "MISMATCH":  "detected meter differs from the file's chandas header",
    "PROSE":     "non-metrical text rendered with the gadya reference",
    "HYPERMETRIC": "undetected, but an anuṣṭubh-dominant text with 15-19 syll. hemistichs -> anuṣṭubh (soft flag)",
}
FALLBACK = "vasantatilaka"            # same as render.py FALLBACK_METER
# Undetected verses: use the general-purpose reference whose hemistich length (syllables) is
# nearest the verse's, so at least phrase length and pacing match. Order breaks ties.
NEAREST = [("anushtubh", 16), ("upajati", 22), ("vamshastha", 24), ("vasantatilaka", 28),
           ("malini", 30), ("shardulavikridita", 38), ("sragdhara", 42)]

VERSE_MACROS = {  # name -> (n_args, n_trailing_annotation_args)
    "onelineshloka": (1, 0), "twolineshloka": (2, 0), "threelineshloka": (3, 0),
    "fourlineindentedshloka": (4, 0), "fourlineshloka": (4, 0), "THREElineshloka": (3, 0),
    "annotwolineshloka": (3, 1), "annofourlineindentedshloka": (5, 1),
}
HEADING_MACROS = {"sect", "chapt", "dnsub"}                # one arg, never recited
DEVA = re.compile(r"[\u0900-\u097F]")
SVARA = re.compile(r"[\u0951-\u0954\u1CD0-\u1CFF\uA8E0-\uA8FF\u200C\u200D]")


def read_group(s, i):
    """s[i] must be '{' (after whitespace); return (content, index after matching '}')."""
    j0 = i
    while s[i].isspace() or s[i] in "।॥": i += 1
    if "।" in s[j0:i] or "॥" in s[j0:i]:
        print(f"[warn] stray daṇḍa between macro args near: {s[max(0, j0-40):i+20]!r}", file=sys.stderr)
    assert s[i] == "{", f"expected '{{' at {i}: {s[i:i+30]!r}"
    depth, j = 0, i
    while True:
        c = s[j]
        if c == "\\": j += 2; continue
        if c == "{": depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0: return s[i + 1:j], j + 1
        j += 1


def clean(t, hyphens=False):
    """LaTeX fragment -> plain Devanāgarī words (optionally keeping '-' compound breaks)."""
    t = re.sub(r"\\mbox\{([^{}]*)\}", r"\1", t)
    t = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?", " ", t)    # any other macro
    t = re.sub(r"\\.", " ", t)                             # \\  \,  \-  etc.
    t = SVARA.sub("", t)
    t = t.replace("=", "")
    if not hyphens: t = t.replace("-", "")                 # compound-split hints
    t = re.sub(r"[{}~'’|।॥0-9०-९\[\]()*]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def display(t):
    """LaTeX fragment -> Devanāgarī as printed (keeps '-' compound breaks and avagraha; drops
    in-line daṇḍas/numbers, which the slide re-adds in a uniform style)."""
    t = re.sub(r"\\mbox\{([^{}]*)\}", r"\1", t)
    t = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?", " ", t)
    t = re.sub(r"\\.", " ", t)
    t = SVARA.sub("", t).replace("=", "")
    t = re.sub(r"[{}~|]", " ", t)
    t = re.sub(r"^[।॥\s]+|[।॥\s0-9०-९]+$", "", t.strip())
    return re.sub(r"\s+", " ", t).strip()


def load_macros(path):
    """\\newcommand{\\name}{body} definitions of a .tex file -> {name: body}."""
    src = open(path, encoding="utf-8").read(); out = {}
    for m in re.finditer(r"\\newcommand\{\\(\w+)\}\s*(?=\{)", src):
        out[m.group(1)], _ = read_group(src, m.end())
    return out


def expand_macros(tex, macros):
    """Inline the given zero-argument macros (nested ones too); comments are dropped first."""
    tex = re.sub(r"(?<!\\)%.*", "", tex)
    for _ in range(4):
        new = re.sub(r"\\([A-Za-z]+)(?![A-Za-z])", lambda m: macros.get(m.group(1), m.group(0)), tex)
        if new == tex: break
        tex = new
    return tex


def parse_meta(tex):
    m = re.search(r"% --meta--(.*?)% --end-meta--", tex, re.S)
    meta = {}
    for line in (m.group(1).splitlines() if m else []):
        k, _, v = line.lstrip("% ").partition(":")
        if v: meta[k.strip()] = v.strip()
    return meta


COLOPHON_WORDS = re.compile(r"सम्पूर्ण|समाप्त|अध्याय|ऽध्याय|सर्ग|(स्तोत्रम्|स्तवः|स्तुतिः|ष्टकम्)\s*$")


def iti(raw, sec):
    """A line starting with इति: a verse line if it scans like a hemistich (14-18 syllables, e.g.
    'इति श्रीरामचन्द्रस्य नाम्नामष्टोत्तरं शतम्'), a colophon if long, else a label (skipped)."""
    text = clean(raw); n = n_ak(text)
    if COLOPHON_WORDS.search(text) or n >= 20:
        return [("colophon", None, [clean(raw, hyphens=True)], [display(raw)])]
    if 14 <= n <= 18: return [("verse", (sec, None), [text], [display(raw)])]
    return []


def parse(tex, headings=False, zones=False):
    """Return [('verse', (sec, num|None), [hemistich,...]) | ('prose', None, [segment,...])];
    sec counts \\resetShloka restarts that follow numbered verses, so (sec, num) is unique.
    headings: \\chapt/\\sect become ('heading', ...) clips ("अथ <name>"), recited.
    zones: \\dnsub/\\closesub/headings emit ('zone', None, [label]) markers (label '' = main text);
    verses inside a labelled zone (dhyāna, maṅgala) are unnumbered."""
    body = re.sub(r"(?<!\\)%.*", "", tex)                  # comments (incl. %12 verse tags)
    count, sec, i, prose, zone = 0, 0, 0, [], ""
    tok = re.compile(r"\\([a-zA-Z]+)(\*?)|(?<!\\)\{")

    def flush():
        text = "".join(prose); prose.clear()
        # a prose run may end in colophons (॥इति ...॥); other segments are '-delimited
        head, *tails = re.split(r"(?=॥\s*इति)", text)
        res, segs = [], []
        for x in re.split(r"'|\n\s*\n", head):
            if not DEVA.search(x): continue
            if re.match(r"\s*[।॥]?\s*(इति|इत्य)", clean(x)): res += iti(x, sec)
            else: segs.append(clean(x, hyphens=True))
        for t in tails:
            t = re.sub(r"^॥\s*", "", t); res += iti(t.split("॥")[0], sec)
        return ([("prose", None, segs, None)] if segs else []) + res

    out = []
    while i < len(body):
        m = tok.search(body, i)
        prose.append(body[i:m.start() if m else len(body)])
        if not m: break
        if m.group(0) == "{":
            # bare top-level group: a verse fragment typeset without a macro (e.g. a half-verse
            # split off by \uvacha), a braced colophon, or a wrapper to parse inside
            g, j = read_group(body, m.start())
            if "\\" in g:
                i = m.end(); continue                          # wrapper: parse its contents
            i = j
            text = clean(g)
            if not DEVA.search(text): continue
            out += flush()
            if re.match(r"इति|इत्य", text): out += iti(g, sec)        # verse line / colophon / label
            elif text.startswith("ॐ") and COLOPHON_WORDS.search(text):   # "ॐ तत् सदिति … अध्यायः" (Gītā)
                out.append(("colophon", None, [clean(g, hyphens=True)], [display(g)]))
            else: out.append(("verse", (sec, None), [text], [display(g)]))
            continue
        name, star = m.group(1), m.group(2)
        i = m.end()
        if name in VERSE_MACROS:
            out += flush()
            n, anno = VERSE_MACROS[name]
            args = []
            for _ in range(n): a, i = read_group(body, i); args.append(a)
            lines = [clean(a) for a in args[:n - anno]]
            shown = [display(a) for a in args[:n - anno]]
            if len(lines) == 4:      # four pādas -> two hemistichs
                lines = [lines[0] + " " + lines[1], lines[2] + " " + lines[3]]
            num = None
            joined = " ".join(lines)
            if re.match(r"इति|इत्य", joined) and COLOPHON_WORDS.search(joined):   # colophon set as a verse
                out.append(("colophon", None, [clean(" ".join(args[:n - anno]), hyphens=True)],
                            [" ".join(shown)]))
                continue
            if not star and not zone: count += 1; num = count
            out.append(("verse", (sec, num), lines, shown))
        elif name == "uvacha":           # "X उवाच": recited before the next verse, shown with it
            out += flush(); a, i = read_group(body, i)
            if DEVA.search(clean(a)): out.append(("uvaca", None, [clean(a)], [display(a)]))
        elif name in HEADING_MACROS:
            out += flush(); a, i = read_group(body, i)
            if zones and name == "dnsub":
                zone = display(a) or "-"; out.append(("zone", None, [zone], None))
            elif name in ("sect", "chapt") and (headings or zones):
                if zones: zone = ""; out.append(("zone", None, [""], None))
                if headings:
                    segs = [t for t in (clean(x) for x in re.split(r"\\textsf\{[-—–]*\}", a)) if t]
                    out.append(("heading", None, ["अथ " + segs[0]] + segs[1:], ["अथ " + " । ".join(segs)]))   # one pada per segment: pause between them
        elif name == "closesub" and zones:
            out += flush(); zone = ""; out.append(("zone", None, [""], None))
        elif name == "resetShloka":
            if count: sec += 1
            count = 0
        elif name == "addtocounter":
            _, i = read_group(body, i); k, i = read_group(body, i); count += int(k)
        elif name in ("begin", "end", "setlength", "label", "hyperref", "fontspec", "newcommand",
                      "renewcommand", "centerline", "textbf", "vspace", "hspace", "columnsep"):
            # structural: swallow first arg except for content-bearing wrappers
            if name in ("centerline", "textbf"):
                a, i = read_group(body, i)
                if re.match(r"इति|इत्य", clean(a)): out += flush() + iti(a, sec); continue
                if re.search(r"नमः", a): continue            # blessing lines
                prose.append(a)
            else:
                while i < len(body) and body[i] in " {[" and body[i] != "\n":
                    if body[i] == "{": _, i = read_group(body, i)
                    elif body[i] == "[": i = body.index("]", i) + 1
                    else: i += 1
                    if name not in ("setlength", "addtocounter"): break
        elif name == "def":
            i = body.index("\n", i)
    out += flush()
    return out


def scan_meter(hemis):
    name = _scan(hemis)
    if not name and len(hemis) != 2 and all(_scan([h]) == "anushtubh" for h in hemis):
        name = "anushtubh"     # 1- or 3-hemistich anuṣṭubh (detector only knows 16/32 syllables)
    return name


def _scan(hemis):
    d = PT.to_deva(" | ".join(hemis))
    slp = sanscript.transliterate(d, sanscript.DEVANAGARI, sanscript.SLP1)
    syls = syllabify(re.sub(r"\s+", " ", slp).strip())
    tag_weights(syls)
    name = detect_meter(syls).get("name", "unknown")
    if name == "unknown":
        pat = "".join(s["weight"] for s in syls)
        name = next((n for n, pl, t in EXTRA_METERS if _match_meter(pat, pl, t)), "")
    return "anushtubh" if name == "anushtubh_half" else name


def n_ak(t):
    return len(re.findall(r"[\u0905-\u0914]|[\u0915-\u0939](?!\u094D)", t))


def chunk(seg, maxak):
    """Split a prose segment at word boundaries into pieces of <= maxak akṣaras."""
    pieces, cur, n = [], [], 0
    for w in re.findall(r"[^\s-]+-?", seg):
        k = max(1, n_ak(w))
        if cur and n + k > maxak: pieces.append(" ".join(cur)); cur, n = [], 0
        cur.append(w); n += k
    if cur: pieces.append(" ".join(cur))
    return [re.sub(r"-\s*", "", p).strip() for p in pieces]


def _overrides(path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "overrides.tsv")):
    """overrides.tsv: per-line fixes for bad takes -- clip text (pieces joined by ' | ') -> meter
    (reference clip) and seed. Changing either changes the cache key, so only that clip re-renders."""
    if not os.path.exists(path): return {}
    rows = [l.rstrip("\n").split("\t") for l in open(path, encoding="utf-8")][1:]
    return {re.sub(r"\s+", " ", r[0]).strip(): (r[1], int(r[2])) for r in rows if len(r) >= 3 and r[0]}


OVERRIDES = _overrides()


def render_key(c):
    blob = json.dumps([RENDER_VERSION, c["meter"], c["padas"], c["seed"], c["no_sandhi"]], ensure_ascii=False)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def build(path, seed, gadya_max, group=None, collection="stotras", cache="out/cache",
          part=None, after=None, slug=None, headings=False, zones=False, expand=None, swap=None):
    """part=(first, last) line numbers (1-based) and/or after=marker select a piece of a file
    (one chapter of the Gītā, the dhyāna of nyasa.tex); slug names that piece.
    swap=(marker, replacement) replaces everything from marker on; expand=<.tex> inlines that file's
    \\newcommand macros (the Purāṇa dhyāna/maṅgala verses); headings/zones: see parse()."""
    tex = open(path, encoding="utf-8").read()
    if part: tex = "".join(tex.splitlines(keepends=True)[part[0] - 1:part[1]])
    if after: tex = tex[tex.index(after):]
    if swap: tex = tex[:tex.index(swap[0])] + swap[1]
    meta = parse_meta(tex)
    if expand: tex = expand_macros(tex, load_macros(expand))
    deity = group or os.path.basename(os.path.dirname(path)).lower()
    slug = slug or re.sub(r"[^a-z0-9]+", "", os.path.splitext(os.path.basename(path))[0].lower())
    stotra = f"{collection}/{slug}" if group else f"{collection}/{deity}/{slug}"
    declared = DECLARED.get(meta.get("chandas", "").lower(), "")
    clips, seq, unnum, zone = [], 0, 0, ""
    for kind, num, parts, *shown in parse(tex, headings, zones):
        if zones and clips and "zone" not in clips[-1]: clips[-1]["zone"] = zone
        if kind == "zone": zone = parts[0]; continue
        if kind == "heading":
            seq += 1; nh = sum(1 for c in clips if c["flag"] == "HEADING") + 1
            clips.append(dict(id=f"{deity}_{slug}_h{nh:02d}", meter="anushtubh", padas=parts, seed=seed,
                              no_sandhi=True, display=shown[0], stotra=stotra, seq=seq, detected="",
                              declared=declared, flag="HEADING"))
            continue
        if kind == "uvaca":
            seq += 1; nw = sum(1 for c in clips if c["flag"] == "UVACA") + 1
            cid = f"{deity}_{slug}_w{nw:02d}"
            # anuṣṭubh reference: the gadya reference was unreliable on these short lines (2026-09-27)
            clips.append(dict(id=cid, meter="anushtubh", padas=parts, seed=seed, no_sandhi=True,
                              display=shown[0], stotra=stotra, seq=seq, detected="",
                              declared=declared, flag="UVACA"))
            continue
        if kind == "colophon":
            seq += 1; ncol = sum(1 for c in clips if c["flag"] == "COLOPHON") + 1
            cid = f"{deity}_{slug}_c{ncol:02d}"
            clips.append(dict(id=cid, meter="gadya", padas=chunk(parts[0], gadya_max), seed=seed,
                              no_sandhi=True, display=shown[0], stotra=stotra, seq=seq,
                              detected="", declared=declared, flag="COLOPHON"))
            continue
        if kind == "prose":
            for seg in parts:
                seq += 1
                cid = f"{deity}_{slug}_g{seq:03d}"
                clips.append(dict(id=cid, meter="gadya", padas=chunk(seg, gadya_max), seed=seed,
                                  no_sandhi=True, stotra=stotra, seq=seq,
                                  detected="", declared=declared, flag="PROSE"))
            continue
        seq += 1
        sec, num = num
        if num is None: unnum += 1
        cid = f"{deity}_{slug}_" + (f"s{sec + 1}" if sec else "") + \
              (f"v{num:03d}" if num is not None else f"u{unnum:02d}")
        det = scan_meter(parts)
        flags = []
        if det and det in BANK_STEMS: meter = det
        elif det: meter = FALLBACK; flags.append("NO_REF")
        else:
            flags.append("UNDETECTED")
            hl = sum(n_ak(h) for h in parts) / len(parts)
            meter = min(NEAREST, key=lambda m: abs(m[1] - hl))[0]
        if det and declared and det != declared and num is not None:
            flags.append("MISMATCH")      # unnumbered dhyāna verses are often in a different meter
        clips.append(dict(id=cid, meter=meter, padas=parts, seed=seed, no_sandhi=True, display=shown[0],
                          stotra=stotra, seq=seq,
                          detected=det, declared=declared, flag=",".join(flags)))
    if zones and clips and "zone" not in clips[-1]: clips[-1]["zone"] = zone
    dets = [c["detected"] for c in clips if c["detected"]]
    dominant = max(set(dets), key=dets.count) if dets else declared
    for c in clips:
        if c["flag"] == "UNDETECTED" and "anushtubh" in (dominant, declared) \
                and all(15 <= n_ak(h) <= 19 for h in c["padas"]):
            c["meter"], c["flag"] = "anushtubh", "HYPERMETRIC"
    for c in clips:
        ov = OVERRIDES.get(" | ".join(c["padas"]))
        if ov: c["meter"], c["seed"] = ov; c["override"] = True
        c["src"] = os.path.abspath(path)
        if part: c["part"] = list(part)
        if after: c["after"] = after
        opts = {k: v for k, v in dict(headings=headings, zones=zones, expand=expand, swap=swap).items() if v}
        if opts: c["opts"] = opts
        c["key"] = render_key(c)
        c["out"] = f"{cache}/{c['key'][:2]}/{c['key']}.wav"
    return clips


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tex", nargs="+")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--qc", help="also write a TSV of id/meter/detected/declared/flag/text")
    ap.add_argument("--seed", type=int, default=60)
    ap.add_argument("--collection", default="stotras", help="top-level publish folder")
    ap.add_argument("--cache", default="out/cache", help="content-addressed render cache")
    ap.add_argument("--gadya_max", type=int, default=24)
    ap.add_argument("--group", help="id prefix instead of the parent directory name (e.g. ekadashi)")
    ap.add_argument("--no_prose", action="store_true", help="drop non-metrical (gadya) clips")
    ap.add_argument("--limit", type=int, default=0, help="keep only the first N clips per file")
    a = ap.parse_args()
    clips = []
    for p in a.tex:
        c = build(p, a.seed, a.gadya_max, a.group, a.collection, a.cache)
        if a.no_prose: c = [x for x in c if x["meter"] != "gadya"]
        clips += c[:a.limit] if a.limit else c
    json.dump(clips, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if a.qc:
        with open(a.qc, "w", encoding="utf-8") as f:
            f.write("id\tmeter\tdetected\tdeclared\tflag\ttext\n")
            for c in clips:
                f.write("\t".join([c["id"], c["meter"], c["detected"], c["declared"], c["flag"],
                                   " | ".join(c["padas"])]) + "\n")
    from collections import Counter
    print(f"{len(clips)} clips -> {a.out}", file=sys.stderr)
    for k, v in Counter((c["meter"], c["flag"]) for c in clips).most_common():
        print(f"  {v:5d}  {k[0]:<18} {k[1]}", file=sys.stderr)


if __name__ == "__main__":
    main()
