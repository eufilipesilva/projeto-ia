#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gera um som ambiente de bar (murmúrio de pessoas + tilintar de copos).
100% local, sem download, sem licença. Salva 'fundo_bar.wav'.

Pode rodar sozinho:  python fundo_bar.py
Ou ser importado:    from fundo_bar import garantir_fundo
"""

import os
import wave
import numpy as np

SR = 22050          # taxa de amostragem
DUR = 20            # segundos (o arquivo é tocado em loop)


def _passa_banda(x, sr, baixo, alto):
    """Filtro passa-banda via FFT (sem dependências externas)."""
    X = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), 1 / sr)
    X[(freqs < baixo) | (freqs > alto)] = 0
    return np.fft.irfft(X, n=len(x))


def gerar(caminho="fundo_bar.wav"):
    rng = np.random.default_rng(7)
    n = SR * DUR

    # 1) Murmúrio: ruído na faixa da voz humana
    murmurio = _passa_banda(rng.standard_normal(n), SR, 150, 2200)

    # 2) Envelope lento (vozes que sobem e descem, vai e vem da multidão)
    env = _passa_banda(rng.standard_normal(n), SR, 0.1, 5)
    env -= env.min()
    env /= (env.max() + 1e-9)
    env = 0.35 + 0.65 * env
    sig = murmurio * env

    # 3) Rumor grave de fundo (ambiente do salão)
    grave = _passa_banda(np.cumsum(rng.standard_normal(n)), SR, 30, 180)
    grave /= (np.abs(grave).max() + 1e-9)
    sig = sig / (np.abs(sig).max() + 1e-9) * 0.85 + grave * 0.15

    # 4) Tilintar ocasional de copos
    for _ in range(10):
        pos = rng.integers(0, n - 3000)
        t = np.arange(3000)
        f = rng.uniform(1800, 3200)
        clink = np.sin(2 * np.pi * f * t / SR) * np.exp(-t / 400)
        sig[pos:pos + 3000] += clink * 0.06

    # 5) Normaliza e faz loop sem emenda (crossfade início/fim)
    sig /= (np.abs(sig).max() + 1e-9)
    xf = SR  # 1 segundo de crossfade
    fade = np.linspace(0, 1, xf)
    sig[:xf] = sig[:xf] * fade + sig[-xf:] * (1 - fade)
    sig = sig[:-xf]

    # Converte para 16-bit e grava
    audio = (sig * 0.6 * 32767).astype(np.int16)
    with wave.open(caminho, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(audio.tobytes())

    return caminho


def garantir_fundo(caminho="fundo_bar.wav"):
    """Cria o arquivo se ainda não existir. Retorna o caminho ou None se falhar."""
    if os.path.exists(caminho):
        return caminho
    try:
        return gerar(caminho)
    except Exception as e:
        print(f"[AVISO] Não consegui gerar o fundo de bar: {e}")
        return None


if __name__ == "__main__":
    destino = gerar()
    print(f"[OK] Som de bar gerado: {destino}")
