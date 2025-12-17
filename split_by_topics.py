# split_by_topics.py
import json, sys, pathlib, subprocess
base = pathlib.Path(sys.argv[1]).resolve()
chap = json.load(open(base/"chapters.json"))
src  = base/"audio_16k.wav"
outd = base/"topics"; outd.mkdir(exist_ok=True)
for i,c in enumerate(chap):
    dur = c["end"]-c["start"]
    out = outd/f"{i:02d}_{int(c['start'])}-{int(c['end'])}.wav"
    subprocess.run(["ffmpeg","-y","-ss",str(c["start"]),"-t",str(dur),"-i",str(src),
                    "-acodec","copy",str(out)], check=True)
print("Topics exported:", outd)
