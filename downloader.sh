#!/usr/bin/env bash
set -euo pipefail

# 用法: ./downloader.sh <space_url> [browser] [out_root]
# 例子: ./downloader.sh "https://twitter.com/i/spaces/XXXX" chrome "$HOME/Downloads/spaces"

SPACEURL="${1:-}"
BROWSER="${2:-chrome}"   # 默认 chrome，可改 firefox/edge/...
OUT_ROOT="${3:-$HOME/Downloads/spaces}"

if [[ -z "$SPACEURL" ]]; then
  echo "Usage: $0 <space_url> [browser] [out_root]"
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

# 临时文件夹
TEMP_DIR="$TARGET_DIR/.temp_chunks"
mkdir -p "$TEMP_DIR"

# 下载 m3u8
wget "$STREAM" -O "$TEMP_DIR/stream.m3u8"

# 有的 m3u8 是相对路径，先推全，再下载到临时目录
STREAMPATH=$(echo "$STREAM" | grep -Eo "(^.*[\/])" || true)
sed -E "s|(^[^.#]+\.aac$)|$STREAMPATH\1|g" "$TEMP_DIR/stream.m3u8" > "$TEMP_DIR/modified.m3u8"

aria2c -x 10 --dir "$TEMP_DIR" --console-log-level warn -i "$TEMP_DIR/modified.m3u8"

# 生成指向本地分片的 m3u8
awk -v dir="$TEMP_DIR" '{
  if ($0 ~ /\.aac$/ && $0 !~ /^#/) print dir "/" $0; else print $0
}' "$TEMP_DIR/stream.m3u8" > "$TEMP_DIR/local.m3u8"

# 合并为 m4a
ffmpeg -y -protocol_whitelist file,concat -i "$TEMP_DIR/local.m3u8" -vn -acodec copy -movflags +faststart "$FINAL_FILE"

# 清理
rm -rf "$TEMP_DIR"

echo "Saved: $FINAL_FILE"
