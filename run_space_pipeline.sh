#!/usr/bin/env bash
set -euo pipefail

SPACEURL="${1:-}"
BROWSER="${2:-chrome}"
OUT_ROOT="${3:-$HOME/Downloads/spaces}"

if [[ -z "$SPACEURL" ]]; then
  echo "Usage: $0 <space_url> [browser] [out_root]"
  exit 1
fi

# 1) 下载
./downloader.sh "$SPACEURL" "$BROWSER" "$OUT_ROOT"

# 2) 寻找最新目录（按时间排序取最后一个）
TARGET_DIR=$(ls -dt "$OUT_ROOT"/*/ | head -n1 | sed 's:/*$::')
BASE_NAME=$(basename "$TARGET_DIR")

# 3) 转16k WAV
ffmpeg -y -i "$TARGET_DIR/$BASE_NAME.m4a" -ac 1 -ar 16000 "$TARGET_DIR/audio_16k.wav"

# 4) 说话人切分
python3 diarize.py "$TARGET_DIR/audio_16k.wav" "$TARGET_DIR/diarization"

# 5) ASR
python3 asr_whisper.py "$TARGET_DIR/audio_16k.wav" "$TARGET_DIR/asr.json"

# 6) 防碎片平滑
python3 smooth_segments.py \
  "$TARGET_DIR/diarization/segments.csv" \
  "$TARGET_DIR/asr.json" \
  "$TARGET_DIR/diarization/segments_smoothed.csv"

# 7) 主题切分
python3 topic_seg.py "$TARGET_DIR/asr.json" "$TARGET_DIR/chapters.json"

# 8) 批量导出
python3 split_by_speaker.py \
  "$TARGET_DIR/audio_16k.wav" \
  "$TARGET_DIR/diarization/segments_smoothed.csv" \
  "$TARGET_DIR/speakers"

python3 split_by_topics.py "$TARGET_DIR"

# 9) 生成文字稿与摘要
python3 post_export.py "$TARGET_DIR"

echo "Done. See: $TARGET_DIR"
