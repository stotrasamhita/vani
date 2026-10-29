#!/usr/bin/env python3
"""slides/kanchi_pontiffs.tsv (pontiff number, name, regnal numeral) from the ārādhanā TOMLs of jyotisham/adyatithi
(mahApuruSha/kAnchI-maTha, names.sa = "काञ्ची N जगद्गुरु-श्री-<नाम>-सरस्वती[-numeral]-आराधना").

    python3 pipeline/kanchi_names.py [--src /data1/karthik_data/adyatithi-kanchi/mahApuruSha/kAnchI-maTha]

The numeral is the TOML's own when it has one, else the pontiff's rank among those of the identical name when
several share it. Anomalies are printed, not hidden.
"""
import argparse, collections, glob, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIG = {c: str(i) for i, c in enumerate("०१२३४५६७८९")}
NAME_FIX = {1: ("आदिशङ्कर", "आद्यशङ्कर")}   # the TOML spells the first ācārya Ādi-Śaṅkara; the stava slides use Ādya
OVERRIDE = {67: 6, 21: 1}      # 67: the TOML says ५ (as for 63) but caption and rank say VI; 21: the TOML has no numeral, yet 50 and 55 are II and III


def parse(sa):
    s = re.sub(r"^काञ्ची \d+ जगद्गुरु-", "", sa)
    s = re.sub(r"-(आराधना|आश्रम-स्वीकार-दिनम्|जयन्ती)$", "", s)
    parts = s.split("-"); num = None
    if parts[-1] and all(c in DIG for c in parts[-1]): num = int("".join(DIG[c] for c in parts.pop()))
    name = ""
    for p in parts:
        name += (" " if name.endswith("ः") or p == "सरस्वती" else "") + p
    name = name.replace("श्री", "श्री ", 1).replace("श्री  ", "श्री ")
    if re.match(r"श्री [अआइईउऊऋएऐओऔ]", name): name = name.replace("श्री ", "श्रीमद् ", 1)
    return name, num


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="/data1/karthik_data/adyatithi-kanchi/mahApuruSha/kAnchI-maTha")
    a = ap.parse_args()
    rec = {}
    for f in glob.glob(f"{a.src}/**/kAJcI_*.toml", recursive=True):
        m = re.search(r"kAJcI_(\d+)_", f)
        sa = re.search(r"\[names\]\s*\nsa = \[\s*\"([^\"]+)\"", open(f, encoding="utf-8").read())
        if m and sa:
            nm, nu = parse(sa.group(1)); k = int(m.group(1))
            if k in NAME_FIX: nm = nm.replace(*NAME_FIX[k])
            rec[k] = (nm, nu)
    groups = collections.defaultdict(list)
    for n in sorted(rec): groups[rec[n][0]].append(n)
    rows = []
    for n in sorted(rec):
        name, num = rec[n]; g = groups[name]
        rank = g.index(n) + 1 if len(g) > 1 else None
        if n in OVERRIDE: num = OVERRIDE[n]
        elif num is None: num = rank
        if rank and num != rank: print(f"note: {n} {name}: TOML numeral {num}, rank among same name {rank}")
        rows.append((n, name, num or ""))
    gaps = [n for n in range(1, max(rec) + 1) if n not in rec]
    if gaps: print("no TOML for", gaps)
    with open(f"{ROOT}/slides/kanchi_pontiffs.tsv", "w", encoding="utf-8") as f:
        f.write("n\tname\tnumeral\n")
        for r in rows: f.write(f"{r[0]}\t{r[1]}\t{r[2]}\n")
    print(len(rows), "pontiffs ->", f"{ROOT}/slides/kanchi_pontiffs.tsv")


if __name__ == "__main__":
    main()
