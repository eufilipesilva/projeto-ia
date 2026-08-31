# -*- coding: utf-8 -*-
"""Validador das histórias adaptadas — as regras do FORMATO.md, automatizadas.

Cada regra aqui existe porque o erro correspondente ACONTECEU ao adaptar "A bela
adormecida" à mão e só apareceu ao rodar o pipeline de verdade. Verificar isso no
olho não escala para 73 histórias; verificar por máquina custa milissegundos.

Dois modos:

  rápido    (padrão) só análise de texto — pega quase tudo, roda instantâneo
  completo  (--gemma) roda a fase 1 de verdade e confere o elenco real

Uso:
    python -m acervo.validar --id a-bela-adormecida
    python -m acervo.validar --todos
    python -m acervo.validar --id X --gemma
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acervo import base, metricas          # noqa: E402
import motor_v2 as motor                   # noqa: E402

# Alvos numéricos por idade (ver FORMATO.md). Faixa, não valor exato.
ALVOS = {
    "pal_por_frase_max": 15.0,
    "ilf_min":           70.0,
    "personagens_max":   len(motor.PALETA),   # a paleta dá a volta depois disso
}

# Palavras que NÃO servem como nome de personagem. `_norm_nome` fica com a
# primeira palavra depois do artigo, então uma tag como "disse a última fada"
# produz o personagem "ultima". O conserto é escrever o substantivo primeiro.
_ROTULOS_RUINS = {
    "primeira", "primeiro", "segunda", "segundo", "terceira", "terceiro",
    "quarta", "quarto", "quinta", "quinto", "ultima", "ultimo", "outra",
    "outro", "mesma", "mesmo", "velha", "velho", "nova", "novo", "pequena",
    "pequeno", "grande", "jovem", "pobre", "rica", "rico", "bela", "belo",
    "boa", "bom", "ma", "mau", "linda", "lindo", "triste", "alegre",
}


def _tags_de_falante(beats):
    """Nome do falante que cada beat de FALA consegue provar pela tag vizinha.

    Reproduz as duas primeiras camadas de `_classificar_beats` (as que não usam
    LLM). Beat sem nome aqui é fala que depende de herdar o falante anterior —
    exatamente onde a atribuição erra."""
    nomes = {}
    for i, (eh_fala, _) in enumerate(beats):
        if not eh_fala:
            continue
        nome = motor._falante_interno(beats[i][1])
        if not nome and i + 1 < len(beats) and not beats[i + 1][0]:
            nome = motor._falante_da_tag(beats[i + 1][1], "depois")
        if not nome and i - 1 >= 0 and not beats[i - 1][0]:
            prev = beats[i - 1][1].rstrip()
            nome = motor._falante_da_tag(
                prev, "antes" if motor._tag_vem_antes(prev) else "depois")
            if not nome:
                nome = motor._falante_da_tag(prev, "antes")
        if nome:
            nomes[i] = nome
    return nomes


def validar_texto(txt, idade=6):
    """Devolve (erros, avisos, dados). Erro = quebra o pipeline; aviso = piora
    o resultado mas não impede a síntese."""
    erros, avisos = [], []
    beats = motor._beats_historia(txt)
    if not beats:
        return ["texto não produziu nenhum beat"], [], {}

    m = metricas.analisar(txt) or {}
    tags = _tags_de_falante(beats)
    falas = [i for i, (f, _) in enumerate(beats) if f]

    # ── Regra 1: aspas e travessão na mesma linha ───────────────────────────
    for n, linha in enumerate(txt.splitlines(), 1):
        tem_aspas = any(c in linha for c in '"“”„‟«»')
        tem_trav = bool(re.match(r"\s*[-–—]", linha)) or " – " in linha or " — " in linha
        if tem_aspas and tem_trav:
            avisos.append(f"linha {n}: aspas E travessão na mesma linha — o "
                          f"segmentador usa o ramo das aspas e ignora os travessões")

    # ── Regra 2: fala sem tag de atribuição ────────────────────────────────
    # AVISO, não erro — e isso foi medido, não suposto. A primeira versão
    # tratava fala sem tag como falha certa ("vai herdar o falante errado") e
    # reprovava 22 histórias por isso. Mas a atribuição tem TRÊS camadas: sem
    # tag, entra `_quem_fala_gemma`, que lê ±8 beats de contexto — e só herda o
    # falante anterior se esse também falhar. Rodando a fase 1 de verdade em
    # seis casos sem tag, a Gemma acertou os seis (inclusive sujeito pronominal,
    # "Ela disse: —", que o regex recusa por princípio).
    #
    # Continua sendo ERRO num caso: sequência longa de falas sem tag nenhuma.
    # Aí não há âncora de nome no contexto e a cadeia de herança se propaga.
    seq = 0
    for i in falas:
        if tags.get(i):
            seq = 0
            continue
        seq += 1
        if seq == 3:
            erros.append(f"beat {i}: 3 falas seguidas sem nenhuma tag de "
                         f"atribuição — sem âncora de nome, a atribuição vira "
                         f"chute: \"{beats[i][1][:45]}\"")
    n_sem_tag = len(falas) - len(tags)
    if n_sem_tag:
        avisos.append(f"{n_sem_tag} de {len(falas)} falas sem tag de atribuição "
                      f"— resolvidas pela Gemma na fase 1; confira o elenco depois")

    # ── Regra 3: rótulo de falante ruim (ordinal/adjetivo antes do nome) ────
    for i, nome in tags.items():
        if nome in _ROTULOS_RUINS:
            erros.append(f"beat {i}: tag produz o personagem '{nome}' — "
                         f"escreva o substantivo antes do adjetivo "
                         f"(ex.: 'a fada zangada', não 'a última fada')")

    # ── Regra 4: quantidade de personagens ─────────────────────────────────
    elenco = []
    for i in falas:
        n = tags.get(i)
        if n and n not in elenco:
            elenco.append(n)
    if len(elenco) > ALVOS["personagens_max"]:
        erros.append(f"{len(elenco)} personagens com fala, máximo {ALVOS['personagens_max']} "
                     f"(a PALETA dá a volta e o {ALVOS['personagens_max']+1}º repete a voz "
                     f"do 1º): {elenco}")

    # ── Regra 5: nomes quase idênticos ─────────────────────────────────────
    # Só interessa a colisão de VERDADE (velhinho/velhinha), não prefixo comum
    # entre palavras distintas (princesa/principe são personagens canônicos e
    # não se confundem).
    for a in range(len(elenco)):
        for b in range(a + 1, len(elenco)):
            x, y = elenco[a], elenco[b]
            quase = (len(x) == len(y)
                     and sum(1 for cx, cy in zip(x, y) if cx != cy) <= 1)
            if quase or x.startswith(y) or y.startswith(x):
                avisos.append(f"'{x}' e '{y}' são quase o mesmo nome — "
                              f"confunde a atribuição e o ouvinte")

    # ── Regra 7: contaminação pelo exemplo do prompt / laço de repetição ────
    # A Gemma copia a linha de exemplo do prompt para dentro da história e às
    # vezes entra em laço nela ("Vamos embora?" apareceu 40 vezes num conto).
    # Limiar alto de propósito. Em conto CUMULATIVO o refrão repetido 3, 4 ou 5
    # vezes é a estrutura da história ("cada animal faz a mesma pergunta") — é
    # justamente o que se quer para criança pequena. A primeira versão cortava
    # em 3 e reprovava refrão legítimo. O que se quer pegar aqui é degeneração:
    # o vazamento do exemplo do prompt chegou a 40 repetições da mesma frase.
    linhas_fala = [b[1].strip() for b in beats if b[0] and len(b[1].split()) >= 3]
    for frase in set(linhas_fala):
        n = linhas_fala.count(frase)
        if n > 6:
            erros.append(f"a fala \"{frase[:40]}\" se repete {n} vezes — "
                         f"laço de repetição ou vazamento do exemplo do prompt")

    # ── Regra 6: alvos numéricos ───────────────────────────────────────────
    if m:
        if m["pal_por_frase"] > ALVOS["pal_por_frase_max"]:
            avisos.append(f"{m['pal_por_frase']} palavras por frase "
                          f"(alvo até {ALVOS['pal_por_frase_max']})")
        if m["ilf"] < ALVOS["ilf_min"]:
            avisos.append(f"ILF {m['ilf']} (alvo acima de {ALVOS['ilf_min']})")
        if m["idade_min"] > idade:
            erros.append(f"mede {m['idade_min']} anos, alvo era {idade}")
        # Comprimento mínimo: "A serpente branca" saiu com 295 palavras contra
        # ~650 pedidas — não é adaptação, é esboço, e o conto se perde.
        if m["n_palavras"] < 350:
            erros.append(f"só {m['n_palavras']} palavras — curto demais, a "
                         f"história não cabe (alvo em torno de 650)")
        if not falas:
            erros.append("história sem nenhuma fala — seria 100% narrador")

    dados = dict(m, beats=len(beats), falas=len(falas),
                 elenco_provado=elenco, falas_sem_tag=len(falas) - len(tags))
    return erros, avisos, dados


def validar_roteiro(roteiro, elenco):
    """Valida o roteiro JÁ classificado pela fase 1 — o elenco REAL.

    `validar_texto` só enxerga o elenco que as tags provam. A Gemma infere mais
    falantes que isso, então histórias com 7 personagens passavam na validação
    de texto e só apareciam aqui. Esta checagem fecha o buraco."""
    erros = []
    falas = [b for b in roteiro if b.get("fala")]

    if len(elenco) > ALVOS["personagens_max"]:
        erros.append(f"elenco real com {len(elenco)} personagens, máximo "
                     f"{ALVOS['personagens_max']}: {elenco}")

    curtos = [n for n in elenco if len(n) < 3]
    if curtos:
        erros.append(f"nome(s) de personagem sem sentido (resto de texto): {curtos}")

    # Narrador-personagem: a Gemma às vezes embrulha o conto numa moldura com
    # uma "narradora" que conversa com o ouvinte ("Olá, pequenino!"). Aí toda
    # fala vai para 'narrador', os personagens reais ficam sem voz, e o elenco
    # sai vazio mesmo havendo dezenas de falas.
    if falas and not elenco:
        erros.append(f"{len(falas)} falas, mas nenhum personagem — provavelmente "
                     f"a história foi embrulhada numa moldura de narrador")

    if not falas:
        erros.append("história sem nenhuma fala — seria 100% narrador")
    return erros


def validar_com_gemma(txt):
    """Confere o elenco REAL (fase 1 completa). Lento — só para confirmação."""
    roteiro = motor.roteirizar_historia(txt)
    return motor.elenco_do_roteiro(roteiro), roteiro


def validar_id(_id, idade=6, usar_gemma=False, verbose=True):
    p = base.caminho(base.ADAPTADOS, _id, "txt")
    if not os.path.exists(p):
        if verbose:
            print(f"{_id}: sem versão adaptada.")
        return None
    txt = open(p, encoding="utf-8").read()
    erros, avisos, d = validar_texto(txt, idade)

    if verbose:
        sinal = "ERRO" if erros else ("aviso" if avisos else "ok")
        print(f"\n[{sinal}] {_id}")
        print(f"  {d.get('n_palavras')}p · {d.get('minutos')}min · ILF {d.get('ilf')} · "
              f"{d.get('pal_por_frase')}p/frase · mede {d.get('idade_min')}a")
        print(f"  {d.get('beats')} beats · {d.get('falas')} falas · "
              f"elenco provado por tag: {d.get('elenco_provado')}")
        for e in erros:
            print(f"  ✗ {e}")
        for a in avisos:
            print(f"  ! {a}")

    if usar_gemma:
        elenco, _ = validar_com_gemma(txt)
        if verbose:
            print(f"  elenco real (Gemma): {elenco}")
            extras = [n for n in elenco if n not in d.get("elenco_provado", [])]
            if extras:
                print(f"  ! a Gemma inferiu {extras} sem tag explícita — "
                      f"confira se está certo")
        d["elenco_gemma"] = elenco
    return erros, avisos, d


def main():
    ap = argparse.ArgumentParser(description="Valida as histórias adaptadas")
    ap.add_argument("--id", help="valida uma história")
    ap.add_argument("--todos", action="store_true", help="valida todas as adaptadas")
    ap.add_argument("--idade", type=int, default=6)
    ap.add_argument("--gemma", action="store_true", help="confere o elenco real (lento)")
    a = ap.parse_args()
    base.console_utf8()

    if a.id:
        validar_id(a.id, a.idade, a.gemma)
        return
    if not a.todos:
        ap.print_help()
        return

    idx = base.carregar_indice()
    ok = com_erro = 0
    for _id in sorted(idx):
        if not os.path.exists(base.caminho(base.ADAPTADOS, _id, "txt")):
            continue
        r = validar_id(_id, a.idade, a.gemma)
        if r and r[0]:
            com_erro += 1
        elif r:
            ok += 1
    print(f"\n{ok} sem erro · {com_erro} com erro")


if __name__ == "__main__":
    main()
