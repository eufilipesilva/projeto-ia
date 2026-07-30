# -*- coding: utf-8 -*-
"""
TESTE 1: OmniVoice batch nativo vs loop atual
Roda com: python app/estudio/tools/teste_batch_omni.py
(dentro do venv_omni, com o servidor PARADO para ter VRAM livre)

Mede o tempo de sintetizar 6 frases curtas de 2 formas:
  A) Loop atual: 1 chamada generate() por frase
  B) Batch nativo: 1 chamada generate() com lista de frases
"""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import torch
import soundfile as sf

print("Carregando OmniVoice... (pode demorar ~20s)")
from omnivoice import OmniVoice, OmniVoiceGenerationConfig

t_load = time.time()
model = OmniVoice.from_pretrained(
    "k2-fsa/OmniVoice",
    device_map="auto",
    dtype=torch.float16,
    load_asr=False,
    token=False,
)
print(f"Modelo carregado em {time.time()-t_load:.1f}s")

import motor_v2 as motor

# Usa a Dora como voz de referência (arquivo existe na galeria)
VOZ_REF = os.path.join(os.path.dirname(__file__), "..", "vozes", "Dora (PT-F).wav")
if not os.path.exists(VOZ_REF):
    print(f"ERRO: arquivo não encontrado: {VOZ_REF}")
    print("Ajuste VOZ_REF para qualquer .wav da pasta vozes/")
    sys.exit(1)

perfil = motor.perfil_voz(VOZ_REF)
prompt = motor._criar_prompt_voz(model, perfil)

cfg = OmniVoiceGenerationConfig(
    num_step=32,
    guidance_scale=3.0,
    class_temperature=0.0,
    postprocess_output=False,
)

TEXTOS = [
    "Feche os olhos suavemente.",
    "Respire fundo e solte devagar.",
    "Sinta o peso do seu corpo relaxar.",
    "Cada respiração te leva mais fundo.",
    "Você está seguro e em paz.",
    "Permita-se descansar completamente.",
]

# ──────────────────────────────────────────────────────────────────────────────
print(f"\n{'='*50}")
print(f"TESTE A: Loop atual ({len(TEXTOS)} frases, 1 chamada por vez)")
print(f"{'='*50}")
torch.cuda.synchronize()
t0 = time.time()
results_loop = []
for i, txt in enumerate(TEXTOS):
    wav = model.generate(
        motor._com_ponto(txt),
        language="pt",
        voice_clone_prompt=prompt,
        generation_config=cfg,
    )[0]
    results_loop.append(wav)
    print(f"  Frase {i+1}: {len(wav)/motor.SR:.1f}s de áudio")
torch.cuda.synchronize()
t_loop = time.time() - t0
print(f"\n→ Tempo total LOOP: {t_loop:.1f}s  ({t_loop/len(TEXTOS):.1f}s por frase)")

# ──────────────────────────────────────────────────────────────────────────────
print(f"\n{'='*50}")
print(f"TESTE B: Batch nativo ({len(TEXTOS)} frases, 1 chamada só)")
print(f"{'='*50}")
vram_antes = torch.cuda.memory_allocated() / 1e9
print(f"VRAM usada antes do batch: {vram_antes:.2f} GB")

torch.cuda.synchronize()
t0 = time.time()
try:
    results_batch = model.generate(
        [motor._com_ponto(t) for t in TEXTOS],
        language="pt",
        voice_clone_prompt=[prompt] * len(TEXTOS),
        generation_config=cfg,
    )
    torch.cuda.synchronize()
    t_batch = time.time() - t0
    vram_depois = torch.cuda.memory_allocated() / 1e9
    print(f"VRAM usada durante batch: {vram_depois:.2f} GB")
    for i, wav in enumerate(results_batch):
        print(f"  Frase {i+1}: {len(wav)/motor.SR:.1f}s de áudio")
    print(f"\n→ Tempo total BATCH: {t_batch:.1f}s  ({t_batch/len(TEXTOS):.1f}s por frase)")
    print(f"\n{'='*50}")
    print(f"RESULTADO FINAL:")
    print(f"  Loop:  {t_loop:.1f}s")
    print(f"  Batch: {t_batch:.1f}s")
    print(f"  Ganho: {t_loop/t_batch:.1f}x mais rápido")
    print(f"  Economia: {t_loop - t_batch:.0f}s numa meditação de 6 frases")
except torch.cuda.OutOfMemoryError:
    print("ERRO: VRAM insuficiente para batch com 6 frases!")
    print("Tente reduzir TEXTOS para 3 frases e rodar de novo.")
    print("(Batch usa mais VRAM que loop — pode não caber na RTX 2060 6GB)")
except Exception as e:
    print(f"ERRO inesperado: {e}")
