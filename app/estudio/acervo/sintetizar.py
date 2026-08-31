# -*- coding: utf-8 -*-
"""Último passo da esteira: roteiro → áudio.

Percorre os roteiros aprovados e sintetiza cada um com o OmniVoice, usando o
mapa global de vozes por personagem (`personagens.py`). Quem não tem voz
definida cai na PALETA — as variações automáticas sobre a voz do narrador.

Por que em LOTE: a GPU de 6 GB não comporta Gemma e OmniVoice juntos. Como a
fase 1 (Gemma) já rodou inteira em `roteirizar.py`, aqui o OmniVoice é
carregado UMA vez e serve todas as histórias — duas trocas de modelo no lote
todo, em vez de duas por história.

Uso:
    python -m acervo.sintetizar --id os-musicos-de-bremen
    python -m acervo.sintetizar                 # tudo que está roteirizado
    python -m acervo.sintetizar --voz "Pandora.wav" --ritmo 0.90
"""
import argparse
import json
import os
import sys
import time

import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acervo import base, personagens          # noqa: E402
import motor_v2 as motor                      # noqa: E402

VOZ_NARRADOR = "Pandora.wav"
RITMO = 0.90          # mesmo padrão do slider da aba Contador


def _perfis_dos_personagens(_id, verbose=True):
    """{personagem: perfil} a partir do mapa global de vozes.

    Só entram os personagens com voz definida; o resto o motor resolve com a
    PALETA, então não é preciso mapear todo mundo."""
    caminhos = personagens.vozes_da_historia(_id)
    mapa = personagens.carregar_mapa()
    perfis = {}
    for nome, caminho in caminhos.items():
        try:
            # `speed` é o terceiro eixo da assinatura (ver gerar_vozes): o
            # tempo de fala do personagem. Entra como `base_speed` do perfil,
            # que é por onde `sintetizar_roteiro` calcula a velocidade de cada
            # fala — burro arrastado, rato apressado.
            reg = mapa.get(nome) or {}
            perfil = motor.perfil_voz(caminho, base_speed=reg.get("speed"))
            # tratamento de vilão: vai no perfil e `sintetizar_roteiro` aplica
            # depois de gerar cada fala desse personagem
            if reg.get("maligno"):
                perfil["maligno"] = float(reg["maligno"])
            perfis[nome] = perfil
        except Exception as e:
            if verbose:
                print(f"      voz de '{nome}' falhou ({e}) — usando a paleta")
    return perfis


def sintetizar_um(_id, reg, perfil_narrador, ritmo=RITMO, forcar=False,
                  verbose=True):
    destino = base.caminho(base.AUDIOS, _id, "wav")
    if os.path.exists(destino) and not forcar:
        return "pulado"
    origem = base.caminho(base.ROTEIROS, _id, "json")
    if not os.path.exists(origem):
        return None

    d = json.load(open(origem, encoding="utf-8"))
    roteiro = d.get("roteiro") or []
    if not roteiro:
        return None

    vmap = _perfis_dos_personagens(_id, verbose)
    if verbose:
        mapeados = sorted(vmap) or ["(nenhum — todos na paleta)"]
        print(f"  {_id}: {len(roteiro)} beats · elenco {d.get('elenco')}")
        print(f"      vozes próprias: {', '.join(mapeados)}")

    t0 = time.time()
    audio, _saida = motor.sintetizar_roteiro(
        perfil_narrador, roteiro, ritmo=ritmo,
        progresso=(lambda f, m="": None) if not verbose else
        (lambda f, m="": print(f"      [{int(f*100):3d}%] {m}", end="\r")),
        vozes_map=vmap or None)

    base.garantir_pastas()
    sf.write(destino, audio, motor.SR)
    dur = len(audio) / motor.SR
    reg["audio"] = os.path.basename(destino)
    reg["duracao_seg"] = round(dur, 1)
    reg["status"] = "sintetizado"
    if verbose:
        print(f"      pronto: {dur/60:.1f} min de áudio em "
              f"{(time.time()-t0)/60:.1f} min  ->  {destino}")
    return "ok"


def sintetizar_acervo(um=None, voz=VOZ_NARRADOR, ritmo=RITMO, limite=0,
                      forcar=False, verbose=True):
    idx = base.carregar_indice()
    motor.descarregar_gemma()      # o OmniVoice precisa da VRAM inteira

    caminho_voz = os.path.join(personagens.VOZES_ESTUDIO, voz)
    if not os.path.exists(caminho_voz):
        print(f"Voz do narrador não encontrada: {caminho_voz}")
        return {}
    if verbose:
        print(f"Narrador: {voz}")
    perfil = motor.perfil_voz(caminho_voz)

    if um:
        alvos = [(um, idx[um])] if um in idx else []
    else:
        alvos = [(i, r) for i, r in sorted(idx.items())
                 if r.get("status") in ("roteirizado", "sintetizado")]
    if limite:
        alvos = alvos[:limite]
    if verbose:
        print(f"{len(alvos)} história(s) para sintetizar.\n")

    contagem = {}
    for _id, reg in alvos:
        try:
            r = sintetizar_um(_id, reg, perfil, ritmo, forcar, verbose)
        except Exception as e:
            r = "erro"
            if verbose:
                print(f"  {_id}: FALHOU — {e}")
        if r:
            contagem[r] = contagem.get(r, 0) + 1
        base.gravar_indice(idx)

    base.gravar_indice(idx)
    if verbose:
        print(f"\n{contagem}")
    return contagem


def main():
    ap = argparse.ArgumentParser(description="Roteiro → áudio")
    ap.add_argument("--id")
    ap.add_argument("--voz", default=VOZ_NARRADOR, help="voz do narrador")
    ap.add_argument("--ritmo", type=float, default=RITMO)
    ap.add_argument("--limite", type=int, default=0)
    ap.add_argument("--forcar", action="store_true", help="regera o que já existe")
    a = ap.parse_args()
    base.console_utf8()
    sintetizar_acervo(a.id, a.voz, a.ritmo, a.limite, a.forcar)


if __name__ == "__main__":
    main()
