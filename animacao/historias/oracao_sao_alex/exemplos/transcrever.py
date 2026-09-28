import json, sys
from faster_whisper import WhisperModel
m = WhisperModel("small", device="cpu", compute_type="int8")
segs, info = m.transcribe(r"C:\Users\Filipe Pereira\Downloads\oracao.wav", language="pt", word_timestamps=True, vad_filter=True)
out = []
for s in segs:
    for w in s.words:
        out.append({"w": w.word.strip(), "t0": round(w.start, 3), "t1": round(w.end, 3)})
json.dump(out, open(r"F:\Projeto IA\animacao\historias\oracao_sao_alex\exemplos\palavras.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(" ".join(o["w"] for o in out))
print(len(out), "palavras")
