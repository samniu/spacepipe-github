from faster_whisper import WhisperModel
import sys, json, pathlib, torch

wav = pathlib.Path(sys.argv[1])
out = pathlib.Path(sys.argv[2])

# 自动检测设备
device = "cuda" if torch.cuda.is_available() else "cpu"
compute = "float16" if device == "cuda" else "int8"

print(f"[info] device = {device}, compute_type = {compute}")

# 可选模型: tiny / base / small / medium / large-v3
model = WhisperModel("small", device=device, compute_type=compute)

# 开始识别
segments, info = model.transcribe(str(wav), vad_filter=True)
print("Detected language:", info.language)

results = []
for seg in segments:
    results.append({
        "start": seg.start,
        "end": seg.end,
        "text": seg.text.strip()
    })

with open(out, "w") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"✅ Transcription saved to {out}")