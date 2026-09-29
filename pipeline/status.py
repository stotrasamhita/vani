#!/usr/bin/env python3
"""Progress of the current render: cache coverage of the shard, rate, ETA, failures, texts done.

    python3 pipeline/status.py [SHARD.json]
"""
import datetime, glob, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config                                              # noqa: E402,F401  (chdir to repo root)
from collections import defaultdict

shard = sys.argv[1] if len(sys.argv) > 1 else "work/bulk.json"
clips = json.load(open(shard, encoding="utf-8"))
done = {c["id"] for c in clips if os.path.exists(c["out"])}
texts = defaultdict(lambda: [0, 0])
for c in clips:
    t = texts[c["stotra"]]; t[0] += 1; t[1] += c["id"] in done
complete = sum(1 for n, d in texts.values() if n == d)
colls = defaultdict(lambda: [0, 0])
for s, (n, d) in texts.items():
    k = "/".join(s.split("/")[:2]) if s.startswith("stotras/") else s.split("/")[0]
    colls[k][0] += n; colls[k][1] += d

now = datetime.datetime.now()
workers = []   # every render log still being written (one per GPU worker)
for log in glob.glob("work/render_*.log"):
    idle = (now - datetime.datetime.fromtimestamp(os.path.getmtime(log))).total_seconds()
    if idle > 24 * 3600: continue
    lines = open(log, encoding="utf-8").read().splitlines()
    t0 = datetime.datetime.strptime(re.search(r"(\d{8}_\d{4})\.log$", log).group(1), "%Y%m%d_%H%M")
    ok = [l for l in lines if l.startswith("OK ")]
    workers.append(dict(log=os.path.basename(log), idle=idle, ok=ok,
                        fails=[l for l in lines if l.startswith("FAIL ")],
                        rate=len(ok) / max((now - t0).total_seconds(), 1)))
active = [w for w in workers if w["idle"] < 600]
fails = [f for w in workers for f in w["fails"]]
left = len(clips) - len(done)
nproc = int(os.popen("ps -eo cmd | grep -c '[s]rc/render.py'").read().strip())
running = nproc > 0
idle = min((w["idle"] for w in workers), default=0)

print(f"{now:%a %d %b %H:%M}  render {f'RUNNING ({nproc} worker(s))' if running else 'NOT RUNNING'}"
      f"{'' if idle < 600 else f'  (log idle {idle/60:.0f} min!)'}")
print(f"clips {len(done)}/{len(clips)} ({100*len(done)/len(clips):.0f}%), {left} left; {len(fails)} FAIL")
rate = sum(w["rate"] for w in active)
if left and rate:
    print(f"throughput {3600*rate:.0f} clips/h -> ETA {now + datetime.timedelta(seconds=left/rate):%a %d %b %H:%M}")
print(f"texts complete {complete}/{len(texts)}")
for w in active:
    print(f"  {w['log']}: {len(w['ok'])} OK, on {w['ok'][-1].split()[1] if w['ok'] else '-'}")
for k, (n, d) in sorted(colls.items()):
    print(f"  {k:<28} {d:5d}/{n:<5d} {'done' if n == d else ''}")
for l in fails[-5:]: print("  " + l)
if any(l.startswith("RENDER_EXIT") for l in open("work/run.log", encoding="utf-8")):
    print("run.sh: render finished; see run.log for publish step")
