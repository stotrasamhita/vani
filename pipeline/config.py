"""Paths and tools for vani.

Defaults assume this layout (sources as siblings of the repo):

    <parent>/vani/                 this repo; vagdhenu/ is a git submodule
    <parent>/stotra-sangrahah/     https://github.com/stotrasamhita/stotra-sangrahah
    <parent>/puja-vidhanam/        https://github.com/stotrasamhita/puja-vidhanam

Anything machine-specific goes in <repo>/vani.env (KEY=VALUE lines, not committed) or the
environment, e.g. where the Vāgdhenu weights and BigVGAN live, or a non-PATH ffmpeg/tectonic.
All pipeline scripts run with the repo root as working directory (importing this module
chdir()s there), so shard paths like out/cache/... are relative to the repo.
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_env(path):
    env = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = os.path.expandvars(v.strip().strip('"'))
    return env


_ENV = {**_load_env(os.path.join(ROOT, "vani.env")), **os.environ}


def get(key, default):
    return _ENV.get(key) or default


VAGDHENU = get("VANI_VAGDHENU", os.path.join(ROOT, "vagdhenu"))
VAGDHENU_SRC = os.path.join(VAGDHENU, "src")
BANK = os.path.join(VAGDHENU_SRC, "reference_bank", "bank.json")
MODELS = get("CHAMP_ROOT", os.path.join(VAGDHENU, "models"))          # Vāgdhenu weights
BIGVGAN = get("VANI_BIGVGAN", os.path.join(VAGDHENU, "BigVGAN"))       # NVIDIA/BigVGAN clone

SOURCES_DIR = get("VANI_SOURCES", os.path.dirname(ROOT))
STOTRA_SANGRAHAH = get("VANI_STOTRA_SANGRAHAH", os.path.join(SOURCES_DIR, "stotra-sangrahah"))
PUJA_VIDHANAM = get("VANI_PUJA_VIDHANAM", os.path.join(SOURCES_DIR, "puja-vidhanam"))
FONTS = get("VANI_FONTS", os.path.join(STOTRA_SANGRAHAH, "fonts")) + "/"

TECTONIC = get("VANI_TECTONIC", "tectonic")
FFMPEG = get("VANI_FFMPEG", "ffmpeg")
DRONE = get("VANI_DRONE", os.path.join(ROOT, "assets", "sruthi_4F_Sa174_32cycles.flac"))

WORK = os.path.join(ROOT, "work")          # shards, logs (not committed)
OUT = os.path.join(ROOT, "out")            # render cache, mp3s, videos (not committed)

os.chdir(ROOT)
