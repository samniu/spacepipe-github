# Spacepipe: X Spaces Audio Pipeline & Web UI

Minimal toolkit to download an X/Twitter Space, diarize speakers, run Whisper ASR, smooth segments, split by speaker/topic, and export transcripts/summaries. Includes a small web UI to kick off jobs locally.

## Quick start
```bash
cd spacepipe-github
# ensure dependencies are installed (see below)
python3 webapp.py --host 127.0.0.1 --port 8000
# open http://127.0.0.1:8000 and submit a Space URL (uses browser cookies via yt-dlp)
```

CLI pipeline (single run):
```bash
bash run_space_pipeline.sh "https://twitter.com/i/spaces/XXXX" chrome ~/Downloads/spaces
```
- Arguments: `<space_url> [browser_cookie_source] [out_root]`
- Requirements: `yt-dlp`, `aria2c`, `ffmpeg` on PATH; browser cookies available for yt-dlp.

## Web UI
- Standard-library WSGI server (no Flask). Starts background jobs, shows status and logs.
- Logs live under `web_logs/` (created at runtime).
- Form fields: Space URL, browser (default `chrome`), output root (default `~/Downloads/spaces`).

## Outputs (per Space)
- `<date-title>.m4a`, `audio_16k.wav`, diarization CSV/RTTM, `asr.json`, smoothed segments, topic splits, speaker splits, `transcript.(txt|srt|md)`, `summary.(md|json)`, `topics/`, `speakers/`.

## Dependencies
System: `yt-dlp`, `aria2c`, `ffmpeg`.

Python (suggest virtualenv):
```
pip install -r requirements.txt
# and authenticate HF if needed:
huggingface-cli login  # or export HF_TOKEN=...
```

## License
MIT License (see `LICENSE`).

## Notes
- `diarize.py` uses `pyannote/speaker-diarization-3.1`; requires HF auth and accepts terms.
- `asr_whisper.py` uses `faster-whisper` and auto-selects CUDA/CPU (MPS via torch if available).
- `topic_seg.py` uses `sentence-transformers` (MiniLM) + `ruptures`.
- `quick_diarize.py` lets you process first N minutes for fast checks.
- Scripts call `python3` explicitly in `run_space_pipeline.sh`.

## Deploy to GitHub
Inside this folder:
```bash
git init
git add .
git commit -m "Add space pipeline and web UI"
git remote add origin <your-repo-url>
git push -u origin main
```
