# -*- coding: utf-8 -*-
"""Adaptação para uma faixa etária — com barreira de conteúdo e laço de correção.

Por que este passo existe: a idade medida em `metricas.py` é propriedade da
TRADUÇÃO, não do conto. "Os músicos de Bremen" mede 8 anos porque este texto de
1800 tem 10 minutos — mas a história (cumulativa, com bichos, sem ninguém
morrendo) é ideal para 5. Adaptar é o que move o conto de 8 para 5.

Três passos, nesta ordem:

1. `avaliar_conteudo()` — BARREIRA. A Gemma lê e devolve os temas pesados e uma
   idade de conteúdo. As métricas de forma são cegas para isso: "A senhora
   Trude" mede 3 anos (é curta e fácil de ler) e é um conto em que uma criança
   é transformada em lenha e queimada.
2. `adaptar()` — reescreve no comprimento e vocabulário do alvo.
3. `adaptar_com_validacao()` — LAÇO. Valida a saída contra as regras do
   FORMATO.md e, havendo erro, reescreve informando ao modelo exatamente o que
   errou. É isto que torna a adaptação automática confiável: pedir "não deixe
   fala sem atribuição" em abstrato não funciona; apontar "o beat 19 está sem
   tag" funciona.

O que a Gemma não conseguir em N tentativas fica marcado para adaptação à mão
(ver `fila.py`). Adaptação manual tem `fonte_adaptacao == "manual"` e nunca é
sobrescrita por um lote automático.

Uso:
    python -m acervo.adaptar --idade 6              # o acervo inteiro
    python -m acervo.adaptar --idade 6 --limite 5
    python -m acervo.adaptar --so-avaliar           # só a barreira de conteúdo
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acervo import base, metricas, validar    # noqa: E402
import motor_v2 as motor                      # noqa: E402

# Quanto tempo a história adaptada deve durar, por idade alvo. Atenção curta é
# a restrição real nessa faixa — não vocabulário.
MINUTOS_ALVO = {3: 3, 4: 3, 5: 4, 6: 5, 7: 6, 8: 7, 9: 8, 10: 10}

# Distância entre a idade do CONTEÚDO e a idade alvo a partir da qual não
# adianta adaptar: a história teria que virar outra história.
#
# Este é o critério que funciona na prática. A primeira versão bloqueava por
# PALAVRA-CHAVE ("mutilação", "tortura") e não pegou nada: a Gemma devolve
# temas abstratos ("maldição", "ganância", "desespero"), não descrições
# concretas — "A donzela sem mãos", cujo enredo é a amputação das mãos de uma
# menina, voltou como "maldição, morte, violência (potencial)". Já o NÚMERO
# separou muito bem: 14 anos para essa e 6 para "A noiva do coelhinho".
MARGEM_BLOQUEIO = 6

# Temas que, mesmo sem estourar a MARGEM_BLOQUEIO, merecem olho humano antes de
# virar áudio para uma criança. "A senhora Trude" passou com idade_conteudo=8
# (alvo 6, margem 12) trazendo os temas "crueldade, morte, violência" — é o
# conto em que uma criança é transformada em lenha e queimada. Sinalizar, e não
# bloquear, é de propósito: o que serve para uma criança de 6 anos é decisão de
# quem cria a criança, não de um limiar meu. Quem revisa vê a marca em
# `revisar_conteudo` no acervo.jsonl e em `fila.py --revisar`.
TEMAS_DUROS = {"morte", "crueldade", "violência", "violencia", "assassinato",
               "abandono", "castigo", "vingança", "vinganca", "maldição",
               "maldicao", "fome", "medo extremo", "sangue"}

# Segunda trava, para quando o modelo é explícito. Custa nada.
TEMAS_BLOQUEIO = {"tortura", "abuso", "incesto", "suicidio", "suicídio",
                  "mutilacao", "mutilação", "canibalismo", "infanticidio",
                  "infanticídio", "estupro"}

# Quantas vezes reescrever antes de mandar para a fila manual.
TENTATIVAS = 3

# História de referência usada como exemplo de formato no prompt. É a versão
# escrita à mão e validada; serve de padrão concreto de qualidade, que funciona
# muito melhor num modelo de 4B do que regra abstrata.
EXEMPLAR_ID = "a-bela-adormecida"


def _linha(saida, rotulo):
    """Extrai 'ROTULO: valor' da resposta da Gemma, tolerante a variação."""
    m = re.search(rf"^\s*{rotulo}\s*:\s*(.+)$", saida, re.IGNORECASE | re.MULTILINE)
    return m.group(1).strip() if m else ""


# ── 1. Barreira de conteúdo ─────────────────────────────────────────────────
def avaliar_conteudo(texto):
    """Temas sensíveis + idade sugerida POR CONTEÚDO (não por forma).

    Manda só o começo e o fim: é onde a violência dos contos de Grimm costuma
    estar (a ameaça na abertura, o castigo no desfecho)."""
    amostra = texto[:4000]
    if len(texto) > 9000:
        amostra += "\n[...]\n" + texto[-3000:]
    p = ("Você avalia histórias infantis. Leia o conto e responda EXATAMENTE "
         "neste formato, em português do Brasil, sem comentar nada além disso:\n\n"
         "TEMAS: lista curta dos temas pesados separados por vírgula, ou 'nenhum'\n"
         "IDADE: a menor idade para quem esta HISTÓRIA (não o texto) é adequada, "
         "só o número\n"
         "RESUMO: uma frase dizendo o que acontece\n\n"
         "Considere pesado: morte, violência física, crueldade com animais, "
         "abandono de crianças, castigo cruel, canibalismo, mutilação.\n\n"
         '"""\n' + amostra + '\n"""\n\nAvaliação:')
    saida = motor._gemma(p, num_predict=180, num_ctx=8192, temperature=0)
    temas = _linha(saida, "TEMAS").lower()
    m = re.search(r"\d+", _linha(saida, "IDADE"))
    return {
        "temas": "" if temas.startswith("nenhum") else temas,
        "idade_conteudo": int(m.group()) if m else None,
        "resumo": _linha(saida, "RESUMO"),
        "bloqueado": any(t in temas for t in TEMAS_BLOQUEIO),
    }


# ── 2. Reescrita ────────────────────────────────────────────────────────────
def _condensar(texto, progresso=lambda *a: None):
    """Conto longo demais para caber num prompt vira lista de acontecimentos.

    Reescrever a partir dos acontecimentos preserva o enredo; truncar o texto
    perderia o final, que é onde os contos se resolvem."""
    blocos = [texto[i:i + 7000] for i in range(0, len(texto), 7000)]
    partes = []
    for i, b in enumerate(blocos):
        progresso(0.2 + 0.2 * i / len(blocos), f"Condensando {i+1}/{len(blocos)}")
        p = ("Liste em ordem os ACONTECIMENTOS deste trecho de história, um por "
             "linha, frases curtas, em português do Brasil. Só o que está no "
             "texto.\n\n\"\"\"\n" + b + "\n\"\"\"\n\nACONTECIMENTOS:")
        try:
            partes.append(motor._gemma(p, num_predict=400, num_ctx=8192, temperature=0))
        except Exception:
            continue
    return "\n".join(partes).strip()


def _exemplar(linhas=16):
    """Trecho da história de referência, para servir de exemplo de formato."""
    p = base.caminho(base.ADAPTADOS, EXEMPLAR_ID, "txt")
    if not os.path.exists(p):
        return ""
    texto = open(p, encoding="utf-8").read()
    return "\n".join(texto.splitlines()[:linhas]).strip()


_REGRAS = """- cerca de {palavras} palavras (aproximadamente {minutos} minutos de narração)
- frases curtas: no máximo 12 a 15 palavras cada
- vocabulário simples e concreto, português do Brasil atual
- preserve o enredo, os personagens e o final feliz ou tranquilo
- diálogo SEMPRE neste molde: travessão no começo da linha, uma fala por linha,
  e quem falou logo depois:
      — <o que o personagem diz> — disse <nome do personagem>.
  Isto é só o molde: NUNCA copie estas palavras para a história.
- toda fala que troca de falante precisa dizer quem falou
- escreva o SUBSTANTIVO antes do adjetivo em quem falou: 'disse a fada zangada',
  nunca 'disse a última fada' (senão o personagem vira "ultima")
- personagens do mesmo papel usam o mesmo substantivo ('a madrinha mais velha',
  'a madrinha do meio') para falarem com a mesma voz
- no máximo 6 personagens com fala
- repetição é de ESTRUTURA, não de palavra: repita uma lista ou uma cena
  inteira, nunca 'muito, muito, muito'
- não repita a mesma frase mais de duas vezes
- não escreva título, nem moral no fim
- responda SÓ com a história, nada antes nem depois"""


def adaptar(texto, idade=6, temas="", correcoes=None, progresso=lambda *a: None):
    """Reescreve o conto para a idade alvo. `correcoes` = erros da tentativa
    anterior, que entram no prompt como instruções concretas."""
    minutos = MINUTOS_ALVO.get(idade, 5)
    palavras = int(minutos * metricas.PALAVRAS_POR_MINUTO)

    fonte, tipo = texto, "o conto abaixo"
    if len(texto) > 11000:
        progresso(0.2, "Conto longo — condensando antes de reescrever")
        fonte, tipo = _condensar(texto, progresso), "os acontecimentos abaixo"

    cuidado = ""
    if temas:
        cuidado = ("\nA versão original tem temas pesados (" + temas + "). "
                   "Resolva esses momentos sem crueldade e sem descrição de "
                   "violência: ninguém precisa morrer nem ser castigado com "
                   "requintes. O vilão pode fugir, se arrepender ou ir embora.\n")

    exemplo = _exemplar()
    bloco_ex = ""
    if exemplo:
        bloco_ex = ("\nEXEMPLO DE FORMATO — de OUTRA história, só para você ver o "
                    "estilo e a marcação de diálogo. NÃO use nada deste conteúdo:\n"
                    "-----\n" + exemplo + "\n-----\n")

    bloco_corr = ""
    if correcoes:
        bloco_corr = ("\nA SUA VERSÃO ANTERIOR TINHA ESTES ERROS. Corrija todos:\n"
                      + "\n".join(f"  * {e}" for e in correcoes[:8]) + "\n")

    progresso(0.55, f"Reescrevendo para {idade} anos (~{minutos} min)")
    p = (f"Reescreva {tipo} como uma história para ser NARRADA em voz alta para "
         f"uma criança de {idade} anos.\n\nREGRAS:\n"
         + _REGRAS.format(palavras=palavras, minutos=minutos)
         + "\n" + cuidado + bloco_ex + bloco_corr
         + '\n"""\n' + fonte + '\n"""\n\nHISTÓRIA:')
    saida = motor._gemma(p, num_predict=int(palavras * 2.2), num_ctx=8192,
                         temperature=0.4)
    return _limpar_saida(saida)


def _limpar_saida(s):
    """Tira preâmbulo/cerca de código que o modelo às vezes acrescenta."""
    s = (s or "").strip()
    s = re.sub(r"^```[a-z]*\n?|```$", "", s, flags=re.MULTILINE).strip()
    s = re.sub(r'^\s*"""|"""\s*$', "", s).strip()
    s = re.sub(r"^(?:aqui est[áa][^\n]*|hist[óo]ria[^\n]{0,20}):\s*\n", "", s,
               flags=re.IGNORECASE)
    return s.strip()


# ── 3. Laço de correção ─────────────────────────────────────────────────────
def adaptar_com_validacao(texto, idade=6, temas="", tentativas=TENTATIVAS,
                          verbose=True):
    """Reescreve até passar no validador. Devolve (texto, erros, n_tentativas).

    Realimentar o erro concreto é o que faz diferença: "toda fala precisa de
    tag" no abstrato o modelo ignora; "o beat 19 está sem tag" ele conserta."""
    melhor, melhores_erros, correcoes = "", None, None
    for n in range(1, tentativas + 1):
        try:
            novo = adaptar(texto, idade, temas, correcoes)
        except Exception as e:
            if verbose:
                print(f"      tentativa {n}: falhou ({e})")
            continue
        if len(novo.split()) < 80:
            correcoes = [f"a resposta veio com só {len(novo.split())} palavras; "
                         f"escreva a história inteira"]
            continue
        erros, _avisos, _d = validar.validar_texto(novo, idade)
        # guarda sempre a melhor tentativa até agora
        if melhores_erros is None or len(erros) < len(melhores_erros):
            melhor, melhores_erros = novo, erros
        if not erros:
            return novo, [], n
        if verbose:
            print(f"      tentativa {n}: {len(erros)} erro(s), reescrevendo")
        correcoes = erros
    return melhor, (melhores_erros or ["nenhuma tentativa produziu texto"]), tentativas


# ── Esteira ─────────────────────────────────────────────────────────────────
def processar(idade=6, limite=0, so_avaliar=False, tentativas=TENTATIVAS,
              verbose=True):
    """Avalia e adapta o acervo para a idade alvo. Retomável e repetível."""
    base.garantir_pastas()
    idx = base.carregar_indice()
    motor.descarregar_omni()      # a Gemma precisa da VRAM inteira

    # `fonte_adaptacao == "manual"` é intocável: são as versões escritas à mão,
    # que existem justamente porque a Gemma não deu conta.
    fila = [(i, r) for i, r in sorted(idx.items())
            if r.get("status") in ("classificado", "limpo")
            and r.get("triagem") != "inviavel"
            and r.get("fonte_adaptacao") != "manual"]
    if limite:
        fila = fila[:limite]
    if verbose:
        print(f"{len(fila)} história(s) na fila para {idade} anos.\n")

    feitos = bloqueados = manuais = 0
    for n, (_id, reg) in enumerate(fila, 1):
        texto = base.ler_texto(_id)
        if not texto:
            continue
        if verbose:
            print(f"[{n}/{len(fila)}] {reg.get('titulo', _id)}")

        try:
            aval = avaliar_conteudo(texto)
        except Exception as e:
            if verbose:
                print(f"    falha na avaliação: {e}")
            continue
        reg["temas"] = aval["temas"]
        reg["idade_conteudo"] = aval["idade_conteudo"]
        reg["resumo"] = aval["resumo"]

        ic = aval["idade_conteudo"]
        # Não bloqueia, marca: conteúdo acima do alvo com tema duro pede olho
        # humano antes de virar áudio para criança.
        duros = [t for t in TEMAS_DUROS if t in (aval["temas"] or "")]
        reg["revisar_conteudo"] = bool(duros and ic and ic > idade)
        reg["temas_duros"] = duros
        longe = ic is not None and ic >= idade + MARGEM_BLOQUEIO
        if aval["bloqueado"] or longe:
            reg["status"] = "descartado"
            reg["motivo"] = (f"conteúdo para {ic} anos, alvo {idade}"
                             if longe else "conteúdo impróprio: " + aval["temas"])
            bloqueados += 1
            if verbose:
                print(f"    BLOQUEADO — {reg['motivo']}")
            base.gravar_indice(idx)
            continue
        if so_avaliar:
            base.gravar_indice(idx)
            continue

        novo, erros, n_tent = adaptar_com_validacao(
            texto, idade, aval["temas"], tentativas, verbose)
        if not novo:
            continue
        base.escrever(base.ADAPTADOS, _id, "txt", novo)
        m = metricas.analisar(novo) or {}
        reg["adaptado_para"] = idade
        reg["fonte_adaptacao"] = "gemma"
        reg["tentativas"] = n_tent
        reg["adaptado"] = {k: m.get(k) for k in
                           ("n_palavras", "minutos", "ilf", "pal_por_frase", "idade_min")}
        if erros:
            reg["status"] = "adaptado"       # fica de fora do roteirizar
            reg["erros_formato"] = erros
            manuais += 1
            if verbose:
                print(f"    PARA REVISÃO MANUAL — {len(erros)} erro(s) após "
                      f"{n_tent} tentativas")
        else:
            reg["status"] = "aprovado"
            reg.pop("erros_formato", None)
            feitos += 1
            if verbose:
                print(f"    ok em {n_tent} tentativa(s) — {m.get('n_palavras')}p/"
                      f"{m.get('minutos')}min · mede {m.get('idade_min')}a")
        base.gravar_indice(idx)

    base.gravar_indice(idx)
    motor.descarregar_gemma()
    if verbose:
        print(f"\nAprovadas: {feitos} | para revisão manual: {manuais} | "
              f"bloqueadas: {bloqueados}")
    return feitos, manuais, bloqueados


def main():
    ap = argparse.ArgumentParser(description="Adapta o acervo para uma faixa etária")
    ap.add_argument("--idade", type=int, default=6)
    ap.add_argument("--limite", type=int, default=0)
    ap.add_argument("--tentativas", type=int, default=TENTATIVAS)
    ap.add_argument("--so-avaliar", action="store_true",
                    help="só a barreira de conteúdo, sem reescrever")
    a = ap.parse_args()
    base.console_utf8()
    processar(a.idade, a.limite, a.so_avaliar, a.tentativas)


if __name__ == "__main__":
    main()
