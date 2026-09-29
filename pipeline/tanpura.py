#!/usr/bin/env python3
"""Mix a tanpura drone under a text's _full mp3 -> <slug>_full[_FALLBACK]_tanpura.mp3 (same folder).

    python3 pipeline/tanpura.py FOLDER [FOLDER ...] [--drone DRONE]
                                       [--drone_sa HZ --sa 170.8] [--skip S] [--suffix _tanpura]
                                       [--below 20] [--lead 2.5] [--tail 3] [--lufs -14]

The drone (Pa-Sa-Sa-Sa, Sa = 170.4 Hz, which matches the renders' measured tonic of ~171 Hz,
see tonic.py) is looped with equal-power crossfades, placed --below dB under the chant's
active level (RMS over frames within 30 dB of its loudest), started --lead s before the first
verse and faded out over --tail s after the last. With --drone_sa, the drone is retuned from
its measured Sa to --sa by resampling (a drone tolerates the ~2% tempo change; no artifacts).
--skip drops the drone's first S seconds (e.g. a fade-in in the recording).
With --period (the drone's cycle length, s; set --skip to a cycle start), the lead-in is
--lead_cycles empty cycles (time for the video's title slide) so the chant enters on a cycle
boundary, and the drone runs on to the end of its current cycle after the last verse, then
fades out over --tail_cycles more cycles. The mix is loudness-normalised with a
two-pass ffmpeg loudnorm (linear) to --lufs integrated, -1.5 dBTP.
"""
import argparse, glob, json, os, re, subprocess, tempfile
import sys
import numpy as np, soundfile as sf, librosa
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import FFMPEG, DRONE                           # noqa: E402


def active_rms_db(y, sr, win=0.05):
    n = int(win * sr); f = y[: len(y) // n * n].reshape(-1, n)
    db = 10 * np.log10(np.mean(f ** 2, axis=1) + 1e-12)
    act = db[db > db.max() - 30]
    return 10 * np.log10(np.mean(10 ** (act / 10)))


def loop_drone(d, sr, length, xf=2.0):
    """Tile d to `length` samples with equal-power crossfades of xf seconds. With a cyclic drone
    whose excerpt holds a whole number of cycles, pass xf = one cycle: each join then overlaps a
    cycle with the next copy's first cycle, so the tiling stays on the drone's cycle grid."""
    x = int(xf * sr); t = np.linspace(0, np.pi / 2, x)
    fin, fout = np.sin(t), np.cos(t)
    out = d.copy()
    while len(out) < length:
        out = np.concatenate([out[:-x], out[-x:] * fout + d[:x] * fin, d[x:]])
    return out[:length]


def loudnorm(src, dst, lufs):
    af = f"loudnorm=I={lufs}:TP=-1.5:LRA=11"
    r = subprocess.run([FFMPEG, "-hide_banner", "-i", src, "-af", af + ":print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True, check=True)
    m = json.loads(re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr).group(0))
    af2 = (af + f":measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
           f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    subprocess.run([FFMPEG, "-loglevel", "error", "-y", "-i", src, "-af", af2, "-ar", "44100",
                    "-b:a", "192k", dst], check=True)


def mix(folder, a):
    full = [f for f in glob.glob(os.path.join(folder, "*_full*.mp3")) if re.search(r"_full(_FALLBACK)?\.mp3$", f)]
    assert len(full) == 1, f"{folder}: expected one _full mp3, found {full}"
    chant, sr = librosa.load(full[0], sr=None, mono=True)
    # read only the stretch of drone this text needs (the recording may be long), then retune by
    # resampling: target rate sr*drone_sa/sa played back at sr lowers the pitch by that ratio
    ratio = a.drone_sa / a.sa if a.drone_sa else 1.0
    info = sf.info(a.drone); dsr = info.samplerate
    need = int((len(chant) / sr + 3 * (a.period or 1) + a.lead + a.tail + 5) / ratio * dsr) + dsr
    start = int(a.skip * dsr)
    drone, _ = sf.read(a.drone, start=start, frames=min(need, info.frames - start), dtype="float32", always_2d=True)
    drone = librosa.resample(drone.mean(axis=1), orig_sr=dsr, target_sr=round(sr * ratio))
    if a.period:
        P = a.period * a.drone_sa / a.sa if a.drone_sa else a.period   # retuning down plays slower: longer cycle
        lead = int(round(a.lead_cycles * P * sr))
        rest = (-len(chant) / sr) % P                                # finish the current cycle
        tail = int(round((rest + a.tail_cycles * P) * sr))
    else:
        lead, tail = int(a.lead * sr), int(a.tail * sr)
    n = lead + len(chant) + tail
    dr = loop_drone(drone, sr, n, xf=P if a.period else 2.0)
    gain_db = active_rms_db(chant, sr) - a.below - active_rms_db(drone, sr)
    dr *= 10 ** (gain_db / 20)
    env = np.ones(n)
    fi = int(1.5 * sr); env[:fi] = np.linspace(0, 1, fi) ** 2
    fo = int(round(a.tail_cycles * P * sr)) if a.period else tail
    env[-fo:] = np.linspace(1, 0, fo) ** 2
    out = dr * env
    out[lead:lead + len(chant)] += chant
    out /= max(1.0, np.abs(out).max() / 0.98)
    dst = full[0][:-4] + a.suffix + ".mp3"
    with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
        sf.write(tmp.name, out.astype(np.float32), sr)
        loudnorm(tmp.name, dst, a.lufs)
    json.dump(dict(lead_s=lead / sr, tail_s=tail / sr, chant_s=len(chant) / sr, total_s=n / sr,
                   sa=a.sa, cycle_s=(P if a.period else None)),
              open(dst[:-4] + ".json", "w"), indent=1)          # timing for the video builder
    print(f"{dst}  (drone {gain_db:+.1f} dB, lead {lead/sr:.2f}s, tail {tail/sr:.2f}s, {n/sr/60:.1f} min)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folders", nargs="+")
    # defaults = production choice (2026-09-27): Śruti 4F retuned −16 c, starting on a cycle boundary
    ap.add_argument("--drone", default=DRONE, help="default: assets/sruthi_4F_Sa174_32cycles.flac")
    ap.add_argument("--drone_sa", type=float, default=174.45, help="measured Sa of the drone (Hz); retune to --sa")
    ap.add_argument("--sa", type=float, default=172.85, help="target Sa (Hz)")
    ap.add_argument("--skip", type=float, default=0.0, help="the bundled excerpt starts on a cycle boundary")
    ap.add_argument("--suffix", default="_sruthi_m16")
    ap.add_argument("--below", type=float, default=20)
    ap.add_argument("--period", type=float, default=3.7439, help="drone cycle length (s) before retuning; 0 = none")
    ap.add_argument("--lead_cycles", type=float, default=1.0)
    ap.add_argument("--tail_cycles", type=float, default=1.0)
    ap.add_argument("--lead", type=float, default=2.5)
    ap.add_argument("--tail", type=float, default=3.0)
    ap.add_argument("--lufs", type=float, default=-14)
    a = ap.parse_args()
    for f in a.folders: mix(f, a)


if __name__ == "__main__":
    main()
