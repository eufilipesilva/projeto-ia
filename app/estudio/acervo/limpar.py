# -*- coding: utf-8 -*-
"""Wikitext bruto → texto limpo, pronto para `motor_v2._beats_historia()`.

Passo separado da coleta de propósito: este limpador vai ser reajustado várias
vezes conforme aparecem casos novos, e cada ajuste precisa poder rodar sobre o
que já está em `brutos/` — sem bater na rede de novo.

O que o texto limpo PRECISA preservar (senão o Contador quebra):
  * quebras de linha entre falas — é o que separa locutores em `_beats_historia`
  * travessões de diálogo (— – -) e aspas — é como o segmentador acha as falas
  * pontuação final de frase — o `_split_frases` corta por `. ! ? …`

Uso:
    python -m acervo.limpar              # limpa tudo que está com status "novo"
    python -m acervo.limpar --todos      # relimpa o acervo inteiro
    python -m acervo.limpar --ver <id>   # mostra o resultado de um, sem gravar
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acervo import base  # noqa: E402

# ── Capitular ilustrada ──────────────────────────────────────────────────────
# As páginas abrem com a primeira letra como IMAGEM:
#     [[Ficheiro:InicialH.svg|left|100px]]<p align="justify">á muito tempo...
# Removendo a imagem ingenuamente, o conto começa em "á muito tempo" — cada
# história perderia a primeira letra. A letra está no nome do arquivo, então dá
# para devolvê-la ao texto.
_CAPITULAR = re.compile(
    r"\[\[\s*(?:Ficheiro|Arquivo|File|Image)\s*:\s*Inicial([A-Za-zÀ-ÿ])[^\]]*\]\]",
    re.IGNORECASE)

_FICHEIRO = re.compile(
    r"\[\[\s*(?:Ficheiro|Arquivo|File|Image)\s*:[^\[\]]*(?:\[\[[^\]]*\]\][^\[\]]*)*\]\]",
    re.IGNORECASE)


def _restaurar_capitular(w):
    """Troca a imagem da capitular pela letra que ela representa, colando-a na
    palavra que vem logo depois (pulando tags HTML pelo caminho)."""
    m = _CAPITULAR.search(w)
    if not m:
        return w
    letra = m.group(1).upper()
    resto = w[m.end():]
    # pula tags/espaços entre a imagem e o início real do texto
    salto = re.match(r"(?:\s|<[^>]+>)*", resto)
    pos = salto.end() if salto else 0
    return w[:m.start()] + resto[:pos] + letra + resto[pos:]


# ── Metadados do cabeçalho {{navegar}} ───────────────────────────────────────
def extrair_navegar(w):
    """Lê os campos do template {{navegar|obra=|autor=|seção=|...}} do topo."""
    m = re.search(r"\{\{\s*navegar(.*?)\n\}\}", w, re.DOTALL | re.IGNORECASE)
    if not m:
        return {}
    meta = {}
    for campo in m.group(1).split("\n|"):
        if "=" not in campo:
            continue
        k, _, v = campo.partition("=")
        k = k.strip().lstrip("|").strip().lower()
        v = re.sub(r"\[\[([^\]|]*\|)?([^\]]*)\]\]", r"\2", v).strip()
        v = re.sub(r"<[^>]+>", " ", v).strip()
        if k and v:
            meta[k] = v
    return meta


def numero_do_conto(meta):
    """A `seção` vem como '50 – A bela adormecida'. Devolve o 50."""
    m = re.match(r"\s*(\d+)", meta.get("seção", meta.get("secao", "")))
    return int(m.group(1)) if m else None


# ── Limpeza ──────────────────────────────────────────────────────────────────
def limpar_wikitext(w):
    """Wikitext → texto corrido, preservando parágrafos e diálogo."""
    if not w:
        return ""
    w = _restaurar_capitular(w)
    # cabeçalho de navegação e demais templates (podem ser aninhados)
    w = re.sub(r"\{\{\s*navegar.*?\n\}\}", "", w, flags=re.DOTALL | re.IGNORECASE)
    for _ in range(3):
        w, n = re.subn(r"\{\{[^{}]*\}\}", "", w)
        if not n:
            break
    w = _FICHEIRO.sub("", w)                       # imagens restantes
    w = re.sub(r"<ref[^>]*>.*?</ref>", "", w, flags=re.DOTALL | re.IGNORECASE)
    w = re.sub(r"<ref[^>]*/>", "", w, flags=re.IGNORECASE)
    # <p>, <br> e afins viram quebra de parágrafo; o resto das tags some
    w = re.sub(r"</?\s*(?:p|br|div|center)\b[^>]*>", "\n", w, flags=re.IGNORECASE)
    w = re.sub(r"<[^>]+>", "", w)
    # links: [[destino|rótulo]] → rótulo ; [[destino]] → destino
    w = re.sub(r"\[\[([^\]|]*)\|([^\]]*)\]\]", r"\2", w)
    w = re.sub(r"\[\[([^\]]*)\]\]", r"\1", w)
    w = re.sub(r"\[https?://\S+\s+([^\]]*)\]", r"\1", w)
    w = re.sub(r"\[https?://\S+\]", "", w)
    # marcação de ênfase e títulos de seção
    w = re.sub(r"'{2,}", "", w)
    # Títulos de seção são REMOVIDOS, não desembrulhados: nessas páginas o
    # "== ... ==" é o próprio título do conto — já está no acervo.jsonl e não
    # deve ser narrado como se fosse a primeira frase da história.
    w = re.sub(r"^\s*=+[^=\n]*=+\s*$", "", w, flags=re.MULTILINE)
    w = w.replace("&nbsp;", " ").replace("&mdash;", "—").replace("&amp;", "&")
    # espaços: sem tocar nas quebras de linha, que o segmentador usa
    w = re.sub(r"[ \t]+", " ", w)
    w = re.sub(r" *\n *", "\n", w)
    w = re.sub(r"\n{3,}", "\n\n", w)
    linhas = [ln.strip() for ln in w.split("\n")]
    return "\n".join(linhas).strip()


def remover_titulo_repetido(txt, titulo):
    """Descarta a primeira linha quando ela é só o título do conto.

    A marcação das 79 páginas não é uniforme: umas trazem o título em
    `== ... ==`, outras como linha solta sem marcação nenhuma. Comparar pelo
    slug ignora acento, caixa e pontuação, então "A MESA MÁGICA" e
    "A mesa magica," casam com o título do registro."""
    linhas = txt.split("\n")
    for i, ln in enumerate(linhas[:3]):
        if not ln.strip():
            continue
        if titulo and base.slug(ln) == base.slug(titulo):
            return "\n".join(linhas[i + 1:]).lstrip("\n")
        break   # só a primeira linha com conteúdo interessa
    return txt


def limpar_um(_id, reg, gravar=True):
    bruto = base.ler_bruto(_id)
    if bruto is None:
        return None
    meta = extrair_navegar(bruto)
    txt = limpar_wikitext(bruto)
    txt = remover_titulo_repetido(txt, reg.get("titulo", ""))
    if gravar:
        base.escrever(base.TEXTOS, _id, "txt", txt)
        reg["n_palavras"] = len(txt.split())
        reg["n_chars"] = len(txt)
        reg["hash_texto"] = base.hash_texto(txt)
        if meta.get("autor"):
            reg["autor"] = meta["autor"]
        n = numero_do_conto(meta)
        if n:
            reg["numero"] = n
        reg["status"] = "limpo"
    return txt


def marcar_duplicatas(idx):
    """Títulos diferentes que redirecionam para a mesma página produzem o mesmo
    bruto. Mantém o primeiro (menor id) e descarta os demais, para não narrar a
    mesma história duas vezes no lote."""
    vistos, dups = {}, 0
    for _id in sorted(idx):
        h = idx[_id].get("hash_bruto")
        if not h:
            continue
        if h in vistos:
            idx[_id]["status"] = "descartado"
            idx[_id]["motivo"] = f"duplicata de {vistos[h]}"
            dups += 1
        else:
            vistos[h] = _id
    return dups


def limpar_acervo(todos=False, verbose=True):
    idx = base.carregar_indice()
    dups = marcar_duplicatas(idx)
    feitos = 0
    for _id, reg in idx.items():
        if reg.get("status") == "descartado":
            continue
        if not todos and reg.get("status") != "novo":
            continue
        if limpar_um(_id, reg) is not None:
            feitos += 1
    base.gravar_indice(idx)
    if verbose:
        print(f"Limpos: {feitos} | duplicatas descartadas: {dups} | acervo: {len(idx)}")
    return feitos


def main():
    ap = argparse.ArgumentParser(description="Limpa o wikitext do acervo")
    ap.add_argument("--todos", action="store_true", help="relimpa tudo, não só os novos")
    ap.add_argument("--ver", metavar="ID", help="mostra o resultado de um id, sem gravar")
    a = ap.parse_args()
    base.console_utf8()
    if a.ver:
        idx = base.carregar_indice()
        reg = idx.get(a.ver)
        if not reg:
            print(f"id '{a.ver}' não está no acervo."); return
        print(limpar_um(a.ver, reg, gravar=False))
    else:
        limpar_acervo(a.todos)


if __name__ == "__main__":
    main()
