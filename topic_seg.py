# topic_seg.py
import json, sys, pathlib, numpy as np
from sentence_transformers import SentenceTransformer
import ruptures as rpt

asr = json.load(open(sys.argv[1]))
out = pathlib.Path(sys.argv[2]); out.parent.mkdir(parents=True, exist_ok=True)

texts  = [r["text"] for r in asr]
starts = [r["start"] for r in asr]
ends   = [r["end"]   for r in asr]

min_len = 5        # 每段最少句子数
n_bkpt  = 8        # 期望主题数(可调/可自适应)

emb = SentenceTransformer("all-MiniLM-L6-v2")
X = emb.encode(texts, normalize_embeddings=True)

algo = rpt.KernelCPD(kernel="rbf", min_size=min_len).fit(X)
bkpts = algo.predict(n_bkpt)

chapters=[]; prev=0
for k in bkpts:
    s = starts[prev]; e = ends[k-1]
    rep = texts[(prev+k)//2] if k-prev>0 else texts[prev]
    chapters.append({"start": round(s,2), "end": round(e,2), "rep": rep})
    prev = k

# 简单合并短段（<25s）
merged=[]
for ch in chapters:
    if merged and (ch["end"]-ch["start"]<25):
        merged[-1]["end"]=ch["end"]
    else:
        merged.append(ch)

json.dump(merged, open(out,"w"), ensure_ascii=False, indent=2)
print("Chapters ->", out)
