#!/usr/bin/env python3
"""Generate transcripts (txt/srt) and simple extractive summaries from ASR output."""
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import List, Dict, Any


def load_asr(base: Path) -> List[Dict[str, Any]]:
    """Load ASR output with a sensible fallback (asr.json -> asr_quick.json)."""
    primary = base / "asr.json"
    quick = base / "asr_quick.json"
    if primary.exists():
        return json.load(open(primary))
    if quick.exists():
        print("[warn] asr.json not found; using asr_quick.json")
        return json.load(open(quick))
    raise FileNotFoundError(f"Missing asr.json (or asr_quick.json) in {base}")


def load_chapters(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    return json.load(open(path))


def ts_fmt(sec: float, srt: bool = False) -> str:
    hours = int(sec // 3600)
    minutes = int((sec % 3600) // 60)
    seconds = int(sec % 60)
    millis = int(round((sec - int(sec)) * 1000))
    if srt:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def write_plain_transcript(asr: List[Dict[str, Any]], path: Path) -> None:
    lines = [f"[{ts_fmt(seg['start'])}] {seg['text'].strip()}" for seg in asr]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_srt(asr: List[Dict[str, Any]], path: Path) -> None:
    parts = []
    for i, seg in enumerate(asr, start=1):
        start = ts_fmt(seg["start"], srt=True)
        end = ts_fmt(seg["end"], srt=True)
        text = seg["text"].strip()
        parts.append(f"{i}\n{start} --> {end}\n{text}\n")
    path.write_text("\n".join(parts).strip() + "\n", encoding="utf-8")


STOPWORDS = set(
    [
        "the",
        "a",
        "an",
        "and",
        "or",
        "to",
        "of",
        "in",
        "for",
        "on",
        "is",
        "are",
        "am",
        "be",
        "was",
        "were",
        "that",
        "this",
        "with",
        "as",
        "by",
        "at",
        "from",
        "it",
        "its",
        "we",
        "you",
        "i",
        "me",
        "my",
        "our",
        "ours",
        "they",
        "them",
        "their",
        "theirs",
        "he",
        "she",
        "him",
        "her",
        "his",
        "hers",
        "but",
        "so",
        "if",
        "then",
        "嗯",
        "啊",
        "呃",
        "额",
        "对",
        "好",
        "行",
        "哦",
        "啊哈",
        "嗯哼",
        "就是",
        "然后",
    ]
)


def tokenize(sentence: str) -> List[str]:
    # Keep simple alphanum + CJK; all lowercase for English tokens.
    return re.findall(r"[\\w\\u4e00-\\u9fff']+", sentence.lower())


def split_sentences(text: str) -> List[str]:
    return [s.strip() for s in re.split(r"(?<=[。！？.!?])\\s*", text) if s.strip()]


def summarize_text(text: str, max_sentences: int = 3) -> List[str]:
    sentences = split_sentences(text)
    if not sentences:
        return []
    word_freq = Counter()
    for sent in sentences:
        for tok in tokenize(sent):
            if tok in STOPWORDS:
                continue
            word_freq[tok] += 1
    if not word_freq:
        return sentences[:max_sentences]

    scores = []
    for idx, sent in enumerate(sentences):
        score = sum(word_freq[tok] for tok in tokenize(sent) if tok not in STOPWORDS)
        scores.append((score, idx, sent))

    # Pick top-scoring sentences, keep original order for readability.
    top = sorted(scores, key=lambda x: (-x[0], x[1]))[:max_sentences]
    top_sorted = sorted(top, key=lambda x: x[1])
    return [t[2] for t in top_sorted]


def gather_text(asr: List[Dict[str, Any]], start: float, end: float) -> str:
    parts = []
    for seg in asr:
        if seg["end"] <= start or seg["start"] >= end:
            continue
        parts.append(seg["text"].strip())
    return " ".join(parts)


def summarize_chapters(
    chapters: List[Dict[str, Any]], asr: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    out = []
    for ch in chapters:
        text = gather_text(asr, ch["start"], ch["end"])
        summary = summarize_text(text, max_sentences=3)
        out.append(
            {
                "start": ch["start"],
                "end": ch["end"],
                "rep": ch.get("rep", ""),
                "summary": summary,
            }
        )
    return out


def write_summary_files(
    base: Path, overall: List[str], chapters: List[Dict[str, Any]]
) -> None:
    json.dump(
        {"overall": overall, "chapters": chapters},
        open(base / "summary.json", "w"),
        ensure_ascii=False,
        indent=2,
    )

    lines = ["# Summary", "## Overall"]
    if overall:
        for sent in overall:
            lines.append(f"- {sent}")
    else:
        lines.append("- (no content)")

    if chapters:
        lines.append("## Chapters")
        for idx, ch in enumerate(chapters):
            label = f"{ts_fmt(ch['start'])}-{ts_fmt(ch['end'])}"
            lines.append(f"{idx+1}. [{label}] {ch.get('rep','').strip()}")
            for sent in ch["summary"]:
                lines.append(f"   - {sent}")

    (base / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_markdown_transcript(
    base: Path, asr: List[Dict[str, Any]], chapters: List[Dict[str, Any]]
) -> None:
    lines = ["# Transcript"]
    if chapters:
        lines.append("\n## By Chapter")
        for idx, ch in enumerate(chapters):
            label = f"{ts_fmt(ch['start'])}-{ts_fmt(ch['end'])}"
            lines.append(f"\n### {idx+1}. {label}")
            for seg in asr:
                if seg["end"] <= ch["start"] or seg["start"] >= ch["end"]:
                    continue
                lines.append(f"- [{ts_fmt(seg['start'])}] {seg['text'].strip()}")
    else:
        lines.extend([f"- [{ts_fmt(seg['start'])}] {seg['text'].strip()}" for seg in asr])

    (base / "transcript.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    if len(sys.argv) < 2:
        print("Usage: post_export.py <target_dir_with_asr_json>")
        sys.exit(1)

    base = Path(sys.argv[1]).resolve()
    asr = load_asr(base)
    chapters = load_chapters(base / "chapters.json")

    write_plain_transcript(asr, base / "transcript.txt")
    write_srt(asr, base / "transcript.srt")
    write_markdown_transcript(base, asr, chapters)

    full_text = " ".join(seg["text"].strip() for seg in asr)
    overall_summary = summarize_text(full_text, max_sentences=5)
    chapter_summaries = summarize_chapters(chapters, asr) if chapters else []
    write_summary_files(base, overall_summary, chapter_summaries)

    print("Transcript + summaries saved to:", base)


if __name__ == "__main__":
    main()
