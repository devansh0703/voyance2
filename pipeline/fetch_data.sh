#!/usr/bin/env bash
# Download NOAA MarineCadastre daily AIS parquet (CC0) + UN/LOCODE (open).
# Resumable: .done markers skip completed files.
set -u
cd "$(dirname "$0")/../data/raw"
mkdir -p .
BASE="https://ocmgeodatastor1.blob.core.windows.net/marinecadastre/ais2024"
for m in 2024-01 2024-04 2024-07; do
  for d in 08 09 10 11 12 13 14; do
    f="ais-$m-$d.parquet"
    [ -f "$f.done" ] && continue
    aria2c -x 16 -s 16 -k 4M --file-allocation=none --summary-interval=0 \
      --console-log-level=error -o "$f" "$BASE/$f" && touch "$f.done"
  done
done
[ -f unlocode.csv ] || curl -sL -o unlocode.csv \
  'https://raw.githubusercontent.com/datasets/un-locode/main/data/code-list.csv'
echo FETCH_DONE
