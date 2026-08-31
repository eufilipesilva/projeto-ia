# -*- coding: utf-8 -*-
"""Fabrica a voz de cada personagem por BLEND de embeddings do Kokoro.

Este é o caminho que funciona, depois de dois que não funcionaram:

  1. Modo Design do OmniVoice — espaço estreito demais. Seis gerações com a
     mesma instrução variaram ~3 semitons: é a mesma voz repetida.
  2. Busca no áudio do projeto — o acervo tem 45 vozes femininas e só ~8
     masculinas, todas na mesma família grave. Não há timbre para distribuir.

O Kokoro está local (`laboratorios/voices_kokoro`) com 54 vozes, entre elas
três em português: `pf_dora`, `pm_alex` e `pm_santa`. O que o torna a solução é
que os vetores de estilo são SOMÁVEIS: `0.6*pm_alex + 0.4*am_onyx` produz um
timbre novo que continua pronunciando português. Em vez de procurar uma voz,
fabrica-se a voz que o `ELENCO_VOZES.md` descreve — e o espaço é contínuo.

A âncora portuguesa nunca fica abaixo de 55%: menos que isso e a fonética
começa a escorregar para o sotaque da voz misturada.

Limite conhecido: o F0 masculino do Kokoro não passa de ~146 Hz. Para os bichos
pequenos (rato, galo, pássaro) o agudo vem do FORMANTE, que encolhe o corpo sem
tocar no pitch e não deixa artefato — e um rato não precisa ler como homem.

Uso:
    python -m acervo.banco_vozes --sondar
    python -m acervo.banco_vozes --gerar
    python -m acervo.banco_vozes --gerar --personagem lobo
"""
import argparse
import os
import sys
import warnings

import numpy as np
import soundfile as sf

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acervo import base, personagens          # noqa: E402
import motor_v2 as motor                      # noqa: E402

KOKORO_DIR = os.path.join(os.path.dirname(os.path.dirname(base.DIR)),
                          "laboratorios", "voices_kokoro")
MODELO = os.path.join(KOKORO_DIR, "kokoro-v1.0.onnx")
VOICES = os.path.join(KOKORO_DIR, "voices-v1.0.bin")

# Frase de referência: vira o `ref_text` de todas as vozes, gravado no .txt ao
# lado do .wav (o ASR do OmniVoice está desligado no projeto).
FRASE = ("Era uma vez, num lugar bem distante daqui, uma história que "
         "começava assim, com calma e bastante clareza.")

VOZEADO_MINIMO = 0.55

# ── Receitas ────────────────────────────────────────────────────────────────
# (blend, formante). O blend define timbre e altura; o formante ajusta o TAMANHO
# do corpo depois, sem mexer no pitch — é o eixo que o Kokoro não oferece.
#
# Medidos na sondagem: pm_alex 135 Hz/var 2.3 · pm_santa 129/4.8 (mas só 41%
# vozeado, evitar puro) · pf_dora 177/2.5 · +am_onyx puxa para ~110 e escurece
# o corpo · +af_nova sobe para ~146 · +am_puck deixa mais solto.
def _r(blend, formante=1.0):
    return dict(blend=blend, formante=formante)


RECEITAS = {
    # ── vilões: graves, planos, corpo grande ─────────────────────────────
    "lobo":      _r([("pm_alex", .60), ("am_onyx", .40)], 0.88),
    "diabo":     _r([("pm_alex", .58), ("bm_george", .42)], 0.84),
    "gigante":   _r([("pm_alex", .55), ("am_onyx", .45)], 0.74),
    "bruxa":     _r([("pf_dora", .58), ("bf_alice", .42)], 0.86),
    # ── autoridade: graves e planos, corpo médio ─────────────────────────
    "rei":       _r([("pm_alex", .70), ("am_eric", .30)], 0.90),
    "rainha":    _r([("pf_dora", .65), ("bf_isabella", .35)], 0.94),
    # ── família ──────────────────────────────────────────────────────────
    "pai":       _r([("pm_alex", .62), ("am_michael", .38)], 0.97),
    "mae":       _r([("pf_dora", .64), ("af_sarah", .36)], 1.00),
    # madrasta: mesma altura da mãe, timbre mais fechado e frio
    "madrasta":  _r([("pf_dora", .74), ("bf_alice", .26)], 0.92),
    "madrinha":  _r([("pf_dora", .60), ("af_sarah", .40)], 1.02),
    "principe":  _r([("pm_alex", .62), ("bm_daniel", .38)], 1.02),
    "princesa":  _r([("pf_dora", .55), ("af_bella", .45)], 1.06),
    "filho":     _r([("pm_alex", .58), ("af_nova", .42)], 1.08),
    "irmao":     _r([("pm_alex", .60), ("am_liam", .40)], 1.03),
    "menina":    _r([("pf_dora", .55), ("af_bella", .45)], 1.16),
    "lila":      _r([("pf_dora", .55), ("af_jessica", .45)], 1.14),
    # ── povo ─────────────────────────────────────────────────────────────
    "velhinha":  _r([("pf_dora", .62), ("af_sarah", .38)], 0.94),
    "senhor":    _r([("pm_alex", .68), ("am_eric", .32)], 0.94),
    "senhora":   _r([("pf_dora", .64), ("af_sarah", .36)], 0.98),
    "pastor":    _r([("pm_alex", .62), ("am_adam", .38)], 0.90),
    "moleiro":   _r([("pm_alex", .62), ("am_eric", .38)], 0.93),
    "cacador":   _r([("pm_alex", .60), ("am_fenrir", .40)], 0.90),
    "homem":     _r([("pm_alex", .68), ("am_eric", .32)], 0.98),
    "joao":      _r([("pm_alex", .70), ("am_liam", .30)], 1.00),
    "pedro":     _r([("pm_alex", .58), ("am_puck", .42)], 1.08),
    "lucas":     _r([("pm_alex", .62), ("bm_daniel", .38)], 0.96),
    # o alfaiate é pequeno, rápido e vaidoso: corpo miúdo
    "alfaiate":  _r([("pm_alex", .58), ("am_puck", .42)], 1.14),
    "anao":      _r([("pm_alex", .58), ("am_puck", .42)], 1.20),
    "criada":    _r([("pf_dora", .60), ("af_jessica", .40)], 1.04),
    "esposa":    _r([("pf_dora", .62), ("af_nicole", .38)], 1.02),
    "sofia":     _r([("pf_dora", .58), ("af_bella", .42)], 1.08),
    # ── bichos: o corpo faz o trabalho ───────────────────────────────────
    "sapo":      _r([("pm_alex", .58), ("am_onyx", .42)], 0.80),
    "burro":     _r([("pm_alex", .62), ("am_adam", .38)], 0.86),
    "urso":      _r([("pm_alex", .58), ("am_onyx", .42)], 0.78),
    "cavalo":    _r([("pm_alex", .62), ("am_michael", .38)], 0.88),
    "cachorro":  _r([("pm_alex", .60), ("am_puck", .40)], 0.96),
    "gato":      _r([("pf_dora", .58), ("af_nicole", .42)], 1.08),
    "raposa":    _r([("pf_dora", .60), ("af_kore", .40)], 1.04),
    "galinha":   _r([("pf_dora", .56), ("af_jessica", .44)], 1.12),
    # rato, galo e pássaro: agudo vem do formante, não do blend
    "rato":      _r([("pf_dora", .55), ("af_jessica", .45)], 1.26),
    "galo":      _r([("pm_alex", .55), ("am_puck", .45)], 1.24),
    "passaro":   _r([("pf_dora", .55), ("af_bella", .45)], 1.28),
    "coelhinho": _r([("pm_alex", .56), ("am_puck", .44)], 1.16),
    "fada":      _r([("pf_dora", .58), ("af_bella", .42)], 1.14),
}

_k = None


def kokoro():
    global _k
    if _k is None:
        from kokoro_onnx import Kokoro
        if not (os.path.exists(MODELO) and os.path.exists(VOICES)):
            raise SystemExit(f"Kokoro não encontrado em {KOKORO_DIR}")
        _k = Kokoro(MODELO, VOICES)
    return _k


def estilo(blend):
    """Soma ponderada dos vetores de estilo — é isto que torna o espaço
    contínuo em vez de um catálogo de 54 vozes fixas."""
    k = kokoro()
    vetor = None
    for nome, peso in blend:
        s = peso * np.asarray(k.get_voice_style(nome))
        vetor = s if vetor is None else vetor + s
    return vetor.astype(np.float32)


def medir(audio, sr):
    import librosa
    a = np.asarray(audio, dtype=float)
    f, vf, _ = librosa.pyin(a, fmin=60, fmax=450, sr=sr, frame_length=2048)
    v = f[~np.isnan(f)]
    f0 = float(np.median(v)) if len(v) else 0.0
    var = (float(np.std(12 * np.log2(np.clip(v, 1, None) / max(f0, 1))))
           if len(v) > 8 else 0.0)
    cen = float(np.mean(librosa.feature.spectral_centroid(y=a.astype(np.float32),
                                                          sr=sr)))
    return f0, var, cen, float(np.mean(vf))


def gerar_para(nome, verbose=True):
    rec = RECEITAS.get(nome)
    if not rec:
        return None
    k = kokoro()
    audio, sr = k.create(FRASE, estilo(rec["blend"]), lang="pt-br")
    audio = np.asarray(audio, dtype=np.float32)
    f0, var, cen, voc = medir(audio, sr)
    if voc < VOZEADO_MINIMO:
        if verbose:
            print(f"  {nome:<11} só {100*voc:.0f}% vozeado — receita ruim")
        return "ruim"
    # o corpo entra depois, sem tocar no pitch
    if abs(rec["formante"] - 1.0) > 1e-3:
        audio = motor._formantes(audio, rec["formante"])
    f0b, varb, cenb, _ = medir(audio, sr)

    pasta = os.path.join(base.VOZES_PERS, nome)
    os.makedirs(pasta, exist_ok=True)
    destino = os.path.join(pasta, f"{nome}.wav")
    sf.write(destino, audio, sr)
    with open(destino[:-4] + ".txt", "w", encoding="utf-8") as f:
        f.write(FRASE)

    mapa = personagens.carregar_mapa()
    reg = mapa.setdefault(nome, {})
    reg["voz"] = os.path.basename(destino)
    reg["voz_arquivo"] = destino
    reg["origem"] = "kokoro_blend"
    reg["receita"] = " + ".join(f"{p:.0%} {n}" for n, p in rec["blend"])
    reg["formante"] = rec["formante"]
    personagens.gravar_mapa(mapa)
    if verbose:
        print(f"  {nome:<11} F0={f0b:6.1f} var={varb:4.2f} corpo={cenb:5.0f} "
              f"voz={100*voc:3.0f}%  [{reg['receita']}]")
    return "ok"


def gerar(um=None, verbose=True):
    alvos = [um] if um else sorted(RECEITAS)
    contagem = {}
    for nome in alvos:
        r = gerar_para(nome, verbose)
        if r:
            contagem[r] = contagem.get(r, 0) + 1
    if verbose:
        print(f"\n{contagem}")
    return contagem


def main():
    ap = argparse.ArgumentParser(description="Fabrica vozes por blend do Kokoro")
    ap.add_argument("--gerar", action="store_true")
    ap.add_argument("--personagem")
    a = ap.parse_args()
    base.console_utf8()
    if a.gerar or a.personagem:
        gerar(a.personagem)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
