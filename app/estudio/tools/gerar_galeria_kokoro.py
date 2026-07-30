# -*- coding: utf-8 -*-
"""
Gera a galeria de vozes pt-BR de referência usando o Kokoro TTS v1.0 (local).

As vozes inglesas do Kokoro carregam sotaque nos fonemas difíceis do português
(nasais, lh/nh, rr, palatalização ti/di). Para ter variedade de timbre mantendo
o pt-BR, fazemos BLEND dos embeddings (vetores de estilo) das vozes do Kokoro:
ex. 0.6*pf_dora + 0.4*af_bella → um timbre novo, mais "abrasileirado".

Cada clipe é gerado a partir de uma frase fixa conhecida — então o ref_text
(transcrição) já é sabido e salvamos junto num .txt, evitando o ASR do OmniVoice
(que quebra por falta de ffmpeg/torchcodec).

Rodar com o Python do venv_omni:
    .venv_omni/Scripts/python.exe app/estudio/tools/gerar_galeria_kokoro.py
"""
import os
import numpy as np
import soundfile as sf
from kokoro_onnx import Kokoro

AQUI       = os.path.dirname(os.path.abspath(__file__))
ESTUDIO    = os.path.dirname(AQUI)                       # app/estudio
RAIZ       = os.path.dirname(os.path.dirname(ESTUDIO))   # f:/Projeto IA
KOKORO_DIR = os.path.join(RAIZ, "app", "laboratorios", "voices_kokoro")
VOZES_DIR  = os.path.join(ESTUDIO, "vozes")

MODELO = os.path.join(KOKORO_DIR, "kokoro-v1.0.onnx")
VOICES = os.path.join(KOKORO_DIR, "voices-v1.0.bin")

# Frase de referência (vira o ref_text de TODAS as vozes, pois todas a pronunciam)
FRASE = "Olá, eu sou a sua narradora. Respire fundo e deixe a sua mente descansar."

# Galeria: (arquivo de saída, lista de (voz_kokoro, peso))
# As 2 primeiras são puras (pt-BR nativas); as demais são blends para variar o timbre.
GALERIA = [
    ("Dora (PT-F).wav",        [("pf_dora", 1.0)]),
    ("Santa (PT-M).wav",       [("pm_santa", 1.0)]),
    ("Bia (PT-F clara).wav",   [("pf_dora", 0.6), ("af_bella", 0.4)]),
    ("Nina (PT-F suave).wav",  [("pf_dora", 0.6), ("af_nicole", 0.4)]),
    ("Ceu (PT-F).wav",         [("pf_dora", 0.55), ("af_sky", 0.45)]),
    ("Isa (PT-F).wav",         [("pf_dora", 0.5), ("bf_isabella", 0.5)]),
    ("Yan (PT-M grave).wav",   [("pm_santa", 0.6), ("zm_yunyang", 0.4)]),
]


def main():
    if not os.path.exists(MODELO) or not os.path.exists(VOICES):
        raise SystemExit(f"Modelo Kokoro não encontrado em {KOKORO_DIR}")
    os.makedirs(VOZES_DIR, exist_ok=True)

    print("Carregando Kokoro...")
    k = Kokoro(MODELO, VOICES)

    def estilo(blend):
        """Soma ponderada dos vetores de estilo das vozes do blend."""
        vetor = None
        for nome, peso in blend:
            s = peso * np.asarray(k.get_voice_style(nome))
            vetor = s if vetor is None else vetor + s
        return vetor.astype(np.float32)

    for arq, blend in GALERIA:
        voz = estilo(blend)
        audio, sr = k.create(FRASE, voz, lang="pt-br")
        cam_wav = os.path.join(VOZES_DIR, arq)
        sf.write(cam_wav, audio, sr)
        # ref_text cacheado ao lado (mesmo nome, extensão .txt)
        cam_txt = os.path.splitext(cam_wav)[0] + ".txt"
        with open(cam_txt, "w", encoding="utf-8") as f:
            f.write(FRASE)
        receita = " + ".join(f"{p:.0%} {n}" for n, p in blend)
        print(f"  {arq:24s} ({len(audio)/sr:.1f}s)  [{receita}]")

    print(f"\nPronto! {len(GALERIA)} vozes em {VOZES_DIR}")


if __name__ == "__main__":
    main()
