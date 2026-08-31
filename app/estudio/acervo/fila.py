# -*- coding: utf-8 -*-
"""Fila de trabalho da esteira — o que já andou e o que é a próxima tarefa.

A esteira tem um passo que não é um script: a ADAPTAÇÃO é escrita à mão, numa
conversa, porque a Gemma não dá conta (ver FORMATO.md). Este módulo existe para
esse passo caber no fluxo: diz qual história vem agora e imprime, num bloco só,
tudo o que é preciso para escrever a adaptação — sem precisar caçar arquivo.

    coletar ──► limpar ──► medir ──► [ADAPTAR à mão] ──► validar ──► roteirizar ──► sintetizar
     auto        auto       auto        conversa           auto        auto          auto

Uso:
    python -m acervo.fila --status
    python -m acervo.fila --proximas 10 --idade 6
    python -m acervo.fila --briefing            # a próxima, com o texto inteiro
    python -m acervo.fila --briefing --id X
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acervo import base  # noqa: E402

ORDEM = ["novo", "limpo", "classificado", "adaptado", "aprovado",
         "roteirizado", "sintetizado", "descartado"]


def candidatas(idx, idade=6):
    """Histórias esperando adaptação, na ordem em que vale a pena atacá-las.

    Critério: as que já servem para a idade alvo primeiro, e as mais curtas
    antes — adaptação curta rende resultado audível mais rápido, e conto curto
    para criança pequena é o que se quer de qualquer forma."""
    fila = []
    for _id, r in idx.items():
        if r.get("status") in ("descartado", "roteirizado", "sintetizado"):
            continue
        if r.get("triagem") == "inviavel":
            continue
        if os.path.exists(base.caminho(base.ADAPTADOS, _id, "txt")):
            continue
        fila.append((_id, r))
    fila.sort(key=lambda x: (x[1].get("idade_min", 99),
                             x[1].get("n_palavras", 10**6)))
    return fila


def status(idx):
    contagem = {s: 0 for s in ORDEM}
    for r in idx.values():
        contagem[r.get("status", "novo")] = contagem.get(r.get("status", "novo"), 0) + 1
    manuais = sum(1 for r in idx.values() if r.get("fonte_adaptacao") == "manual")
    print("ESTEIRA\n" + "-" * 46)
    for s in ORDEM:
        if contagem.get(s):
            print(f"  {s:<14} {contagem[s]:3}")
    print("-" * 46)
    print(f"  total          {len(idx):3}   (adaptadas à mão: {manuais})")


def briefing(_id, reg):
    """Tudo o que a adaptação precisa, num bloco só."""
    txt = base.ler_texto(_id)
    if txt is None:
        print(f"{_id}: sem texto limpo.")
        return
    print("=" * 70)
    print(f"ID      {_id}")
    print(f"TÍTULO  {reg.get('titulo')}")
    print(f"FONTE   {reg.get('url')}  ({reg.get('licenca')})")
    print(f"MEDIDAS {reg.get('n_palavras')}p · {reg.get('minutos')}min · "
          f"ILF {reg.get('ilf')} · {reg.get('pal_por_frase')}p/frase · "
          f"mede {reg.get('idade_min')}a · triagem {reg.get('triagem')}")
    if reg.get("temas"):
        print(f"TEMAS   {reg['temas']}  (conteúdo sugere {reg.get('idade_conteudo')}a)")
    if reg.get("resumo"):
        print(f"RESUMO  {reg['resumo']}")
    print(f"SALVAR EM  acervo/adaptados/{_id}.txt")
    print(f"VALIDAR    python -m acervo.validar --id {_id}")
    print("=" * 70)
    print(txt)
    print("=" * 70)


def main():
    ap = argparse.ArgumentParser(description="Fila de trabalho da esteira")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--proximas", type=int, metavar="N", help="lista as N próximas")
    ap.add_argument("--briefing", action="store_true", help="texto completo da próxima")
    ap.add_argument("--id", help="briefing de uma história específica")
    ap.add_argument("--idade", type=int, default=6)
    ap.add_argument("--revisar", action="store_true",
                    help="histórias marcadas para olho humano no conteúdo")
    a = ap.parse_args()
    base.console_utf8()
    idx = base.carregar_indice()

    if a.status:
        status(idx)
        return
    if a.revisar:
        marcadas = [(i, r) for i, r in sorted(idx.items())
                    if r.get("revisar_conteudo")]
        if not marcadas:
            print("Nenhuma história marcada para revisão de conteúdo.")
            return
        print(f"{len(marcadas)} história(s) pedem olho humano no conteúdo.")
        print("Passaram na barreira automática, mas trazem tema pesado para a "
              "idade alvo — o que serve para a sua criança é você quem decide.\n")
        for _id, r in marcadas:
            print(f"  {_id}")
            print(f"    conteúdo para {r.get('idade_conteudo')}a · "
                  f"duros: {', '.join(r.get('temas_duros', []))}")
            if r.get("resumo"):
                print(f"    {r['resumo'][:100]}")
        return
    if a.id:
        reg = idx.get(a.id)
        if reg:
            briefing(a.id, reg)
        else:
            print(f"'{a.id}' não está no acervo.")
        return

    fila = candidatas(idx, a.idade)
    if not fila:
        print("Nada na fila — tudo adaptado.")
        return
    if a.briefing:
        briefing(*fila[0])
        return

    n = a.proximas or 10
    print(f"{len(fila)} história(s) esperando adaptação. Próximas {min(n, len(fila))}:\n")
    print(f"{'idade':>5} {'min':>5} {'palavras':>8}  {'triagem':<9} id")
    print("-" * 74)
    for _id, r in fila[:n]:
        print(f"{r.get('idade_min', '?'):>5} {r.get('minutos', '?'):>5} "
              f"{r.get('n_palavras', '?'):>8}  {r.get('triagem', '?'):<9} {_id}")


if __name__ == "__main__":
    main()
