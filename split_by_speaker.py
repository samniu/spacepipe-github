# split_by_speaker.py
import os, sys, csv, pathlib, subprocess
src_wav = pathlib.Path(sys.argv[1]).resolve()
csv_path = pathlib.Path(sys.argv[2]).resolve()
out_root = pathlib.Path(sys.argv[3]).resolve()
out_root.mkdir(parents=True, exist_ok=True)

from collections import defaultdict
segs=defaultdict(list)
with open(csv_path) as f:
    r=csv.DictReader(f)
    for row in r:
        segs[row["speaker"]].append((float(row["start"]), float(row["end"])))

for spk, items in segs.items():
    spkdir = out_root/spk; spkdir.mkdir(parents=True, exist_ok=True)
    for i,(st,ed) in enumerate(items):
        out = spkdir/f"{i:04d}_{st:0.2f}_to_{ed:0.2f}.wav"
        dur = ed-st
        subprocess.run(["ffmpeg","-y","-ss",str(st),"-t",str(dur),"-i",str(src_wav),
                        "-acodec","copy",str(out)], check=True)
print("Speakers exported to:", out_root)
