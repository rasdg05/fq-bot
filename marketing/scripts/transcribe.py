#!/usr/bin/env python3
"""Transcribe los clips (espanol) con timestamps para analizar el discurso."""
import json
import os
import sys
from pathlib import Path
from faster_whisper import WhisperModel

AUDIO = Path(__file__).resolve().parent.parent / "public" / "audio"
OUT = AUDIO / "transcripts.json"

model = WhisperModel("small", device="cpu", compute_type="int8")

result = {}
for wav in sorted(AUDIO.glob("*.wav")):
    name = wav.stem
    segments, info = model.transcribe(str(wav), language="es", vad_filter=True)
    segs = [{"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()} for s in segments]
    result[name] = segs
    print(f"\n===== {name} =====")
    for s in segs:
        print(f"[{s['start']:6.2f}-{s['end']:6.2f}] {s['text']}")
    sys.stdout.flush()

OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2))
print(f"\nGuardado: {OUT}")
