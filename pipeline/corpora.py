"""The corpus: which texts are rendered, and the rules that decide what gets published.

Edit this file (not the scripts) to add or drop texts. Changes take effect on the next
`pipeline/run.sh`: only verses whose text or meter changed are re-rendered (see build_shard).
"""
from config import STOTRA_SANGRAHAH, PUJA_VIDHANAM

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
