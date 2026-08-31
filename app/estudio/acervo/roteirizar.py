# -*- coding: utf-8 -*-
"""Fase 1 em lote — detecta as falas e classifica por personagem.

Passo automático da esteira, logo depois da adaptação. Roda
`motor_v2.roteirizar_historia()` sobre cada história adaptada e grava o roteiro
em `roteiros/<id>.json`, junto com o elenco detectado.

Por que em LOTE e não uma a uma: a GPU tem 6 GB e não comporta Gemma e
OmniVoice juntas. Fazendo o lote inteiro aqui, a Gemma é carregada UMA vez para
as N histórias, e depois a síntese carrega o OmniVoice UMA vez. São duas trocas
de modelo no lote todo, em vez de duas por história.

O JSON gravado é exatamente o formato que a aba Contador do estúdio web recebe
em `POST /api/story/render` — então dá para revisar e corrigir o roteiro na
interface antes de sintetizar, sem a Gemma rodar de novo.

Uso:
    python -m acervo.roteirizar
    python -m acervo.roteirizar --id a-bela-adormecida
    python -m acervo.roteirizar --forcar
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acervo import base, validar          # noqa: E402
import motor_v2 as motor                  # noqa: E402


def roteirizar_um(_id, reg, forcar=False, verbose=True):
    caminho_ad = base.caminho(base.ADAPTADOS, _id, "txt")
    if not os.path.exists(caminho_ad):
        return None
    destino = base.caminho(base.ROTEIROS, _id, "json")
    if os.path.exists(destino) and not forcar:
        # Já tem roteiro: só acerta o status, que uma revalidação do texto pode
        # ter puxado de volta para "aprovado".
        reg["status"] = "roteirizado"
        return "pulado"

    txt = open(caminho_ad, encoding="utf-8").read()

    # Validar ANTES de gastar a Gemma: um texto com fala órfã ou rótulo ruim
    # produz roteiro errado, e o erro só apareceria depois, no áudio.
    erros, avisos, _ = validar.validar_texto(txt, reg.get("adaptado_para", 6))
    if erros:
        if verbose:
            print(f"  {_id}: {len(erros)} erro(s) de formato — pulando")
            for e in erros[:3]:
                print(f"      ✗ {e}")
        reg["status"] = "adaptado"
        reg["erros_formato"] = erros
        return "invalido"

    roteiro = motor.roteirizar_historia(txt)
    elenco = motor.elenco_do_roteiro(roteiro)

    # Segunda barreira: o elenco REAL, que só existe depois da fase 1. A
    # validação de texto só enxerga o que as tags provam, então elenco grande
    # demais e moldura de narrador escapavam até aqui.
    erros_rot = validar.validar_roteiro(roteiro, elenco)
    if erros_rot:
        if verbose:
            print(f"  {_id}: roteiro reprovado")
            for e in erros_rot:
                print(f"      ✗ {e}")
        reg["status"] = "adaptado"
        reg["erros_formato"] = erros_rot
        # Apaga o roteiro antigo: `personagens.py` levanta o elenco lendo
        # roteiros/*.json, e um arquivo órfão de história reprovada contamina o
        # elenco global com personagens que não vão virar áudio.
        if os.path.exists(destino):
            os.remove(destino)
        return "invalido"

    base.garantir_pastas()
    with open(destino, "w", encoding="utf-8") as f:
        json.dump({"id": _id, "titulo": reg.get("titulo"),
                   "elenco": elenco, "roteiro": roteiro},
                  f, ensure_ascii=False, indent=1)
    reg["elenco"] = elenco
    reg["n_beats"] = len(roteiro)
    reg["n_falas"] = sum(1 for b in roteiro if b["fala"])
    reg["status"] = "roteirizado"
    reg.pop("erros_formato", None)
    if verbose:
        print(f"  {_id}: {len(roteiro)} beats · {reg['n_falas']} falas · "
              f"elenco {elenco}")
    return "ok"


def roteirizar_acervo(um=None, forcar=False, verbose=True):
    idx = base.carregar_indice()
    motor.descarregar_omni()      # a Gemma precisa da VRAM inteira

    alvos = [(um, idx[um])] if um and um in idx else [
        (i, r) for i, r in sorted(idx.items())
        if r.get("status") in ("adaptado", "aprovado")
        or (r.get("status") == "roteirizado" and forcar)]

    if verbose:
        print(f"{len(alvos)} história(s) para roteirizar.\n")
    contagem = {}
    for _id, reg in alvos:
        r = roteirizar_um(_id, reg, forcar, verbose)
        if r:
            contagem[r] = contagem.get(r, 0) + 1
        base.gravar_indice(idx)

    base.gravar_indice(idx)
    motor.descarregar_gemma()
    if verbose:
        print(f"\n{contagem}")
    return contagem


def main():
    ap = argparse.ArgumentParser(description="Fase 1 em lote: falas por personagem")
    ap.add_argument("--id", help="roteiriza só esta história")
    ap.add_argument("--forcar", action="store_true", help="refaz o que já tem roteiro")
    a = ap.parse_args()
    base.console_utf8()
    roteirizar_acervo(a.id, a.forcar)


if __name__ == "__main__":
    main()
