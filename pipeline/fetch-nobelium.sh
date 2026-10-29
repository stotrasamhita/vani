#!/bin/bash
# Pull the final videos / mp3s / title slides from the server into ./vani-videos.
# Resumable (--partial): a dropped connection restarts and continues. Rebuilt files that differ are re-sent even if the size is unchanged. Safe to rerun any time.
#
#   ./fetch-nobelium.sh                       everything
#   ./fetch-nobelium.sh video/stotras/rama    only that subfolder (path under out/export/)
#   NOCOMP=1 ./fetch-nobelium.sh              everything except the two big compilations
#   DELETE=1 ./fetch-nobelium.sh              also remove local files no longer on the server
#
# Run inside tmux/screen (or with nohup) so closing the terminal doesn't stop it.
HOST=${HOST:-nobelium}
SRC=/data1/karthik_data/vani/out/export
DEST=${DEST:-vani-videos}
SUB=${1:-}
OPTS=(-av --partial --timeout=60 --info=progress2)
[ -n "$NOCOMP" ] && OPTS+=(--exclude 'compilations/')
[ -n "$DELETE" ] && OPTS+=(--delete)
mkdir -p "$DEST/$SUB"
until rsync "${OPTS[@]}" -e "ssh -o ServerAliveInterval=15 -o ServerAliveCountMax=4" \
        "$HOST:$SRC/$SUB${SUB:+/}" "$DEST/$SUB${SUB:+/}"; do
  echo "rsync interrupted; retrying in 10 s"; sleep 10
done
echo "done"
