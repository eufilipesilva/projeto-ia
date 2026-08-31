# -*- coding: utf-8 -*-
"""Coletor de histórias do Wikisource em português.

Usa a **API** (`action=query` / `action=parse`), não raspagem de HTML. Motivos:
enumera a coleção inteira sem adivinhar paginação, devolve o texto sem menu nem
rodapé, e não quebra quando o site muda de layout.

Fonte inicial: `Contos de Grimm` — 200 contos em português, uma página por
conto, domínio público (origem Project Gutenberg).

Uso:
    python -m acervo.wikisource --listar
    python -m acervo.wikisource --coletar --limite 10
    python -m acervo.wikisource --coletar            # a coleção inteira

Só baixa o que ainda não está no acervo, então pode ser interrompido e
rechamado à vontade.
"""
import argparse
import json
import os
import sys
import time
import urllib.parse

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acervo import base  # noqa: E402

API = "https://pt.wikisource.org/w/api.php"

# A Wikimedia pede um User-Agent que identifique a aplicação. A política também
# sugere um contato, mas ela existe para bots de alto volume — aqui são dezenas
# de requisições a 1/s, então não há motivo para deixar dado pessoal no log de
# um terceiro. Se um dia isto virar coleta grande ou automática, aí sim vale
# acrescentar um contato (de preferência a URL do projeto, não um e-mail).
UA = "EstudioPandora/1.0 (uso pessoal; leitor de dominio publico; 1 req/s)"

# Pausa entre BLOCOS (não entre páginas — veja `baixar_lote`). Com 40 títulos
# por requisição, a coleção inteira sai em 2 chamadas.
PAUSA = 2.0

# Títulos por requisição. A API permite 50; 40 deixa folga para títulos longos
# não estourarem o limite de tamanho da URL.
LOTE = 40

COLECOES = {
    "grimm": {
        "prefixo": "Contos de Grimm/",
        "obra":    "Contos de Grimm",
        "autor":   "Irmãos Grimm",
        "licenca": "Domínio público",
    },
}

# Páginas de aparato editorial que convivem com os contos na mesma coleção.
# "Introdução" foi coletada, adaptada e roteirizada como se fosse conto de
# fadas — são 2678 palavras de prosa editorial sobre a obra, não uma história.
# Filtrar aqui é mais barato que descobrir isso na barreira de conteúdo.
NAO_E_CONTO = {
    "introducao", "prefacio", "prologo", "epilogo", "posfacio", "indice",
    "sumario", "notas", "nota-do-tradutor", "apendice", "bibliografia",
    "advertencia", "dedicatoria", "sobre-o-autor", "sobre-esta-edicao",
    "capa", "rosto", "creditos", "licenca",
}

_sessao = None


def _http():
    global _sessao
    if _sessao is None:
        _sessao = requests.Session()
        _sessao.headers.update({"User-Agent": UA})
    return _sessao


def _api(_tentativas=6, **params):
    """Chamada à API com recuo exponencial.

    Sem isto o coletor tomava 429 e continuava pedindo no mesmo ritmo — o
    comportamento exatamente errado: além de não funcionar, é insistir depois de
    o servidor ter pedido para parar. Respeita o cabeçalho `Retry-After` quando
    ele vem, e dobra a espera a cada tentativa quando não vem."""
    params.setdefault("format", "json")
    params.setdefault("formatversion", 2)
    espera = 3.0
    ultimo = None
    for _ in range(_tentativas):
        r = _http().get(API, params=params, timeout=60)
        ultimo = r
        if r.status_code == 429 or r.status_code >= 500:
            cab = r.headers.get("Retry-After", "")
            pausa = float(cab) if cab.isdigit() else espera
            print(f"    (servidor pediu calma: {r.status_code}, aguardando {pausa:.0f}s)")
            time.sleep(pausa)
            espera = min(espera * 2, 120)
            continue
        r.raise_for_status()
        return r.json()
    ultimo.raise_for_status()
    return {}


def listar_colecao(prefixo):
    """Todos os títulos sob um prefixo, seguindo a paginação da API até o fim.

    O `generator=allpages` é a forma confiável de enumerar: a página-índice da
    coleção é HTML feito para humanos e pode listar contos que não existem (ou
    esquecer os que existem)."""
    titulos, cont = [], {}
    while True:
        d = _api(action="query", generator="allpages", gapprefix=prefixo,
                 gapnamespace=0, gaplimit=500, **cont)
        for p in d.get("query", {}).get("pages", []):
            titulos.append(p["title"])
        if "continue" not in d:
            break
        cont = d["continue"]
        time.sleep(PAUSA)
    return sorted(titulos)


def baixar_lote(titulos):
    """Wikitext de VÁRIAS páginas numa requisição só.

    `action=query&prop=revisions` aceita até 50 títulos por chamada, enquanto
    `action=parse` só aceita um. Para 79 contos isso é a diferença entre 2 e 79
    requisições — foi buscando uma a uma que a coleta tomou 429.

    `redirects=1` é obrigatório: no acervo do Grimm as subpáginas
    (`Contos de Grimm/A bela adormecida`) redirecionam para páginas de nível
    superior (`A bela adormecida`). Sem isso o que volta é a linha
    `#REDIRECIONAMENTO [[...]]` — 39 caracteres em vez do conto inteiro.

    Devolve {titulo_pedido: (wikitext, titulo_resolvido)}."""
    d = _api(action="query", prop="revisions", rvprop="content", rvslots="main",
             redirects=1, titles="|".join(titulos))
    q = d.get("query", {})

    # A API responde pelos títulos JÁ resolvidos, então é preciso refazer o
    # caminho pedido → normalizado → redirecionado para reencontrar cada um.
    salto = {}
    for n in q.get("normalized", []):
        salto[n["from"]] = n["to"]
    for r in q.get("redirects", []):
        salto[r["from"]] = r["to"]

    def resolver(t):
        visto = set()
        while t in salto and t not in visto:
            visto.add(t)
            t = salto[t]
        return t

    paginas = {p.get("title"): p for p in q.get("pages", [])}
    saida = {}
    for t in titulos:
        p = paginas.get(resolver(t))
        if not p or p.get("missing"):
            saida[t] = ("", t)
            continue
        try:
            wt = p["revisions"][0]["slots"]["main"]["content"]
        except (KeyError, IndexError, TypeError):
            wt = ""
        saida[t] = (wt, p.get("title", t))
    return saida


def url_de(titulo):
    return "https://pt.wikisource.org/wiki/" + urllib.parse.quote(titulo.replace(" ", "_"))


def coletar(colecao="grimm", limite=0, forcar=False, verbose=True):
    """Baixa a coleção para `brutos/` e registra em `acervo.jsonl`.

    Retomável: pula o que já tem bruto no disco, a menos que `forcar`."""
    cfg = COLECOES[colecao]
    base.garantir_pastas()
    idx = base.carregar_indice()

    if verbose:
        print(f"Listando '{cfg['obra']}'...")
    titulos = listar_colecao(cfg["prefixo"])
    if verbose:
        print(f"  {len(titulos)} páginas na coleção.")

    # só o que ainda não está no disco (retomável)
    pendentes = []
    pulados = 0
    aparato = 0
    for titulo in titulos:
        _id = base.slug(titulo.split("/", 1)[-1])
        if _id in NAO_E_CONTO:
            aparato += 1
            continue
        if not forcar and os.path.exists(base.caminho(base.BRUTOS, _id, "txt")):
            pulados += 1
            continue
        pendentes.append(titulo)
    if aparato and verbose:
        print(f"  {aparato} página(s) de aparato editorial ignorada(s).")
    if limite:
        pendentes = pendentes[:limite]

    novos = falhas = 0
    for ini in range(0, len(pendentes), LOTE):
        bloco = pendentes[ini:ini + LOTE]
        if verbose:
            print(f"  baixando {ini + 1}–{ini + len(bloco)} de {len(pendentes)}...")
        try:
            resultados = baixar_lote(bloco)
        except Exception as e:                       # rede/HTTP/JSON
            falhas += len(bloco)
            if verbose:
                print(f"  FALHA no bloco: {e}")
            continue

        for titulo in bloco:
            wikitext, resolvido = resultados.get(titulo, ("", titulo))
            curto = titulo.split("/", 1)[-1]
            _id = base.slug(curto)
            # Redirecionamento não resolvido ou página vazia: registrar como
            # falha em vez de gravar um "conto" de 39 caracteres no acervo.
            if len(wikitext) < 200 or wikitext.lstrip().upper().startswith("#REDIR"):
                falhas += 1
                if verbose:
                    print(f"    vazia: {curto} ({len(wikitext)} chars)")
                continue
            base.escrever(base.BRUTOS, _id, "txt", wikitext)
            idx[_id] = {
                "id":        _id,
                "titulo":    curto,
                "obra":      cfg["obra"],
                "autor":     cfg["autor"],
                "licenca":   cfg["licenca"],
                "fonte":     "pt.wikisource.org",
                "url":       url_de(resolvido or titulo),
                "status":    "novo",
                "hash_bruto": base.hash_texto(wikitext),
                "n_chars_bruto": len(wikitext),
            }
            novos += 1
        base.gravar_indice(idx)   # grava a cada bloco: um Ctrl+C não perde tudo
        time.sleep(PAUSA)

    base.gravar_indice(idx)
    if verbose:
        print(f"\nNovos: {novos} | já tinha: {pulados} | falhas: {falhas}"
              f" | acervo: {len(idx)}")
    return novos, pulados, falhas


def main():
    ap = argparse.ArgumentParser(description="Coletor de histórias do Wikisource")
    ap.add_argument("--colecao", default="grimm", choices=sorted(COLECOES))
    ap.add_argument("--listar", action="store_true", help="só lista os títulos")
    ap.add_argument("--coletar", action="store_true", help="baixa para o acervo")
    ap.add_argument("--limite", type=int, default=0, help="máximo de histórias novas")
    ap.add_argument("--forcar", action="store_true", help="rebaixa o que já existe")
    a = ap.parse_args()
    base.console_utf8()

    if a.listar:
        for t in listar_colecao(COLECOES[a.colecao]["prefixo"]):
            print(t)
    elif a.coletar:
        coletar(a.colecao, a.limite, a.forcar)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
