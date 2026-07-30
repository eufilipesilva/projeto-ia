# -*- coding: utf-8 -*-
"""Teste comparativo: 'era uma vez' vs 'eeera uma vez'."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, soundfile as sf
import motor_v2 as motor

PASTA     = os.path.dirname(os.path.abspath(__file__))
VOZES_DIR = os.path.join(PASTA, "vozes")
SAIDAS    = os.path.join(PASTA, "saidas")
WAV_REF   = os.path.join(VOZES_DIR, "Pandora.wav")
TXT_REF   = os.path.join(VOZES_DIR, "Pandora.txt")
os.makedirs(SAIDAS, exist_ok=True)

ref_text = open(TXT_REF, encoding="utf-8").read().strip() if os.path.exists(TXT_REF) else ""
perfil   = motor.perfil_voz(WAV_REF, ref_text=ref_text or None)

m      = motor.carregar_omni()
prompt = motor._criar_prompt_voz(m, perfil)
cfg    = motor._cfg(num_step=32, guidance_scale=3.0)

FRASES = [
    ("normal",    "Era uma vez."),
    ("eeera",     "ÉÉra uma veeez..."),
]

silencio = np.zeros(int(motor.SR * 0.8), dtype=np.float32)
segs = []

for nome, frase in FRASES:
    print(f"  [{nome}] {frase}")
    wav = m.generate(frase, language="pt", voice_clone_prompt=prompt,
                     speed=0.82, generation_config=cfg)[0]
    wav = np.asarray(wav, dtype=np.float32).squeeze()
    segs.append(wav)
    segs.append(silencio)

audio = np.concatenate(segs)
pico = np.abs(audio).max()
if pico > 0:
    audio = audio / pico * 0.85

saida = os.path.join(SAIDAS, "abertura_comparacao.wav")
sf.write(saida, audio, motor.SR)
print(f"Salvo: {saida}")
motor.descarregar_omni()
