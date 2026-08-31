# -*- coding: utf-8 -*-
"""Reparo cirúrgico das adaptações reprovadas.

Das 33 histórias na fila manual, a maioria tem UM erro localizado: três falas
sem tag de atribuição, um personagem a mais que a paleta comporta, um rótulo
com adjetivo antes do substantivo. Reescrever a história inteira por causa
disso joga fora o que já ficou bom — e a reescrita costuma trazer erros novos.

Aqui a estratégia é outra: mostrar ao modelo a história pronta e pedir APENAS
a correção apontada, com a localização exata do problema. Tarefa muito mais
fácil para um modelo de 4B do que reescrever, e preserva o texto aprovado.

A trava importante é `_preservou()`. A tentação do modelo, ao receber "corrija
isto", é devolver uma história nova — que pode até passar no validador, mas não
é mais o texto que já estava bom. Se o reparo não preservar a maior parte das
frases originais, é rejeitado mesmo que valide.

Uso:
    python -m acervo.reparar --idade 6
    python -m acervo.reparar --id a-noiva-do-coelhinho
    python -m acervo.reparar --limite 5
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acervo import base, metricas, validar    # noqa: E402
import motor_v2 as motor                      # noqa: E402

TENTATIVAS = 2

# Fração mínima das frases originais que o reparo precisa manter. Abaixo disso
# não foi reparo, foi reescrita.
PRESERVACAO_MINIMA = 0.55


def _frases(txt):
    return {f.strip() for f in re.split(r"(?<=[.!?…])\s+|\n", txt or "")
            if len(f.strip().split()) >= 4}


def _preservou(orig, novo):
    """Fração das frases originais que sobreviveram ao reparo."""
    a, b = _frases(orig), _frases(novo)
    return len(a & b) / len(a) if a else 0.0


def instrucoes(txt, erros):
    """Traduz os erros do validador em instruções LOCALIZADAS.

    O validador fala em número de beat, que não existe para quem lê a história.
    Aqui cada erro vira "nesta linha, faça isto" — com o texto real da linha,
    que é como o modelo consegue encontrar o lugar."""
    beats = motor._beats_historia(txt)
    saida = []
    for e in erros:
        m = re.match(r"beat (\d+):", e)
        i = int(m.group(1)) if m else None

        if "falas seguidas sem nenhuma tag" in e and i is not None:
            trechos = [beats[j][1] for j in range(max(0, i - 4), min(len(beats), i + 1))
                       if beats[j][0]]
            alvo = "\n".join(f'      — {t}' for t in trechos[-3:])
            saida.append(
                "Estas falas seguidas não dizem quem falou:\n" + alvo +
                "\n  Acrescente a marcação de quem falou em cada uma, assim:\n"
                "      — <a fala como está> — disse <nome do personagem>.\n"
                "  Não invente personagem novo: use quem já fala na história.")

        elif "personagens" in e and "máximo" in e:
            nomes = re.findall(r"'([^']+)'", e)
            saida.append(
                f"A história tem personagens demais com fala: {', '.join(nomes)}.\n"
                "  Escolha o MENOS importante e transforme as falas dele em "
                "narração (conte o que ele fez, sem fala direta), até sobrarem "
                "no máximo 6 personagens falando.")

        elif "produz o personagem" in e:
            ruim = re.search(r"personagem '([^']+)'", e)
            ruim = ruim.group(1) if ruim else "?"
            ctx = beats[i + 1][1] if (i is not None and i + 1 < len(beats)) else ""
            saida.append(
                f"A marcação \"{ctx}\" faz o personagem virar \"{ruim}\", que não "
                f"é nome de gente.\n  Reescreva pondo o SUBSTANTIVO antes do "
                f"adjetivo: 'disse a fada zangada', nunca 'disse a última fada'.")

        elif "se repete" in e:
            frase = re.search(r'"([^"]+)"', e)
            saida.append(
                f"A fala \"{frase.group(1) if frase else ''}\" se repete vezes "
                f"demais. Deixe no máximo três repetições e varie as outras.")

        elif "palavras" in e and "curto demais" in e:
            saida.append("A história está curta demais. Desenvolva as cenas que "
                         "já existem (sem inventar enredo novo) até chegar perto "
                         "de 650 palavras.")

        elif "moldura de narrador" in e or "nenhum personagem" in e:
            saida.append("Tire a moldura de narrador que conversa com o ouvinte "
                         "('Olá, pequenino!'). A história deve começar direto, e "
                         "as falas devem ser dos PERSONAGENS, não do narrador.")

        elif "sem nenhuma fala" in e:
            saida.append("A história não tem diálogo nenhum. Transforme algumas "
                         "passagens em falas dos personagens.")

        else:
            saida.append(e)
    return saida


def reparar(txt, erros, idade=6):
    """Uma passada de reparo. Devolve o texto corrigido."""
    passos = instrucoes(txt, erros)
    p = ("Abaixo está uma história infantil que está QUASE pronta. Faça APENAS "
         "as correções listadas e devolva a história inteira.\n\n"
         "MUITO IMPORTANTE: não reescreva a história. Mantenha as mesmas frases, "
         "as mesmas palavras e a mesma ordem em tudo que não for citado abaixo. "
         "Mexa só no que for necessário para as correções.\n\n"
         "CORREÇÕES:\n"
         + "\n".join(f"{i+1}. {s}" for i, s in enumerate(passos))
         + "\n\nResponda só com a história corrigida, nada antes nem depois.\n\n"
         '"""\n' + txt + '\n"""\n\nHISTÓRIA CORRIGIDA:')
    n = int(len(txt.split()) * 2.4)
    saida = motor._gemma(p, num_predict=n, num_ctx=8192, temperature=0.2)
    saida = re.sub(r"^```[a-z]*\n?|```$", "", saida.strip(), flags=re.MULTILINE)
    return re.sub(r'^\s*"""|"""\s*$', "", saida).strip()


def reparar_um(_id, reg, tentativas=TENTATIVAS, verbose=True):
    p = base.caminho(base.ADAPTADOS, _id, "txt")
    if not os.path.exists(p):
        return None
    original = open(p, encoding="utf-8").read()
    erros = reg.get("erros_formato")
    if not erros:
        erros, _a, _d = validar.validar_texto(original, reg.get("adaptado_para", 6))
    if not erros:
        return "ja_ok"

    idade = reg.get("adaptado_para", 6)
    if verbose:
        print(f"  {_id}: {len(erros)} erro(s)")

    atual = original
    for n in range(1, tentativas + 1):
        try:
            novo = reparar(atual, erros, idade)
        except Exception as e:
            if verbose:
                print(f"      tentativa {n}: falhou ({e})")
            break
        if len(novo.split()) < 80:
            break
        preserv = _preservou(original, novo)
        novos_erros, _a, _d = validar.validar_texto(novo, idade)
        if preserv < PRESERVACAO_MINIMA:
            # Reescreveu em vez de reparar: recusa mesmo se validou.
            if verbose:
                print(f"      tentativa {n}: reescreveu demais "
                      f"({preserv:.0%} do texto original preservado) — recusado")
            atual, erros = original, erros
            continue
        if not novos_erros:
            base.escrever(base.ADAPTADOS, _id, "txt", novo)
            m = metricas.analisar(novo) or {}
            reg["status"] = "aprovado"
            reg.pop("erros_formato", None)
            reg["reparado"] = True
            reg["preservacao"] = round(preserv, 2)
            reg["adaptado"] = {k: m.get(k) for k in
                               ("n_palavras", "minutos", "ilf", "pal_por_frase",
                                "idade_min")}
            if verbose:
                print(f"      REPARADO em {n} — {preserv:.0%} do texto preservado")
            return "reparado"
        if verbose:
            print(f"      tentativa {n}: ainda {len(novos_erros)} erro(s) "
                  f"({preserv:.0%} preservado)")
        atual, erros = novo, novos_erros
    return "falhou"


def reparar_acervo(um=None, limite=0, tentativas=TENTATIVAS, verbose=True):
    idx = base.carregar_indice()
    motor.descarregar_omni()

    if um:
        alvos = [(um, idx[um])] if um in idx else []
    else:
        alvos = [(i, r) for i, r in sorted(idx.items())
                 if r.get("status") == "adaptado"
                 and r.get("fonte_adaptacao") != "manual"
                 and os.path.exists(base.caminho(base.ADAPTADOS, i, "txt"))]
    if limite:
        alvos = alvos[:limite]
    if verbose:
        print(f"{len(alvos)} história(s) para reparar.\n")

    contagem = {}
    for _id, reg in alvos:
        r = reparar_um(_id, reg, tentativas, verbose)
        if r:
            contagem[r] = contagem.get(r, 0) + 1
        base.gravar_indice(idx)

    base.gravar_indice(idx)
    motor.descarregar_gemma()
    if verbose:
        print(f"\n{contagem}")
    return contagem


def main():
    ap = argparse.ArgumentParser(description="Reparo cirúrgico das reprovadas")
    ap.add_argument("--id")
    ap.add_argument("--limite", type=int, default=0)
    ap.add_argument("--tentativas", type=int, default=TENTATIVAS)
    ap.add_argument("--idade", type=int, default=6)
    a = ap.parse_args()
    base.console_utf8()
    reparar_acervo(a.id, a.limite, a.tentativas)


if __name__ == "__main__":
    main()
