"""The corpus: which texts are rendered, and the rules that decide what gets published.

Edit this file (not the scripts) to add or drop texts. Changes take effect on the next
`pipeline/run.sh`: only verses whose text or meter changed are re-rendered (see build_shard).
"""
from config import STOTRA_SANGRAHAH, PUJA_VIDHANAM, GITA

SOURCES = [  # (glob, collection, group) -- group replaces the parent folder as the id prefix
    (f"{STOTRA_SANGRAHAH}/stotras/**/*.tex", "stotras", None),
    (f"{PUJA_VIDHANAM}/kathas/ekadashi/padma-puranam/chapters/*.tex", "ekadashi", "ekadashi"),
    # kathās (chosen 2026-09-27)
    (f"{PUJA_VIDHANAM}/kathas/somavara-vrata-katha.tex", "kathas", None),
    (f"{PUJA_VIDHANAM}/kathas/pativrata-mahatyma-parva.tex", "kathas", None),
    (f"{PUJA_VIDHANAM}/kathas/syamantakopakhyanam.tex", "kathas", None),
    (f"{PUJA_VIDHANAM}/kathas/varalakshmi-vratam/varalakshmi-vrata-katha-bhavishya-puranam.tex", "kathas", None),
]

EXCLUDE_DIRS = ["/adhyatma-ramayana-stotras/"]
EXCLUDE_STOTRAS = {
    "stotras/hanuman/hanumanchalisa",                  # Awadhī, not Sanskrit
    "stotras/krishna/bhajagovindam", "stotras/krishna/bhajagovindamlaghu",   # mātrā meter
    "stotras/big/vishnusahasranamastotram",            # deferred
    "stotras/big/saundaryalahari",                     # never (śikhariṇī has no reference clip)
}

RENDER_FLAGS = {"", "HYPERMETRIC"}   # verse flags rendered as-is; others go through the rules below
# Prose (gadya) is never rendered and counts as missing content: texts with more prose than this
# are held back. Every other text is completed -- flagged verses render with the builder's fallback
# meter (MISMATCH -> the detected meter, tag DETECTED; the rest -> nearest-length reference, tag
# FALLBACK). Colophons and uvāca lines are rendered with the gadya reference and never held back.
PROSE_MAX = 0.10


def _parts(path, macro):
    """(first, last) line ranges of each \\<macro>{…} section of a file."""
    lines = open(path, encoding="utf-8").read().splitlines()
    idx = [i + 1 for i, l in enumerate(lines) if l.startswith("\\" + macro + "{")]
    return list(zip(idx, [i - 1 for i in idx[1:]] + [len(lines)]))


# Texts that are pieces of a file: (path, collection, group, slug, options). The Gītā set (2026-09-29):
# dhyānam, 18 chapters (with word-split slides from words/gita-words.tex, line-aligned with gita.tex),
# closing māhātmyam, Varāha-purāṇa māhātmyam, Gītārtha-saṅgraha; then the Padma-purāṇa māhātmyam, one
# text per chapter (6.175-6.192). Presentation (titles, lines above/below) is in slides/texts.tsv.
PIECES = [(f"{GITA}/nyasa.tex", "gita", "gita", "00dhyanam", dict(after="\\dnsub{ध्यानम्}"))]
PIECES += [(f"{GITA}/gita.tex", "gita", "gita", f"chapter{k:02d}",
            dict(part=p, split=f"{GITA}/words/gita-words.tex"))
           for k, p in enumerate(_parts(f"{GITA}/gita.tex", "chapt"), 1)]
PIECES += [(f"{GITA}/mahatmyam.tex", "gita", "gita", "19mahatmyam", {}),
           (f"{GITA}/mahatmyam-varaha-puranam.tex", "gita", "gita", "20varahamahatmyam", {}),
           (f"{GITA}/gsa.tex", "gita", "gita", "21gitarthasangraha", {})]
PIECES += [(f"{GITA}/mahatmyam-padma-puranam.tex", "gita-padma", "gitapadma", f"mahatmyam{k:02d}", dict(part=p))
           for k, p in enumerate(_parts(f"{GITA}/mahatmyam-padma-puranam.tex", "sect"), 1)]
