"""Marcas de boca a partir dos FONEMAS da fala (funciona em português), no mesmo formato JSON do Rhubarb.

O Rhubarb reconhece fonemas com um modelo de inglês e erra bastante em português. Aqui quem reconhece
é o wav2vec2 multilíngue de fonemas (facebook/wav2vec2-lv-60-espeak-cv-ft, IPA a cada 20 ms), e cada
fonema vira uma das bocas do Rhubarb (A..H, X).

    F:\\Projeto IA\\ferramentas\\JoyVASA\\.venv\\Scripts\\python.exe fonemas.py AUDIO.wav [SAIDA.json]
"""
import json, sys, unicodedata
from pathlib import Path

import numpy as np
import torch
import librosa

MODELO = Path(__file__).parent / "modelos" / "wav2vec2-fonemas"
PASSO = 0.02          # segundos por quadro de saída do wav2vec2
MAX_FONEMA = 0.22     # um fonema não segura a boca mais que isso; depois disso é pausa (X)

# fonema (letra base do IPA) -> boca do Rhubarb
BOCA = {}
for ch in "mbp":
    BOCA[ch] = "A"                                  # lábios fechados
for ch in "fv":
    BOCA[ch] = "G"                                  # dente no lábio
for ch in "lɫʎ":
    BOCA[ch] = "H"                                  # língua no céu da boca
for ch in "uʊwy":
    BOCA[ch] = "F"                                  # biquinho
for ch in "oɔɒøœɵ":
    BOCA[ch] = "E"                                  # arredondada
for ch in "aɑæɐ":
    BOCA[ch] = "D"                                  # bem aberta
for ch in "eɛəɜʌ":
    BOCA[ch] = "C"                                  # aberta média
# o resto (consoantes, i, j) = "B": dentes quase juntos


def base(token):
    """Primeira letra do token IPA, sem diacríticos (til, duração, acento)."""
    for ch in unicodedata.normalize("NFD", token):
        if not unicodedata.combining(ch) and ch not in "ːˈˌ":
            return ch
    return ""


def boca_de(token):
    return BOCA.get(base(token), "B")


_cache = {}


def carregar():
    if not _cache:
        from transformers import Wav2Vec2ForCTC
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        m = Wav2Vec2ForCTC.from_pretrained(str(MODELO)).to(dev).eval()
        vocab = json.load(open(MODELO / "vocab.json", encoding="utf-8"))
        _cache.update(modelo=m, dev=dev, id2tok={v: k for k, v in vocab.items()}, pad=m.config.pad_token_id)
    return _cache


@torch.no_grad()
def reconhecer(audio_path):
    """Lista de (inicio_s, fim_s, token_ipa): um item por fonema reconhecido."""
    c = carregar()
    wav, _ = librosa.load(str(audio_path), sr=16000, mono=True)
    x = torch.from_numpy((wav - wav.mean()) / (wav.std() + 1e-7)).float()[None].to(c["dev"])
    ids = c["modelo"](x).logits[0].argmax(-1).cpu().numpy()
    fon, i = [], 0
    while i < len(ids):
        j = i
        while j + 1 < len(ids) and ids[j + 1] == ids[i]:
            j += 1
        if ids[i] != c["pad"]:
            tok = c["id2tok"].get(int(ids[i]), "")
            if tok and tok not in ("<s>", "</s>", "<unk>", "|", " "):
                fon.append([i * PASSO, (j + 1) * PASSO, tok])
        i = j + 1
    return fon, len(wav) / 16000


def marcas(fon, dur):
    """Converte fonemas em marcas de boca contíguas (formato Rhubarb): cada fonema segura a boca
    até o próximo começar (no máximo MAX_FONEMA); o que sobra vira X (pausa)."""
    cues, t = [], 0.0
    for k, (ini, fim, tok) in enumerate(fon):
        prox = fon[k + 1][0] if k + 1 < len(fon) else dur
        if ini > t + 1e-6:
            cues.append({"start": t, "end": ini, "value": "X"})
        fim_boca = min(prox, max(fim, ini + MAX_FONEMA))
        cues.append({"start": ini, "end": fim_boca, "value": boca_de(tok), "fonema": tok})
        t = fim_boca
    if t < dur:
        cues.append({"start": t, "end": dur, "value": "X"})
    # junta vizinhos com a mesma boca
    junto = []
    for c in cues:
        if junto and junto[-1]["value"] == c["value"]:
            junto[-1]["end"] = c["end"]
            junto[-1]["fonema"] = junto[-1].get("fonema", "") + c.get("fonema", "")
        else:
            junto.append(dict(c))
    for c in junto:
        c["start"], c["end"] = round(c["start"], 3), round(c["end"], 3)
    return junto


def gerar(audio_path, saida=None):
    fon, dur = reconhecer(audio_path)
    j = {"metadata": {"soundFile": str(audio_path), "duration": round(dur, 3), "motor": "wav2vec2-fonemas",
                      "fonemas": " ".join(f[2] for f in fon)},
         "mouthCues": marcas(fon, dur)}
    if saida:
        json.dump(j, open(saida, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return j


if __name__ == "__main__":
    a = Path(sys.argv[1])
    s = Path(sys.argv[2]) if len(sys.argv) > 2 else a.with_suffix(".fonemas.json")
    j = gerar(a, s)
    print("fonemas:", j["metadata"]["fonemas"])
    print(" ".join(f"{c['value']}{c['start']:.2f}" for c in j["mouthCues"]))
    print("gravado:", s)
