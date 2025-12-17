# smooth_segments.py
import csv, json, sys, pathlib

MIN_GAP_SAME_SPK   = 0.6
SHORT_INTRUSION    = 1.2
COLLAR             = 0.2
MIN_SEG_DURATION   = 2.5

FILLERS = set(["嗯","啊","呃","额","对","好","行","ok","okay","yes","yeah",
               "right","嗯哼","哈哈","lol","哦","哇","噢","唔","嗷"])

def load_segments_csv(path):
    segs=[]
    with open(path) as f:
        r=csv.DictReader(f)
        for row in r:
            segs.append({"speaker": row["speaker"],
                         "start": float(row["start"]), "end": float(row["end"])})
    return sorted(segs, key=lambda x: x["start"])

def load_asr_json(path): return json.load(open(path))
def dur(s): return s["end"]-s["start"]

def text_stats(asr, s, e):
    txts=[]
    for u in asr:
        if u["end"]<=s or u["start"]>=e: 
            continue
        txts.append(u["text"])
    text=" ".join(txts).strip()
    tokens=[t.strip("，。！？,.!?… ") for t in text.split()]
    tokens=[t for t in tokens if t]
    if tokens:
        filler=sum(1 for t in tokens if t.lower() in FILLERS)/len(tokens)
    else:
        filler=1.0
    return len(tokens), filler

def merge_same_speaker(segs):
    out=[]
    for s in segs:
        if out and s["speaker"]==out[-1]["speaker"] and s["start"]-out[-1]["end"]<MIN_GAP_SAME_SPK:
            out[-1]["end"]=max(out[-1]["end"], s["end"])
        else:
            out.append(s.copy())
    return out

def swallow_intrusions(segs, asr):
    out=[]; i=0
    while i<len(segs):
        if 0<i<len(segs)-1:
            cur=segs[i]; L=segs[i-1]; R=segs[i+1]
            if cur["speaker"]!=L["speaker"] and cur["speaker"]!=R["speaker"] and dur(cur)<=SHORT_INTRUSION:
                tok, filler=text_stats(asr, cur["start"], cur["end"])
                if tok<=3 or filler>=0.5:
                    if L["speaker"]==R["speaker"]:
                        L["end"]=R["end"]; i+=2; continue
                    if dur(L)>=dur(R): L["end"]=max(L["end"],cur["end"])
                    else: R["start"]=min(R["start"],cur["start"])
                    i+=1; continue
        out.append(segs[i]); i+=1
    return out

def apply_collar(segs):
    out=[segs[0].copy()]
    for s in segs[1:]:
        prev=out[-1]
        if s["start"]-prev["end"]<COLLAR:
            if dur(prev)>=dur(s): prev["end"]=max(prev["end"], s["end"])
            else: s["start"]=min(s["start"], prev["start"]); out[-1]=s
        else:
            out.append(s.copy())
    return out

def enforce_min_duration(segs):
    out=[]
    for s in segs:
        if dur(s)<MIN_SEG_DURATION and out:
            out[-1]["end"]=max(out[-1]["end"], s["end"])
        else:
            out.append(s.copy())
    return out

def main(seg_csv, asr_json, out_csv):
    segs = load_segments_csv(seg_csv)
    asr  = load_asr_json(asr_json)
    segs = merge_same_speaker(segs)
    segs = swallow_intrusions(segs, asr)
    segs = apply_collar(segs)
    segs = enforce_min_duration(segs)
    segs = merge_same_speaker(segs)
    with open(out_csv,"w",newline="") as f:
        w=csv.DictWriter(f, fieldnames=["speaker","start","end","duration"])
        w.writeheader()
        for s in segs:
            w.writerow({**s,"duration": round(dur(s),2)})

if __name__=="__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
