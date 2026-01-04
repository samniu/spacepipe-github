# diarize.py
import os, sys, pathlib, csv
import torch
from pyannote.audio import Pipeline
from pyannote.audio.core.task import Specifications, Problem, Resolution

wav_path = pathlib.Path(sys.argv[1]).resolve()
out_dir = pathlib.Path(sys.argv[2]).resolve()
out_dir.mkdir(parents=True, exist_ok=True)

hf_token = os.getenv("HF_TOKEN", None)

# torch 2.6+ defaults weights_only=True; allow pyannote checkpoints to load
try:
    torch.serialization.add_safe_globals(
        [torch.torch_version.TorchVersion, Specifications, Problem, Resolution]
    )
except Exception:
    pass

def load_pipeline(token):
    try:
        # pyannote.audio >=4 uses token=
        return Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", token=token)
    except TypeError:
        # older signature
        return Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", use_auth_token=token)

try:
    pipeline = load_pipeline(hf_token or True)
except Exception as e:
    print("\n[ERROR] 无法下载/加载 pyannote/speaker-diarization-3.1：", e)
    print("请确认：1) 已登录 huggingface-cli；2) 已在模型页点击 Access/同意条款；")
    print("       3) 如在公司/校园网络，检查代理或重试；4) 如缓存损坏可清理后再试：")
    print("          rm -rf ~/.cache/huggingface/hub/models--pyannote--speaker-diarization-3.1\n")
    sys.exit(1)

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
