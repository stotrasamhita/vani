"""Slide templates (XeLaTeX via Tectonic) for the stotra videos: title slide + verse slides.

Layout approved 2026-09-26 (see mock.py for the mock-ups): radial gradient background, cream
Devanāgarī (Sanskrit 2003), IAST in Gentium Basic italic, gold rules, footer links + AI note.
Palettes rotate per text in PALETTE_ORDER.
"""
import os, re, subprocess
from indic_transliteration import sanscript

import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))
from config import FONTS, TECTONIC, FFMPEG                 # noqa: E402

PALETTES = {  # name: (centre, edge, text, accent)
    "aubergine": ("4A1B4E", "12071A", "F3E9D2", "D4AF6A"),
    "indigo":    ("243266", "080C22", "EFE4CC", "C9A55C"),
    "maroon":    ("6B1A1F", "1C0607", "F3E9D2", "C9A55C"),
}
PALETTE_ORDER = ["aubergine", "indigo", "maroon"]            # user's preference order
# Per-slide scheme (user decision 2026-09-27): title and colophon maroon, verses alternate.
FRAME_PALETTE, VERSE_PALETTES = "maroon", ["aubergine", "indigo"]

CHANDAS = {  # detector/bank meter names -> Devanāgarī
    "anushtubh": "अनुष्टुप्", "vasantatilaka": "वसन्ततिलका", "bhujangaprayata": "भुजङ्गप्रयातम्",
    "upajati": "उपजातिः", "indravajra": "इन्द्रवज्रा", "upendravajra": "उपेन्द्रवज्रा",
    "vamshastha": "वंशस्थम्", "indravamsha": "इन्द्रवंशा", "malini": "मालिनी",
    "shardulavikridita": "शार्दूलविक्रीडितम्", "sragdhara": "स्रग्धरा", "rathoddhata": "रथोद्धता",
    "drutavilambita": "द्रुतविलम्बितम्", "shalini": "शालिनी", "pramanika": "प्रमाणिका",
    "shikharini": "शिखरिणी", "totaka": "तोटकम्", "panchachamara": "पञ्चचामरम्",
    "sragvini": "स्रग्विणी", "prithvi": "पृथ्वी", "mandakranta": "मन्दाक्रान्ता", "harini": "हरिणी",
}
def _names(kind):
    """names.tsv (user-reviewed): English metadata value -> (Devanāgarī, role). role is 'author'
    (shown above the title) or 'speaker' (stem; shown below the title as <stem>कृतम्/कृता/कृतः).
    Names not listed there are left off the slide."""
    rows = [l.rstrip("\n").split("\t") for l in open(os.path.join(os.path.dirname(__file__), "names.tsv"),
                                                   encoding="utf-8")][1:]
    return {r[1]: (r[2], r[3] if len(r) > 3 else "") for r in rows if r[0] == kind and len(r) > 2 and r[2]}


COMPOSERS, SOURCES = _names("composer"), {k: v for k, (v, _) in _names("source").items()}
VAKTAS = {k: v for k, (v, _) in _names("vakta").items()}
TITLES = _names("title")          # stotra id -> (Devanāgarī title, English title for IAST word splits)
TEXT_SOURCES = {r[1]: r[4].split("source:", 1)[1].strip()
                for r in (l.rstrip("\n").split("\t") for l in open(os.path.join(os.path.dirname(__file__), "names.tsv"),
                                                                    encoding="utf-8"))
                if r[0] == "title" and len(r) > 4 and "source:" in r[4]}   # stotra id -> English source

def _texts():
    """texts.tsv: per-text presentation for pieces of files (the Gītā set): title, English title,
    a line above the title (e.g. श्रीमद्भगवद्गीता), one below it (the chapter), source, composer."""
    rows = [l.rstrip("\n").split("\t") for l in open(os.path.join(os.path.dirname(__file__), "texts.tsv"),
                                                    encoding="utf-8")]
    return {r[0]: dict(zip(rows[0][1:], r[1:] + [""] * (len(rows[0]) - len(r)))) for r in rows[1:] if r[0]}


TEXTS = _texts()
if "Subrahmanya" in COMPOSERS: COMPOSERS["Composer:Subrahmanya"] = COMPOSERS["Subrahmanya"]   # known source typo


def krta(stem, title):
    """'<speaker>-kṛta' agreeing with the title's gender: स्तुतिः/-ā -> कृता, other -ḥ -> कृतः, else कृतम्."""
    t = title.strip()
    end = "कृता" if re.search(r"(तिः|ा)$", t) else "कृतः" if t.endswith("ः") else "कृतम्"
    return stem + end


DIGITS = str.maketrans("0123456789", "०१२३४५६७८९")


def iast(s):
    return sanscript.transliterate(s, sanscript.DEVANAGARI, sanscript.IAST)


def cap(s):
    return s[:1].upper() + s[1:]


_FOLD = [("ā", "a"), ("ī", "i"), ("ū", "u"), ("ṛ", "ri"), ("ṝ", "ri"), ("ḷ", "l"), ("ṃ", "m"), ("ḥ", ""),
         ("ṅ", "n"), ("ñ", "n"), ("ṭ", "t"), ("ḍ", "d"), ("ṇ", "n"), ("ś", "sh"), ("ṣ", "sh")]


def _fold(s):
    for a, b in _FOLD: s = s.replace(a, b)
    return _norm(s.replace("c", "ch").replace("chch", "cch"))


def _norm(s):          # spelling variants in the English wiki titles: w/v, r/ri (ṛ)
    return s.replace("w", "v").replace("ri", "r")


def title_iast(deva, wiki=""):
    """IAST title, split into words following the ASCII wiki_title ("Ganesha Bhujangam" ->
    "Gaṇeśa Bhujaṅgam"). Falls back to the unsplit form when the words don't line up."""
    t = iast(re.sub(r"[\s-]", "", deva)); words = [_norm(w) for w in wiki.lower().replace("-", " ").split()]
    out, i = [], 0
    if t.startswith("śrī") and words and not words[0].startswith(("shri", "sri")):
        out, i = ["Śrī"], 3                                   # honorific the wiki title omits
    for w in words:
        j = next((j for j in range(len(t), i, -1) if _fold(t[i:j]) == w), None)   # longest match
        if j is None: return cap(iast(deva))
        out.append(cap(t[i:j])); i = j
    return " ".join(out) if i == len(t) and out else cap(iast(deva))


SOURCE_REPO = "stotra-sangrahah"   # footer link; video.py sets it per text (gita, puja-vidhanam)


def _preamble(pal):
    c, e, t, a = PALETTES[pal]
    return rf"""\documentclass{{article}}
\usepackage[paperwidth=16in,paperheight=9in,margin=0in]{{geometry}}
\usepackage{{fontspec,xcolor,tikz,adjustbox}}
\usetikzlibrary{{shadings}}
\pagestyle{{empty}}
\newfontfamily\deva[Path={FONTS},Script=Devanagari]{{sanskrit2003-5-spac-diaresis.ttf}}
\newfontfamily\iast[Path={FONTS},ItalicFont=GenBasI.ttf]{{GenBasR.ttf}}
\definecolor{{bgc}}{{HTML}}{{{c}}}\definecolor{{bge}}{{HTML}}{{{e}}}
\definecolor{{txt}}{{HTML}}{{{t}}}\definecolor{{acc}}{{HTML}}{{{a}}}
\begin{{document}}
\begin{{tikzpicture}}[remember picture,overlay]
  \shade[inner color=bgc,outer color=bge] ([xshift=-2in,yshift=-5in]current page.south west)
        rectangle ([xshift=2in,yshift=3in]current page.north east);
  \draw[acc,line width=0.4pt,opacity=0.5] ([xshift=0.8in,yshift=0.62in]current page.south west)
        -- ([xshift=-0.8in,yshift=0.62in]current page.south east);
  \node[anchor=south west,xshift=0.8in,yshift=0.3in,text=txt,opacity=0.62] at (current page.south west)
       {{\iast\fontsize{{11}}{{13}}\selectfont stotrasamhita.github.io \ \textbullet\ \ github.com/stotrasamhita/{SOURCE_REPO}}};
  \node[anchor=south east,xshift=-0.8in,yshift=0.3in,text=txt,opacity=0.62] at (current page.south east)
       {{\iast\fontsize{{11}}{{13}}\selectfont Chant generated by AI with Vāgdhenu \ \textbullet\ \ github.com/prathoshap/vagdhenu}};
"""


END = "\\end{tikzpicture}\n\\end{document}\n"


def _rule(y):
    return (rf"  \draw[acc,line width=0.6pt] ([xshift=-2.2in,yshift={y}in]current page.center) -- ++(4.4in,0);" "\n"
            rf"  \fill[acc] ([yshift={y}in]current page.center) circle (2.2pt);" "\n")


def title_tex(pal, title, composer=None, chandas=None, title_rom=None, speaker=None, source=None):
    """title: Devanāgarī. composer (author) shows above the framed title; speaker ("इन्द्रकृतम्")
    inside the frame below it; chandas and source ("मूलम् — …") as small lines below the frame."""
    def pair(deva, rom, size=(24, 30), isize=(15, 19)):   # Devanāgarī over IAST, as one tabular cell
        return (rf"\begin{{tabular}}{{c}}{{\deva\fontsize{{{size[0]}}}{{{size[1]}}}\selectfont {deva}}}\\[0.1em]"
                rf"{{\iast\itshape\fontsize{{{isize[0]}}}{{{isize[1]}}}\selectfont {rom}}}\end{{tabular}}")
    rows = []
    if chandas:
        rows.append(pair(f"छन्दः — {chandas}", "Chandaḥ — " + " · ".join(cap(iast(m)) for m in chandas.split(" · "))))
    if source:
        rows.append(pair(f"मूलम् — {source}", f"Mūlam — {cap(iast(source))}", (20, 25), (13, 16)))
    sp = 0.5 if speaker else 0.0                        # extra frame height for the speaker line
    up = 0.2 * bool(speaker) + 0.15 * (len(rows) > 1)  # recentre the whole block
    y = lambda v: f"{v + up:.2f}"
    s = _preamble(pal)
    s += (r"  \node[anchor=north,yshift=-0.7in,text=acc] at (current page.north)"
          r" {\deva\fontsize{22}{26}\selectfont ॥श्रीः॥};" "\n")
    if composer:
        s += (rf"  \node[anchor=south,yshift={y(1.6)}in,text=txt,align=center,opacity=0.9] at (current page.center)"
              rf" {{{pair(composer, cap(iast(composer)))}}};" "\n")
    s += _rule(y(1.35))
    s += (rf"  \node[anchor=center,yshift={y(0.3)}in,text=txt,font=\deva\fontsize{{80}}{{96}}\selectfont]"
          rf" at (current page.center) {{\adjustbox{{max width=14in}}{{{title}}}}};" "\n")
    s += (rf"  \node[anchor=center,yshift={y(-0.75)}in,text=acc,font=\iast\itshape\fontsize{{34}}{{40}}\selectfont]"
          rf" at (current page.center) {{\adjustbox{{max width=14in}}{{{title_rom or cap(iast(title))}}}}};" "\n")
    if speaker:
        s += (rf"  \node[anchor=center,yshift={y(-1.35)}in,text=txt,align=center,opacity=0.9] at (current page.center)"
              rf" {{{pair(speaker, cap(iast(speaker)), (22, 27), (14, 17))}}};" "\n")
    s += _rule(y(-1.3 - sp - 0.05 * bool(speaker)))
    if rows:
        s += (rf"  \node[anchor=north,yshift={y(-1.55 - sp - 0.05 * bool(speaker))}in,text=txt,align=center,opacity=0.9]"
              rf" at (current page.center) {{\parbox{{14in}}{{\centering " + r"\par\vspace{0.9em}".join(rows) + r"}};" + "\n")
    return s + END


def verse_lines(display, num):
    """Display pādas -> (Devanāgarī lines, IAST lines) with daṇḍas and the verse number."""
    n = len(display)
    mid = {4: [1], 3: [0, 1], 6: [1, 3], 2: [0]}.get(n, [])
    end = f" ॥{str(num).translate(DIGITS)}॥" if num else " ॥"
    dev, rom = [], []
    for i, line in enumerate(display):
        d, r = line, iast(line)
        if i in mid: d += " ।"; r += " |"
        if i == n - 1: d += end; r += f" || {num} ||" if num else " ||"
        dev.append(d); rom.append(r)
    return dev, rom


def verse_tex(pal, title, display, num, title_rom=None, uvaca=None):
    dev, rom = verse_lines(display, num)
    size, lead = (42, 56) if len(dev) <= 4 else (34, 46)
    isize, ilead = (21, 27) if len(rom) <= 4 else (17, 22)
    dl = r"\\[0.35em]".join(dev)
    rl = r"\\[0.15em]".join(rom)
    s = _preamble(pal)
    s += (rf"  \node[anchor=north,yshift=-0.55in,text=acc] at (current page.north)"
          rf" {{\deva\fontsize{{26}}{{30}}\selectfont {title}}};" "\n")
    s += (rf"  \node[anchor=north,yshift=-1.12in,text=acc] at (current page.north)"
          rf" {{\iast\itshape\fontsize{{15}}{{18}}\selectfont {title_rom or cap(iast(title))}}};" "\n")
    s += (rf"  \draw[acc,line width=0.6pt] ([xshift=-2.2in,yshift=-1.55in]current page.north) -- ++(4.4in,0);" "\n"
          rf"  \fill[acc] ([yshift=-1.55in]current page.north) circle (2.2pt);" "\n")
    # verse block: Devanāgarī then IAST, stacked and centred between header rule and footer
    s += (rf"  \node[anchor=center,yshift=-0.35in,text=txt,align=center] at (current page.center)"
          rf" {{\adjustbox{{max width=14.2in,max totalheight=6.2in}}{{\begin{{tabular}}{{c}}"
          + (rf"{{\color{{acc}}\deva\fontsize{{26}}{{32}}\selectfont {uvaca}}}\\[0.05em]"
             rf"{{\color{{acc}}\iast\itshape\fontsize{{15}}{{19}}\selectfont {cap(iast(uvaca))}}}\\[0.7em]"
             if uvaca else "") +
          rf"{{\deva\fontsize{{{size}}}{{{lead}}}\selectfont \begin{{tabular}}{{c}}{dl}\end{{tabular}}}}\\[0.9em]"
          rf"{{\color{{txt!82!bge}}\iast\itshape\fontsize{{{isize}}}{{{ilead}}}\selectfont \begin{{tabular}}{{c}}{rl}\end{{tabular}}}}"
          rf"\end{{tabular}}}}}};" "\n")
    return s + END


def _header(head, head_rom):
    return (rf"  \node[anchor=north,yshift=-0.55in,text=acc] at (current page.north)"
            rf" {{\deva\fontsize{{26}}{{30}}\selectfont {head}}};" "\n"
            rf"  \node[anchor=north,yshift=-1.12in,text=acc] at (current page.north)"
            rf" {{\iast\itshape\fontsize{{15}}{{18}}\selectfont {head_rom}}};" "\n"
            r"  \draw[acc,line width=0.6pt] ([xshift=-2.2in,yshift=-1.55in]current page.north) -- ++(4.4in,0);" "\n"
            r"  \fill[acc] ([yshift=-1.55in]current page.north) circle (2.2pt);" "\n")


def split_verse_tex(pal, head, head_rom, display, split, num, uvaca=None):
    """Verse with its word split (padaccheda), split lines in gold (layouts approved 2026-09-29,
    work/gita_mock.py): 2-3 line verses (anuṣṭubh) stacked verse, IAST, split, split IAST (A2);
    4-line verses (triṣṭubh) in two columns, verse | split, each Devanāgarī over IAST (T1)."""
    wide = len(display) >= 4
    D, R = (28, 17) if wide else (34, 20)
    def tab(lines, size, font, colour, gap):
        return (rf"{{\color{{{colour}}}{font}\fontsize{{{size}}}{{{int(size * 1.3)}}}\selectfont \begin{{tabular}}{{c}}"
                + gap.join(lines) + r"\end{tabular}}")
    vd, vr = verse_lines(display, num)
    sd, sr = verse_lines(split, num)
    vd, sd = tab(vd, D, r"\deva", "txt", r"\\[0.2em]"), tab(sd, D, r"\deva", "acc!80!txt", r"\\[0.2em]")
    vr = tab(vr, R, r"\iast\itshape", "txt!85!bge", r"\\[0.1em]")
    sr = tab(sr, R, r"\iast\itshape", "acc!80!txt", r"\\[0.1em]")
    if wide:
        body = (r"\begin{tabular}{c@{\hspace{0.9in}}c}" + rf"\begin{{tabular}}{{c}}{vd}\\[0.6em]{vr}\end{{tabular}} & "
                + rf"\begin{{tabular}}{{c}}{sd}\\[0.6em]{sr}\end{{tabular}}\end{{tabular}}")
    else:
        body = r"\\[0.55em]".join([vd, vr, sd, sr])
    uv = (rf"{{\color{{acc}}\deva\fontsize{{24}}{{30}}\selectfont {uvaca}}}\\[0.02em]"
          rf"{{\color{{acc}}\iast\itshape\fontsize{{14}}{{18}}\selectfont {cap(iast(uvaca))}}}\\[0.6em]" if uvaca else "")
    return (_preamble(pal) + _header(head, head_rom)
            + rf"  \node[anchor=center,yshift=-0.4in,text=txt,align=center] at (current page.center)"
            rf" {{\adjustbox{{max width=14.4in,max totalheight=6.4in}}{{\begin{{tabular}}{{c}}{uv}{body}\end{{tabular}}}}}};" "\n"
            + END)


def colophon_tex(pal, title, text, title_rom=None, end=True):
    """Closing colophon (इति …): wrapped, centred, smaller and in gold; ends with ॥ (end=False: the opening
    "अथ …" heading, no daṇḍa)."""
    n = len(text)
    size, lead, isize, ilead = ((34, 50, 19, 25) if n < 160 else (28, 42, 16, 21) if n < 340 else (23, 34, 13, 17))
    s = _preamble(pal)
    s += (rf"  \node[anchor=north,yshift=-0.55in,text=acc] at (current page.north)"
          rf" {{\deva\fontsize{{26}}{{30}}\selectfont {title}}};" "\n")
    s += (rf"  \node[anchor=north,yshift=-1.12in,text=acc] at (current page.north)"
          rf" {{\iast\itshape\fontsize{{15}}{{18}}\selectfont {title_rom or cap(iast(title))}}};" "\n")
    s += (rf"  \draw[acc,line width=0.6pt] ([xshift=-2.2in,yshift=-1.55in]current page.north) -- ++(4.4in,0);" "\n"
          rf"  \fill[acc] ([yshift=-1.55in]current page.north) circle (2.2pt);" "\n")
    s += (rf"  \node[anchor=center,yshift=-0.35in,text=acc,align=center] at (current page.center)"
          rf" {{\adjustbox{{max totalheight=6.0in}}{{\parbox{{12.5in}}{{\centering"
          rf"{{\deva\fontsize{{{size}}}{{{lead}}}\selectfont {text}{' ॥' if end else ''}\par}}\vspace{{0.8em}}"
          rf"{{\color{{txt!82!bge}}\iast\itshape\fontsize{{{isize}}}{{{ilead}}}\selectfont {cap(iast(text))}{' ||' if end else ''}\par}}}}}}}};" "\n")
    return s + END


def render(tex_src, png, workdir):
    """tex source -> 1920x1080 PNG (rendered at 2x, lanczos-downscaled)."""
    os.makedirs(workdir, exist_ok=True)
    stem = os.path.join(workdir, os.path.splitext(os.path.basename(png))[0])
    open(stem + ".tex", "w", encoding="utf-8").write(tex_src)
    subprocess.run([TECTONIC, "--chatter", "minimal", "--outdir", workdir, stem + ".tex"], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    subprocess.run(["pdftoppm", "-png", "-r", "240", "-singlefile", stem + ".pdf", stem + "_2x"], check=True)
    subprocess.run([FFMPEG, "-loglevel", "error", "-y", "-i", stem + "_2x.png",
                    "-vf", "scale=1920:1080:flags=lanczos", png], check=True)
    for ext in (".tex", ".pdf", "_2x.png"):
        if os.path.exists(stem + ext): os.remove(stem + ext)
