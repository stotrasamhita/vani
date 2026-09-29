# vāṇī

Chanted audio and videos of Sanskrit stotras and kathās, generated with
[Vāgdhenu](https://github.com/prathoshap/vagdhenu) from the LaTeX sources of
[stotra-sangrahah](https://github.com/stotrasamhita/stotra-sangrahah) and
[puja-vidhanam](https://github.com/stotrasamhita/puja-vidhanam).

Every verse is chanted in its own metre, the whole text is mixed over a śruti drone, and a
video is typeset with Devanāgarī and IAST slides. When a source changes, only the affected
verses are re-rendered.

> The chant is AI-generated. It is laukika (non-Vedic) recitation only; Vedic svaras are
> outside Vāgdhenu's scope.

▶️ **Watch on YouTube:** [Stotra Samhita Vani · स्तोत्रसंहिता-वाणी](https://www.youtube.com/@stotrasamhita-vani)

## Examples

| Text | Audio | Slides | Video | YouTube |
|---|---|---|---|---|
| Gaṇeśa Bhujaṅgam | [🎧 mp3](examples/ganeshabhujangam) | [🖼️ slides](examples/ganeshabhujangam/slides) | [🎬 mp4](https://github.com/stotrasamhita/vani/releases/tag/examples-2026.09) | [▶️ YouTube](https://www.youtube.com/watch?v=D1fuBd9QckA) |
| Rāmāṣṭottaraśatanāmastotram | [🎧 mp3](examples/ramaashtottarashatanamastotram) | [🖼️ slides](examples/ramaashtottarashatanamastotram/slides) | [🎬 mp4](https://github.com/stotrasamhita/vani/releases/tag/examples-2026.09) | [▶️ YouTube](https://www.youtube.com/watch?v=GOYzfC-D_wc) |
| Āditya Hṛdayam | [🎧 mp3](examples/adityahrdayam) | [🖼️ slides](examples/adityahrdayam/slides) | [🎬 mp4](https://github.com/stotrasamhita/vani/releases/tag/examples-2026.09) | [▶️ YouTube](https://www.youtube.com/watch?v=ewzhalKKChg) |
| Durgā Candrakalā Stuti | [🎧 mp3](examples/durgachandrakalastuti) | [🖼️ slides](examples/durgachandrakalastuti/slides) | [🎬 mp4](https://github.com/stotrasamhita/vani/releases/tag/examples-2026.09) | [▶️ YouTube](https://www.youtube.com/watch?v=G7udTPooKc8) |

Each example folder has the drone-mixed `_full_sruthi_m16.mp3`, the per-verse QC sheet
(`.tsv`: metre, flags, duration, text), the YouTube chapter list and a few slides.

### ▶️ On YouTube

Videos are being published on **[Stotra Samhita Vani · स्तोत्रसंहिता-वाणी](https://www.youtube.com/@stotrasamhita-vani)**, including:

- [Śravaṇa-dvādaśī-vratam](https://www.youtube.com/watch?v=2f_Va0um5dI) — Padma Purāṇa
- [Pativratā-māhātmya-parva](https://www.youtube.com/watch?v=LCo3u8nnqp0) — the story of Sāvitrī and Satyavān, Mahābhārata
- [Varalakṣmī-vrata-kathā](https://www.youtube.com/watch?v=fkZlDBfJUKY) — Bhaviṣyottara Purāṇa


## How it works

```
 .tex sources ──► build_shard ──► shard (one clip per verse, content-hashed)
                   · parses the verse macros, uvāca lines, colophons
                   · detects the metre of every verse
                                       │
                                       ▼
                 vagdhenu render.py ──► out/cache/<hash>.wav   (only cache misses)
                                       │
          to_mp3 ◄─────────────────────┘
            · per-verse mp3s + <text>_full.mp3 + <text>.tsv      out/mp3/<collection>/…
          tanpura
            · śruti drone under the full mp3, −14 LUFS         <text>_full_sruthi_m16.mp3
          video
            · XeLaTeX slides → PNG → ffmpeg, chapter list        out/video/<collection>/…
```

- **Content-addressed renders.** A clip's cache key hashes its text, metre and seed, so an
  edited verse is re-rendered, while inserting, deleting or renumbering verses reuses every
  existing render. `RENDER_VERSION` in `pipeline/build_shard.py` forces a full re-render.
- **Metre per verse.** Vāgdhenu chants from a per-metre reference clip, and a wrong metre
  produces a plausible but metrically wrong chant with no error. The builder detects each
  verse's metre; when detection fails, or the metre has no reference clip, it uses a fallback
  (the detected metre if it has a reference, otherwise the reference nearest in line length)
  and flags the verse. Texts where more than 10% of verses are fallbacks are published as
  `<text>_FALLBACK` so they can be listened to critically.
- **What is recited.** Verses (all verse macros, plus half-verses written as bare `{…}`),
  uvāca lines (shown in gold above their verse), and the closing colophon (इति …), which is
  chanted in the prose (gadya) style. Prose passages are not rendered; a text with more than 10%
  prose is held back rather than published incomplete.
- **Drone.** A śruti box in F, retuned 16 cents down to sit with the chant (whose Sa measures
  about 171 Hz, see `pipeline/tonic.py`). The first drone cycle is left empty for the title
  slide, and the chant enters on a cycle boundary.
- **Slides.** Title and colophon slides are maroon; verse slides alternate aubergine and
  indigo. The title slide shows the composer (above the title) or, when the metadata names a
  speaker (`% vakta:`), the speaker as *…कृतम्* (below it), the metre when it is reliably
  detected, and the source (*मूलम् — …*). Names are rendered from `slides/names.tsv`.

## Layout

```
pipeline/   build_shard, make_shard, to_mp3, tanpura, video, status, tonic, run.sh
            config.py   — paths/tools (override in vani.env)
            corpora.py  — which texts are rendered, and the publishing rules
slides/     slides.py (templates), names.tsv (composer/source/title names), mock.py
assets/     sruthi_4F_Sa174_32cycles.flac — 32-cycle excerpt of the drone, looped on its cycle grid
vagdhenu/   submodule: Vāgdhenu (fork with batch-rendering fixes, prathoshap/vagdhenu#19)
examples/   four texts: mp3, QC sheet, chapters, slides
docs/       setup notes
out/, work/ generated (not committed)
```

## Setup

```bash
git clone --recursive https://github.com/stotrasamhita/vani.git
git clone https://github.com/stotrasamhita/stotra-sangrahah.git   # siblings of vani/
git clone https://github.com/stotrasamhita/puja-vidhanam.git
cd vani && cp vani.env.example vani.env    # then edit
```

You also need Vāgdhenu's requirements and weights (see `vagdhenu/README.md`), an
[NVIDIA/BigVGAN](https://github.com/NVIDIA/BigVGAN) clone, `ffmpeg`, and
[Tectonic](https://tectonic-typesetting.github.io) for the slides. Fonts come from
stotra-sangrahah (`fonts/`). See [docs/setup-notes.md](docs/setup-notes.md) for GPU and
library pitfalls (Blackwell/cu128, torchcodec, OpenSSL).

## Usage

```bash
tmux new -s vani pipeline/run.sh        # pull sources, render what changed, publish, mix, video
pipeline/run.sh --no-pull --no-video    # e.g. skip steps
python3 pipeline/status.py              # progress of a running render
python3 pipeline/video.py stotras/ganesha/ganeshabhujangam   # one video
```

To add or drop texts, edit `pipeline/corpora.py`; to fix a name on a slide, edit
`slides/names.tsv`; to fix a verse, fix it in the source repository and rerun.

## Acknowledgements

- **Vāgdhenu** by Prathosh ([@prathoshap](https://github.com/prathoshap)) — the chanting model.
- **Śruti drone**: [shanmukhapriya.com — Tambura/Sruthi](https://shanmukhapriya.com/tambura-sruthi) (4 kaṭṭai / F).
- **Texts**: stotrasamhita — [stotra-sangrahah](https://github.com/stotrasamhita/stotra-sangrahah),
  [puja-vidhanam](https://github.com/stotrasamhita/puja-vidhanam).
- **Fonts**: Sanskrit 2003 (Devanāgarī), Gentium Basic (IAST).
- Pipeline developed with Claude Code.
