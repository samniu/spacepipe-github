#!/usr/bin/env bash
set -euo pipefail

# 用法: ./downloader.sh <space_url> [browser] [out_root] [download_minutes]
# 例子: ./downloader.sh "https://twitter.com/i/spaces/XXXX" chrome "$HOME/Downloads/spaces" 3

SPACEURL="${1:-}"
BROWSER="${2:-chrome}"   # 默认 chrome，可改 firefox/edge/...
OUT_ROOT="${3:-$HOME/Downloads/spaces}"
DOWNLOAD_MINUTES="${4:-}"

if [[ -z "$SPACEURL" ]]; then
  echo "Usage: $0 <space_url> [browser] [out_root] [download_minutes]"
  exit 1
fi

mkdir -p "$OUT_ROOT"
IFS=$'\t\n'

# 基名与流 URL
BASE_NAME=$(yt-dlp --cookies-from-browser "$BROWSER" --get-filename -o "%(upload_date)s - %(title)s" "$SPACEURL")
STREAM=$(yt-dlp --cookies-from-browser "$BROWSER" -g "$SPACEURL")

# 目标目录与文件
TARGET_DIR="$OUT_ROOT/$BASE_NAME"
mkdir -p "$TARGET_DIR"
FINAL_FILE="$TARGET_DIR/$BASE_NAME.m4a"

# 可选截断时长（分钟）
YT_SECTIONS=()
FFMPEG_T_SECS=""
if [[ -n "$DOWNLOAD_MINUTES" && "$DOWNLOAD_MINUTES" != "0" ]]; then
  FFMPEG_T_SECS=$(python3 - "$DOWNLOAD_MINUTES" <<'PY'
import sys, math
m = float(sys.argv[1])
secs = max(1, int(math.ceil(m * 60)))
print(secs)
PY
)
  # 格式化为 hh:mm:ss 供 yt-dlp
  HMS=$(python3 - "$FFMPEG_T_SECS" <<'PY'
import sys
secs = int(sys.argv[1])
h = secs // 3600
m = (secs % 3600) // 60
s = secs % 60
print(f"{h:02d}:{m:02d}:{s:02d}")
PY
)
  YT_SECTIONS=(--download-sections "*00:00:00-${HMS}" --force-keyframes-at-cuts)
  echo "[info] download_minutes set => only downloading first ${HMS}"
fi

# 临时文件夹
TEMP_DIR="$TARGET_DIR/.temp_chunks"
mkdir -p "$TEMP_DIR"

# 先尝试直接用 yt-dlp 下载为 m4a（最稳妥）
# quick 模式下如果已有旧文件，先删掉避免复用全量
if [[ -n "$FFMPEG_T_SECS" && -f "$FINAL_FILE" ]]; then
  rm -f "$FINAL_FILE"
fi
if yt-dlp --cookies-from-browser "$BROWSER" -o "$FINAL_FILE" -x --audio-format m4a --audio-quality 0 "${YT_SECTIONS[@]}" "$SPACEURL"; then
  echo "Saved (yt-dlp): $FINAL_FILE"
  exit 0
fi

echo "[warn] yt-dlp direct download failed, fallback to m3u8 chunks..."

# 下载 m3u8
if ! wget "$STREAM" -O "$TEMP_DIR/stream.m3u8"; then
  echo "[error] failed to download m3u8"
  exit 1
fi

# quick 模式下只取前 N 分钟，则直接用 ffmpeg -t；否则继续分片下载
if [[ -n "$FFMPEG_T_SECS" ]]; then
  echo "[info] fallback ffmpeg -t $FFMPEG_T_SECS from m3u8"
  if ! ffmpeg -y -t "$FFMPEG_T_SECS" -i "$STREAM" -vn -acodec copy -movflags +faststart "$FINAL_FILE"; then
    echo "[error] ffmpeg partial fetch failed"
    rm -rf "$TEMP_DIR"
    exit 1
  fi
else
  # 有的 m3u8 是相对路径，先推全，再下载到临时目录
  STREAMPATH=$(echo "$STREAM" | grep -Eo "(^.*[\/])" || true)
  awk -v base="$STREAMPATH" '
    /^#/ {print; next}
    /^https?:\/\// {print; next}
    {print base $0}
  ' "$TEMP_DIR/stream.m3u8" > "$TEMP_DIR/modified.m3u8"

  aria2c -x 10 --dir "$TEMP_DIR" --console-log-level warn --auto-file-renaming=false --allow-overwrite=true --remove-control-file=true -i "$TEMP_DIR/modified.m3u8"

  # 将文件名中的查询参数去掉（aria2 可能保留 ?type=live）
  find "$TEMP_DIR" -maxdepth 1 -type f -name '*\?*' | while read -r f; do
    clean="${f%%\?*}"
    mv "$f" "$clean"
  done

  # 生成指向本地分片的 m3u8
  awk -v dir="$TEMP_DIR" '{
    if ($0 !~ /^#/ && $0 !~ /^https?:\/\//) {
      sub(/\?.*$/, "", $0);
      print dir "/" $0;
    } else if ($0 ~ /^https?:\/\//) {
      file=$0;
      sub(/^.*\//,"",file);
      sub(/\?.*$/,"",file);
      print dir "/" file;
    } else print $0
  }' "$TEMP_DIR/stream.m3u8" > "$TEMP_DIR/local.m3u8"

  # 合并为 m4a
  if ! ffmpeg -y -protocol_whitelist file,concat -i "$TEMP_DIR/local.m3u8" -vn -acodec copy -movflags +faststart "$FINAL_FILE"; then
    echo "[error] ffmpeg merge failed"
    rm -rf "$TEMP_DIR"
    exit 1
  fi
fi

# 清理
rm -rf "$TEMP_DIR"

echo "Saved: $FINAL_FILE"
