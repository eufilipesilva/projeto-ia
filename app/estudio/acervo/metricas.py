# -*- coding: utf-8 -*-
"""Faixa etária MEDIDA a partir do texto — não adivinhada por um modelo.

A ideia é que a etiqueta de idade seja **auditável**: se você discordar da idade
de um conto, olha os números que a produziram e ajusta o limiar, em vez de
torcer para o modelo mudar de opinião. Por isso todos os componentes ficam
gravados no `acervo.jsonl`, não só o resultado.

Três medidas independentes, cada uma sugerindo uma idade mínima; vence a mais
restritiva (um conto curto com frases complicadas continua difícil):

1. **Duração narrada** — o preditor mais forte nessa faixa. Não adianta o texto
   ser simples se são 30 minutos: nenhuma criança de 5 anos acompanha.
2. **ILF** (Índice de Facilidade de Leitura, Flesch adaptado ao português por
   Martins et al., 1996):

       ILF = 248.835 − 1.015 × (palavras/frase) − 84.6 × (sílabas/palavra)

3. **Palavras por frase** — entra separado de propósito. O ILF mistura frase
   longa com palavra longa e as duas podem se cancelar; em narração para
   criança pequena, frase longa sozinha já é um problema.

Nada aqui usa GPU nem rede: roda em segundos sobre o acervo inteiro, então dá
para recalibrar os limiares à vontade.

Uso:
    python -m acervo.metricas                 # classifica o acervo e grava
    python -m acervo.metricas --tabela        # só mostra, sem gravar
    python -m acervo.metricas --idade 6       # lista o que serve até 6 anos
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acervo import base  # noqa: E402

# Velocidade de narração da Pandora, em palavras por minuto. Serve para
# converter tamanho em tempo — calibrar aqui se o ritmo padrão do Contador
# mudar (hoje o slider abre em 0.90).
PALAVRAS_POR_MINUTO = 130

_DIC = None


def _dic():
    """Dicionário de separação silábica.

    `left=1, right=1` é obrigatório: com os padrões do pyphen (2 e 2), palavras
    de duas sílabas curtas não são separadas — "era" e "uma" contam como 1
    sílaba em vez de 2. Conto de fadas é cheio delas, e o ILF divide sílabas por
    palavras, então o índice inteiro sairia enviesado para "mais fácil".
    (`parodia.contar_silabas` usa os padrões; lá o alvo é métrica de verso, não
    legibilidade, então ficam separados de propósito.)"""
    global _DIC
    if _DIC is None:
        import pyphen
        _DIC = pyphen.Pyphen(lang="pt_BR", left=1, right=1)
    return _DIC


_PALAVRA = re.compile(r"[a-zA-ZÀ-ÿ]+")
_FIM_FRASE = re.compile(r"[.!?…]+")


def contar_silabas(texto):
    d = _dic()
    return sum(d.inserted(p).count("-") + 1
               for p in _PALAVRA.findall(texto.lower()))


def medir(texto):
    """Medidas cruas do texto. Sem julgamento de idade — só os números."""
    palavras = _PALAVRA.findall(texto or "")
    n_pal = len(palavras)
    if not n_pal:
        return None
    # Frases: pontuação final. Diálogo sem ponto no fim (comum em travessão)
    # ainda conta como pelo menos uma frase, senão a média estoura.
    n_frases = max(1, len(_FIM_FRASE.findall(texto)))
    n_sil = contar_silabas(texto)
    pal_frase = n_pal / n_frases
    sil_pal = n_sil / n_pal
    ilf = 248.835 - 1.015 * pal_frase - 84.6 * sil_pal
    return {
        "n_palavras":   n_pal,
        "n_frases":     n_frases,
        "n_silabas":    n_sil,
        "pal_por_frase": round(pal_frase, 2),
        "sil_por_pal":  round(sil_pal, 3),
        "ilf":          round(ilf, 1),
        "minutos":      round(n_pal / PALAVRAS_POR_MINUTO, 1),
    }


# ── Limiares (calibrados sobre os 73 contos do acervo, ago/2026) ────────────
# A distribuição medida do corpus mostrou algo decisivo: sílabas/palavra é
# praticamente CONSTANTE (1,9 em metade do acervo) e palavras/frase quase não
# varia (p25=20,5 · p75=25,6). Isso não é propriedade dos contos — é a
# assinatura do tradutor, a mesma nas 73 histórias.
#
# Como o ILF é calculado a partir dessas duas medidas, ele herda a mesma
# uniformidade: metade do acervo cabe numa faixa de 8 pontos. Ou seja, ILF e
# comprimento de frase NÃO discriminam nada aqui — e, quando entravam num
# max() junto com a duração, o valor quase fixo de ~22 palavras/frase sozinho
# empurrava toda história para 10+ anos, achatando a classificação inteira.
#
# O que varia de verdade é a DURAÇÃO: de 1,0 a 69,6 minutos, uma amplitude de
# 70×. Ela passa a ser o eixo principal; o ILF vira um ajuste de no máximo um
# ano, e só nos extremos do próprio corpus (fora do intervalo p10–p90).
_POR_DURACAO = [(4, 4), (6, 5), (8, 6), (12, 8), (18, 10), (30, 12)]

# Extremos do corpus, não limiares absolutos de Flesch: as faixas clássicas do
# índice foram derivadas de texto moderno e não se aplicam a esta tradução.
ILF_DIFICIL = 55.0    # ~p10 do acervo — prosa mais travada que a média
ILF_FACIL   = 75.0    # ~p90 do acervo — prosa notavelmente mais leve

IDADE_MIN, IDADE_MAX = 3, 13


def _faixa_crescente(valor, tabela):
    for limite, idade in tabela:
        if valor <= limite:
            return idade
    return IDADE_MAX


def estimar_idade(m):
    """Idade mínima sugerida + de onde ela veio.

    A duração manda; o ILF ajusta um ano para cima ou para baixo. Todos os
    componentes voltam separados para você ver o que decidiu — é o que torna o
    número discutível em vez de mágico.

    Atenção: isto mede o texto ORIGINAL. É triagem, não o rótulo final — o
    rótulo de verdade sai de medir o texto já ADAPTADO, que é o que vai ser
    narrado de fato."""
    por_dur = _faixa_crescente(m["minutos"], _POR_DURACAO)
    ajuste, motivo = 0, "duração"
    if m["ilf"] < ILF_DIFICIL:
        ajuste, motivo = +1, "duração + prosa travada"
    elif m["ilf"] > ILF_FACIL:
        ajuste, motivo = -1, "duração + prosa leve"
    idade = max(IDADE_MIN, min(IDADE_MAX, por_dur + ajuste))
    return {
        "idade_min":         idade,
        "idade_por_duracao": por_dur,
        "ajuste_ilf":        ajuste,
        "fator_decisivo":    motivo,
        # Triagem: vale a pena mandar para a adaptação? Um conto de 9 mil
        # palavras não vira história de 5 minutos sem deixar de ser a história.
        "triagem": ("curta"   if m["n_palavras"] <= 900 else
                    "media"   if m["n_palavras"] <= 2000 else
                    "longa"   if m["n_palavras"] <= 4000 else
                    "inviavel"),
    }


def analisar(texto):
    m = medir(texto)
    if not m:
        return None
    m.update(estimar_idade(m))
    return m


def classificar_acervo(gravar=True, verbose=True):
    idx = base.carregar_indice()
    linhas = []
    for _id, reg in sorted(idx.items()):
        if reg.get("status") == "descartado":
            continue
        txt = base.ler_texto(_id)
        if txt is None:
            continue
        m = analisar(txt)
        if not m:
            continue
        if gravar:
            reg.update(m)
            if reg.get("status") == "limpo":
                reg["status"] = "classificado"
        linhas.append((_id, reg.get("titulo", _id), m))
    if gravar:
        base.gravar_indice(idx)
    if verbose:
        _tabela(linhas)
    return linhas


def _tabela(linhas):
    print(f"{'idade':>5}  {'min':>5}  {'ILF':>6}  {'p/fr':>5}  {'sil/p':>5} "
          f" {'palavras':>8}  {'decide':<8} título")
    print("-" * 92)
    for _id, titulo, m in sorted(linhas, key=lambda x: x[2]["idade_min"]):
        print(f"{m['idade_min']:>5}  {m['minutos']:>5}  {m['ilf']:>6}  "
              f"{m['pal_por_frase']:>5}  {m['sil_por_pal']:>5}  "
              f"{m['n_palavras']:>8}  {m['fator_decisivo']:<8} {titulo[:40]}")


def main():
    ap = argparse.ArgumentParser(description="Classifica a faixa etária do acervo")
    ap.add_argument("--tabela", action="store_true", help="mostra sem gravar")
    ap.add_argument("--idade", type=int, help="lista só o que serve até essa idade")
    a = ap.parse_args()
    base.console_utf8()
    linhas = classificar_acervo(gravar=not a.tabela, verbose=not a.idade)
    if a.idade:
        cabe = [l for l in linhas if l[2]["idade_min"] <= a.idade]
        print(f"{len(cabe)} de {len(linhas)} histórias servem até {a.idade} anos:\n")
        _tabela(cabe)


if __name__ == "__main__":
    main()
