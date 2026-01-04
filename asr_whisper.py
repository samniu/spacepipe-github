import sys, json, pathlib, torch

wav = pathlib.Path(sys.argv[1])
out = pathlib.Path(sys.argv[2])

# 自动检测设备
device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")

try:
    from faster_whisper import WhisperModel
    compute = "float16" if device == "cuda" else "int8"
    print(f"[info] using faster-whisper; device = {device}, compute_type = {compute}")
    model = WhisperModel("small", device=device, compute_type=compute)
    segments, info = model.transcribe(str(wav), vad_filter=True)
    print("Detected language:", info.language)
    results = [{"start": seg.start, "end": seg.end, "text": seg.text.strip()} for seg in segments]
except Exception as e:
    print(f"[warn] faster-whisper unavailable ({e}); falling back to openai-whisper.")
    import whisper

    model = whisper.load_model("small", device=device)
    # fp16 only on cuda
    result = model.transcribe(str(wav), fp16=(device == "cuda"))
    results = [
        {"start": float(seg["start"]), "end": float(seg["end"]), "text": seg["text"].strip()}
        for seg in result.get("segments", [])
    ]
    print("Detected language:", result.get("language"))

with open(out, "w") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"✅ Transcription saved to {out}")
