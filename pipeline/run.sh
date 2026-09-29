#!/bin/bash
# Full refresh: pull sources -> rebuild shard -> render only new/changed verses -> publish mp3s
#               -> drone mixes -> videos.     Run inside tmux: a full render takes a day or two.
#
#   pipeline/run.sh [--no-pull] [--mp3-only] [--no-mix] [--no-video] [--gpus 0,1]
#
#   --no-pull    skip `git pull` of the source repos
#   --mp3-only   skip rendering; republish from whatever is in the render cache
#   --no-mix     skip the drone mixes;  --no-video  skip the videos
#   --gpus LIST  render on these GPUs (default: $VANI_GPUS or 0). With two, the second
#                worker walks the shard in reverse and they meet in the middle.
#
# Machine-specific settings (weights, BigVGAN, library paths) come from vani.env.
set -o pipefail
cd "$(dirname "$0")/.."
if [ -f vani.env ]; then set -a; . ./vani.env; set +a; fi
VAGDHENU=${VANI_VAGDHENU:-$PWD/vagdhenu}
export PYTHONPATH="${VANI_BIGVGAN:-$VAGDHENU/BigVGAN}:$PYTHONPATH"
export CHAMP_ROOT=${CHAMP_ROOT:-$VAGDHENU/models}
W=work; mkdir -p $W; TS=$(date +%Y%m%d_%H%M)
PULL=1; RENDER=1; MIX=1; VIDEO=1; GPUS=${VANI_GPUS:-0}
while [ $# -gt 0 ]; do
  case $1 in
    --no-pull) PULL=0 ;; --mp3-only) RENDER=0 ;; --no-mix) MIX=0 ;; --no-video) VIDEO=0 ;;
    --gpus) GPUS=$2; shift ;;
    *) echo "unknown option $1"; exit 2 ;;
  esac; shift
done

if [ $PULL = 1 ]; then
  for r in "${VANI_STOTRA_SANGRAHAH:-../stotra-sangrahah}" "${VANI_PUJA_VIDHANAM:-../puja-vidhanam}"; do
    echo "== git pull $r"; git -C "$r" pull --ff-only || exit 1
  done
fi

echo "== build shard"
python3 pipeline/make_shard.py -o $W/bulk.json | tee $W/shard.log || exit 1
TODO=$(grep -oP 'to render \(not in cache\): \K[0-9]+' $W/shard.log)
[ "$TODO" = 0 ] && RENDER=0 && echo "== render: nothing new (all $(grep -oP '^[0-9]+(?= clips)' $W/shard.log) clips cached)"

if [ $RENDER = 1 ]; then
  echo "== render (cache hits are skipped) on GPU(s) $GPUS"
  python3 -c "import torch,torchaudio; print(torch.__version__, torchaudio.__version__)"
  IFS=, read -ra G <<< "$GPUS"
  if [ ${#G[@]} -gt 1 ]; then
    python3 -c "import json; c=json.load(open('$W/bulk.json')); json.dump(c[::-1], open('$W/bulk_rev.json','w'), ensure_ascii=False)"
    CUDA_VISIBLE_DEVICES=${G[1]} python3 $VAGDHENU/src/render.py --skip_existing --shard $W/bulk_rev.json \
      --results $W/bulk_rev_results.json > $W/render_gpu${G[1]}_$TS.log 2>&1 &
    SECOND=$!
  fi
  CUDA_VISIBLE_DEVICES=${G[0]} python3 $VAGDHENU/src/render.py --skip_existing --shard $W/bulk.json \
    --results $W/bulk_results.json 2>&1 | tee $W/render_$TS.log
  [ -n "$SECOND" ] && wait $SECOND
  echo "RENDER_EXIT fails=$(cat $W/render_*$TS.log | grep -c '^FAIL')"
fi

echo "== publish mp3s"
python3 pipeline/to_mp3.py $W/bulk.json || exit 1

if [ $MIX = 1 ]; then
  echo "== drone mixes (only texts whose _full mp3 is newer than their mix)"
  python3 - > $W/mix_todo.txt <<'PY'
import json, os, glob, re
for s in sorted({c["stotra"] for c in json.load(open("work/bulk.json"))}):
    for d in (f"out/mp3/{s}", f"out/mp3/{s}_FALLBACK"):
        full = [f for f in glob.glob(f"{d}/*_full*.mp3") if re.search(r"_full(_FALLBACK)?\.mp3$", f)]
        mix = glob.glob(f"{d}/*_sruthi_m16.mp3")
        if full and (not mix or os.path.getmtime(mix[0]) < os.path.getmtime(full[0])): print(d)
PY
  echo "$(wc -l < $W/mix_todo.txt) to mix"
  xargs -a $W/mix_todo.txt -r -P 16 -n 1 nice -n 10 python3 pipeline/tanpura.py 2>&1 | grep -v -i warn
fi

if [ $VIDEO = 1 ]; then
  echo "== videos (only texts whose mix is newer than their video)"
  python3 - > $W/video_todo.txt <<'PY'
import json, os, glob
for s in sorted({c["stotra"] for c in json.load(open("work/bulk.json"))}):
    if s.startswith("ekadashi/"): continue          # chapter videos not designed yet
    mix = glob.glob(f"out/mp3/{s}/*_sruthi_m16.mp3") + glob.glob(f"out/mp3/{s}_FALLBACK/*_sruthi_m16.mp3")
    mp4 = f"out/video/{s}/{s.rsplit('/', 1)[1]}.mp4"
    if mix and (not os.path.exists(mp4) or os.path.getmtime(mp4) < os.path.getmtime(mix[0])): print(s)
PY
  echo "$(wc -l < $W/video_todo.txt) to build"
  xargs -a $W/video_todo.txt -r -P 4 -I{} sh -c 'nice -n 10 python3 pipeline/video.py {} --jobs 8 2>&1 | tail -1'
fi
echo "EXIT"
