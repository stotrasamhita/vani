# Setup notes

Hard-won notes from getting Vāgdhenu and this pipeline running on a shared lab machine
(Ubuntu 22.04, system Python 3.10, no root, 2 × NVIDIA RTX PRO 2000 Blackwell).

## GPU: Blackwell needs cu128 wheels

Vāgdhenu's `scripts/setup.sh` pins `torch==2.4.1 (+cu121)`, which only ships kernels up to
sm_90. On Blackwell (sm_120) it fails with `CUDA error: no kernel image is available`. Use the
cu128 index instead, and keep **torch, torchaudio and torchcodec from the same index** — every
failure we hit traced back to a version/ABI mismatch between them:

```bash
pip install --force-reinstall torch torchaudio torchcodec --index-url https://download.pytorch.org/whl/cu128
python3 -c "import torch,torchaudio; print(torch.__version__, torchaudio.__version__)"   # re-check after any pip install
```

On an older GPU (e.g. A100, sm_80) the repo's pinned versions work unmodified.

## torchcodec

Recent torchaudio delegates `torchaudio.load` to torchcodec, so it is required. The cu128
torchcodec build links NVIDIA NPP, which torch does not ship; the real error
(`libnppicc.so.12: cannot open shared object file`) is hidden behind a generic message.

```bash
pip install --no-deps "nvidia-npp-cu12>=12.3,<12.4"
# and put .../site-packages/nvidia/npp/lib on LD_LIBRARY_PATH (see vani.env)
python3 -c "import ctypes; ctypes.CDLL('<site-packages>/torchcodec/libtorchcodec<N>.so')"   # shows the real error
```

torchcodec also needs FFmpeg shared libraries; without root, micromamba works:
`micromamba create -p ~/.local/ffmpeg -c conda-forge ffmpeg`.

## Don't export that LD_LIBRARY_PATH globally

The micromamba FFmpeg environment ships its own OpenSSL `libcrypto.so.3`. With its `lib/` on a
global `LD_LIBRARY_PATH`, system tools linked against the system OpenSSL break —
`ssh-keygen` fails with *OpenSSL version mismatch*, and so do `ssh` and git over SSH. Set it
only for the pipeline (`vani.env`, which `run.sh` sources) or in a shell function you call when
needed.

## Other gotchas

- `pip install -r requirements.txt` in Vāgdhenu hits `ResolutionTooDeep` because of the
  IndicF5 git line: install everything else first, then that line with `--no-deps`.
- BigVGAN's `utils.py` imports matplotlib: `pip install matplotlib`.
- BigVGAN runs with `use_cuda_kernel=False`; nothing needs compiling.
- `~/.local` may be shared with other projects; a stray package requiring torch ≥ 2.5 once
  pulled in a CUDA-13 torchaudio. A venv avoids this.
- Long renders: always inside tmux.
- Tectonic (XeTeX) without root: `micromamba create -p ~/.local/tectonic -c conda-forge tectonic`;
  it fetches LaTeX packages on first use.

## Throughput

About 10–35 s per verse per GPU depending on load (≈ 120–150 verses/h per GPU). The stotra
corpus (~7,700 clips) took about two days on two GPUs. Slides and video encoding are CPU-only:
all 215 videos build in a few hours.
