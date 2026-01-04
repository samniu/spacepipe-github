# quick_diarize.py  — 仅处理音频前 N 分钟做快速验证
import os, sys, csv, argparse, pathlib, torch, torchaudio
from pyannote.audio import Pipeline
from pyannote.audio.pipelines.utils.hook import ProgressHook

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio", help="输入音频（建议 audio_16k.wav）")
    ap.add_argument("outdir", help="输出目录（将写 segments_quick.csv/RTTM）")
    ap.add_argument("--minutes", type=float, default=2.0, help="仅处理前 N 分钟，默认 2")
    ap.add_argument("--num", type=int, default=None, help="已知说话人人数（可选）")
    ap.add_argument("--min", dest="min_spk", type=int, default=None, help="最少说话人（可选）")
    ap.add_argument("--max", dest="max_spk", type=int, default=None, help="最多说话人（可选）")
    args = ap.parse_args()

    wav_path = pathlib.Path(args.audio).resolve()
    out_dir  = pathlib.Path(args.outdir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # 读取前 N 分钟到内存（更快）
    waveform, sr = torchaudio.load(str(wav_path))
    max_samples = int(args.minutes * 60 * sr)
    waveform = waveform[:, :max_samples] if waveform.shape[-1] > max_samples else waveform

    # 加载 pipeline（使用环境变量 HF_TOKEN 或已登录的缓存）
    hf_token = os.getenv("HF_TOKEN", None) or True
    try:
        pipe = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", token=hf_token)
    except TypeError:
        pipe = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", use_auth_token=hf_token)

    # 设备选择：MPS (Apple 芯片) > CUDA > CPU
    device = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")
    pipe.to(torch.device(device))
    print(f"[info] device = {device}; duration ≈ {waveform.shape[-1]/sr:.1f}s")

    # 跑推理（带进度钩子，小而直观）
    with ProgressHook() as hook:
        diar = pipe({"waveform": waveform, "sample_rate": sr},
                    hook=hook,
                    num_speakers=args.num,
                    min_speakers=args.min_spk,
                    max_speakers=args.max_spk)

    # 输出（CSV + RTTM）
    csv_path  = out_dir / "segments_quick.csv"
    rttm_path = out_dir / "segments_quick.rttm"

    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["speaker","start","end"])
        for turn, _, spk in diar.itertracks(yield_label=True):
            w.writerow([spk, round(float(turn.start),2), round(float(turn.end),2)])

    with open(rttm_path, "w") as f:
        diar.write_rttm(f)

    print(f"[done] wrote: {csv_path}")
    print(f"[done] wrote: {rttm_path}")

if __name__ == "__main__":
    main()
