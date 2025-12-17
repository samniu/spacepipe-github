# diarize.py
import os, sys, pathlib, csv
from pyannote.audio import Pipeline

wav_path = pathlib.Path(sys.argv[1]).resolve()
out_dir = pathlib.Path(sys.argv[2]).resolve()
out_dir.mkdir(parents=True, exist_ok=True)

hf_token = os.getenv("HF_TOKEN", None)

try:
    if hf_token:
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=hf_token
        )
    else:
        # 已经 huggingface-cli login 的情况下可用 True
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=True
        )
except Exception as e:
    print("\n[ERROR] 无法下载/加载 pyannote/speaker-diarization-3.1：", e)
    print("请确认：1) 已登录 huggingface-cli；2) 已在模型页点击 Access/同意条款；")
    print("       3) 如在公司/校园网络，检查代理或重试；4) 如缓存损坏可清理后再试：")
    print("          rm -rf ~/.cache/huggingface/hub/models--pyannote--speaker-diarization-3.1\n")
    sys.exit(1)

# pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1")
diarization = pipeline(wav_path)

# RTTM
with open(out_dir/"segments.rttm","w") as f:
    diarization.write_rttm(f)

# CSV
with open(out_dir/"segments.csv","w",newline="") as f:
    w=csv.writer(f)
    w.writerow(["speaker","start","end"])
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        w.writerow([speaker, round(turn.start,2), round(turn.end,2)])

print("Diarization saved to:", out_dir)
