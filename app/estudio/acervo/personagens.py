# -*- coding: utf-8 -*-
"""Elenco global do acervo — quem fala, em quantas histórias, e com que voz.

Personagens se repetem entre contos: `rei`, `princesa`, `lobo`, `raposa`,
`velhinha` aparecem em vários. Se cada história escolher voz por conta própria,
o mesmo lobo soa diferente em cada uma. Este módulo levanta o elenco de TODO o
acervo e mantém um mapa único `personagem -> arquivo de voz`, usado na síntese.

Duas fontes, por ordem de confiança:

  roteiros/<id>.json    elenco real da fase 1 (Gemma) — autoritativo
  adaptados/<id>.txt    elenco provável pelas tags de atribuição, sem LLM —
                        serve para ver o quadro antes de roteirizar o lote

Estrutura criada:

  vozes_personagens/
    mapa.json           {personagem: {voz, historias, falas}}
    lobo/               ponha aqui os .wav de referência desse personagem
    princesa/
    ...

A voz de um personagem pode ser um arquivo dentro da pasta dele ou o nome de
uma voz já salva em `estudio/vozes/` — a síntese resolve os dois.

Uso:
    python -m acervo.personagens --levantar
    python -m acervo.personagens --relatorio
    python -m acervo.personagens --definir lobo --voz "Dora (PT-F).wav"
"""
import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acervo import base, validar          # noqa: E402
import motor_v2 as motor                  # noqa: E402

VOZES_ESTUDIO = os.path.join(os.path.dirname(base.DIR), "vozes")

# Papéis que quase sempre pedem voz própria — usados só para ordenar o
# relatório, destacando onde investir gravação primeiro.
PAPEIS_COMUNS = {"rei", "rainha", "princesa", "principe", "lobo", "raposa",
                 "bruxa", "fada", "madrinha", "velhinha", "velho", "mae",
                 "pai", "menino", "menina", "gato", "rato", "urso", "sapo"}


def _do_roteiro(_id):
    p = base.caminho(base.ROTEIROS, _id, "json")
    if not os.path.exists(p):
        return None
    d = json.load(open(p, encoding="utf-8"))
    contagem = {}
    for b in d.get("roteiro", []):
        nome = b.get("quem")
        # mesmo filtro do caminho por tags: nome de 1–2 letras é resto de texto
        if b.get("fala") and nome != "narrador" and len(nome or "") >= 3:
            contagem[nome] = contagem.get(nome, 0) + 1
    return contagem


def _dos_tags(_id):
    """Elenco provável sem LLM, pelas tags de atribuição do texto adaptado."""
    p = base.caminho(base.ADAPTADOS, _id, "txt")
    if not os.path.exists(p):
        return None
    beats = motor._beats_historia(open(p, encoding="utf-8").read())
    contagem = {}
    for nome in validar._tags_de_falante(beats).values():
        # Nome de 1–2 letras é resto de texto truncado ("disse o fe"), não
        # personagem. Criar pasta de voz para isso só suja o mapa.
        if len(nome) < 3:
            continue
        contagem[nome] = contagem.get(nome, 0) + 1
    return contagem


def levantar(verbose=True):
    """Varre o acervo e devolve {personagem: {historias: [...], falas: N}}."""
    idx = base.carregar_indice()
    elenco = {}
    fontes = {"roteiro": 0, "tags": 0}
    for _id in sorted(idx):
        contagem = _do_roteiro(_id)
        fonte = "roteiro"
        if contagem is None:
            contagem = _dos_tags(_id)
            fonte = "tags"
        if not contagem:
            continue
        fontes[fonte] += 1
        for nome, n in contagem.items():
            e = elenco.setdefault(nome, {"historias": [], "falas": 0})
            e["historias"].append(_id)
            e["falas"] += n
    if verbose:
        print(f"{len(elenco)} personagens em {fontes['roteiro']} roteiro(s) "
              f"+ {fontes['tags']} texto(s) adaptado(s) sem roteiro ainda.")
    return elenco


def parecidos(nomes, minimo=4):
    """Sugere nomes que provavelmente são o MESMO personagem.

    `lobo`/`lobinho`, `velha`/`velhinha`: variações de diminutivo produzem
    entradas separadas no elenco e, portanto, vozes diferentes para o mesmo
    papel. Só sugere — a fusão é decisão de quem revisa."""
    pares = []
    lista = sorted(nomes)
    for i, a in enumerate(lista):
        for b in lista[i + 1:]:
            if len(a) < minimo or len(b) < minimo:
                continue
            if b.startswith(a) or a.startswith(b):
                pares.append((a, b))
    return pares


def carregar_mapa():
    if os.path.exists(base.MAPA_VOZES):
        try:
            return json.load(open(base.MAPA_VOZES, encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def gravar_mapa(mapa):
    base.garantir_pastas()
    tmp = base.MAPA_VOZES + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(mapa, f, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, base.MAPA_VOZES)


def sincronizar(minimo=2, verbose=True):
    """Cria a pasta dos personagens RECORRENTES e atualiza o mapa, sem perder
    escolhas de voz já feitas.

    `minimo` = em quantas histórias o personagem precisa aparecer para ganhar
    pasta. 72% do elenco aparece em uma história só, e a `PALETA` do motor já
    dá voz automática a quem não está mapeado — criar 156 pastas para gravar
    seria trabalho jogado fora. O esforço de gravação rende nos papéis que se
    repetem: `mae` e `rei` aparecem em 13 contos cada."""
    todos = levantar(verbose=False)
    elenco = {n: d for n, d in todos.items() if len(d["historias"]) >= minimo}
    mapa = carregar_mapa()
    base.garantir_pastas()
    if verbose:
        print(f"{len(todos)} personagens no acervo · {len(elenco)} aparecem em "
              f"{minimo}+ histórias (os demais usam a PALETA automática)")
    novos = 0
    for nome, dados in elenco.items():
        pasta = os.path.join(base.VOZES_PERS, nome)
        os.makedirs(pasta, exist_ok=True)
        reg = mapa.setdefault(nome, {"voz": None})
        if reg.get("voz") is None:
            novos += 1
        reg["historias"] = len(dados["historias"])
        reg["falas"] = dados["falas"]
        # se o usuário largou um .wav na pasta e ainda não escolheu, adota
        if not reg.get("voz"):
            wavs = sorted(glob.glob(os.path.join(pasta, "*.wav")))
            if wavs:
                reg["voz"] = os.path.basename(wavs[0])
    gravar_mapa(mapa)
    if verbose:
        print(f"{len(elenco)} pasta(s) em {base.VOZES_PERS}")
        print(f"{len(elenco) - novos} com voz definida · {novos} sem voz ainda")
    return mapa


def voz_de(nome, mapa=None):
    """Caminho do arquivo de voz do personagem, ou None.

    Aceita tanto um .wav dentro de `vozes_personagens/<nome>/` quanto o nome de
    uma voz salva em `estudio/vozes/`."""
    mapa = mapa if mapa is not None else carregar_mapa()
    reg = mapa.get(nome) or {}
    # `voz_arquivo` é caminho absoluto para um áudio que já existia no projeto
    # (ver casar_vozes): a referência é apontada, não copiada, para não duplicar
    # arquivo nem perder a rastreabilidade de onde a voz veio.
    externo = reg.get("voz_arquivo")
    if externo and os.path.exists(externo):
        return externo
    voz = reg.get("voz")
    if not voz:
        return None
    p = os.path.join(base.VOZES_PERS, nome, voz)
    if os.path.exists(p):
        return p
    p = os.path.join(VOZES_ESTUDIO, voz)
    return p if os.path.exists(p) else None


def vozes_da_historia(_id, mapa=None):
    """{personagem: caminho_da_voz} para uma história — o que a síntese passa
    como `vozes_map` para `sintetizar_roteiro`."""
    mapa = mapa if mapa is not None else carregar_mapa()
    contagem = _do_roteiro(_id) or _dos_tags(_id) or {}
    saida = {}
    for nome in contagem:
        v = voz_de(nome, mapa)
        if v:
            saida[nome] = v
    return saida


def relatorio(elenco=None, mapa=None):
    elenco = elenco if elenco is not None else levantar(verbose=False)
    mapa = mapa if mapa is not None else carregar_mapa()
    if not elenco:
        print("Nenhum personagem ainda — adapte e roteirize alguma história.")
        return
    ordenado = sorted(elenco.items(),
                      key=lambda x: (-len(x[1]["historias"]), -x[1]["falas"]))
    print(f"{'personagem':<16} {'histórias':>9} {'falas':>6}  voz")
    print("-" * 62)
    for nome, d in ordenado:
        voz = (mapa.get(nome) or {}).get("voz") or "—"
        marca = "*" if nome in PAPEIS_COMUNS else " "
        print(f"{marca}{nome:<15} {len(d['historias']):>9} {d['falas']:>6}  {voz}")
    print("-" * 62)
    print(f"{len(elenco)} personagens · "
          f"{sum(1 for n in elenco if (mapa.get(n) or {}).get('voz'))} com voz")
    print("* = papel que costuma se repetir entre contos (priorize a gravação)")

    pares = parecidos(elenco)
    if pares:
        print("\nProvavelmente o MESMO personagem (considere unificar):")
        for a, b in pares:
            print(f"  {a} ~ {b}")


def main():
    ap = argparse.ArgumentParser(description="Elenco global e vozes por personagem")
    ap.add_argument("--levantar", action="store_true",
                    help="cria as pastas e atualiza o mapa")
    ap.add_argument("--minimo", type=int, default=2,
                    help="em quantas histórias o personagem precisa aparecer "
                         "para ganhar pasta de voz (padrão 2)")
    ap.add_argument("--relatorio", action="store_true")
    ap.add_argument("--definir", metavar="PERSONAGEM")
    ap.add_argument("--voz", metavar="ARQUIVO")
    ap.add_argument("--historia", metavar="ID",
                    help="mostra o mapa de vozes de uma história")
    a = ap.parse_args()
    base.console_utf8()

    if a.definir:
        if not a.voz:
            print("Use --definir PERSONAGEM --voz ARQUIVO.wav")
            return
        mapa = carregar_mapa()
        mapa.setdefault(a.definir, {})["voz"] = a.voz
        gravar_mapa(mapa)
        p = voz_de(a.definir, mapa)
        print(f"{a.definir} -> {a.voz}" + ("" if p else "   (ARQUIVO NÃO ENCONTRADO)"))
        return
    if a.historia:
        for k, v in vozes_da_historia(a.historia).items():
            print(f"  {k:<14} {v}")
        return
    if a.levantar:
        sincronizar(a.minimo)
        print()
    relatorio()


if __name__ == "__main__":
    main()
