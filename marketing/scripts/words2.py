from faster_whisper import WhisperModel
m = WhisperModel("small", device="cpu", compute_type="int8")
for name in ["IMG_5979","IMG_1844"]:
    segs,_ = m.transcribe(f"public/audio/{name}.wav", language="es", word_timestamps=True)
    print(f"\n===== {name} =====")
    for s in segs:
        for w in s.words:
            print(f"{w.start:6.2f}-{w.end:6.2f}  {w.word}")
