# -*- coding: utf-8 -*-
"""Encontra, no áudio que o projeto já tem, a voz de cada personagem.

Por que buscar em vez de gerar: o modo Design do OmniVoice tem um espaço de
timbre estreito — medido, seis gerações com a MESMA instrução variaram só ~3
semitons em F0 e 300 Hz de centroide. São a mesma voz repetida. Já o clonador é
zero-shot e fiel: ele reproduz qualquer referência que receber. Ou seja, a
identidade de um personagem mora na REFERÊNCIA, não em processamento posterior
— foi tentando fabricar identidade com DSP que apareceram os artefatos.

O projeto acumulou ~150 arquivos de voz em `vozes/` e nos laboratórios, muitos
sem rótulo. Este módulo mede todos e procura, para cada personagem, o que mais
se aproxima do alvo dele em dois eixos:

    F0        altura da voz (semitons, escala log — é como o ouvido compara)
    centroide proxy do tamanho do trato vocal (corpo grande x pequeno)

Uso:
    python -m acervo.casar_vozes --inventario
    python -m acervo.casar_vozes --casar
    python -m acervo.casar_vozes --casar --aplicar
    python -m acervo.casar_vozes --audicao lobo,rato,rei
"""
import argparse
import glob
import hashlib
import json
import os
import sys
import warnings

import numpy as np

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acervo import base, personagens                      # noqa: E402
from acervo.gerar_vozes import VOZES, resolver_alias      # noqa: E402
import motor_v2 as motor                                  # noqa: E402

APP = os.path.dirname(os.path.dirname(base.DIR))          # .../app
CACHE = os.path.join(base.DIR, "_inventario_vozes.json")

# Onde procurar. Ordem importa: o que vem primeiro ganha em caso de empate,
# então as vozes nomeadas e curadas vêm antes das sobras de laboratório.
PASTAS = [
    # falantes triados de um corpus externo (ver importar_corpus.py)
    os.path.join(base.DIR, "vozes_corpus"),
    os.path.join(APP, "estudio", "vozes"),
    os.path.join(APP, "laboratorios", "refs_humanas"),
    os.path.join(APP, "laboratorios", "voices_ref"),
    os.path.join(APP, "laboratorios", "vozes_custom"),
    os.path.join(APP, "laboratorios", "refs_emocao"),
    os.path.join(APP, "laboratorios", "teste_ref"),
]

# Qualidade mínima para um arquivo servir de referência de clone.
MIN_VOZEADO = 0.55
MIN_SEG = 3.0
MAX_SEG = 25.0

# F0 alvo por gênero e faixa de altura, em Hz — valores de voz humana real, não
# do que o OmniVoice produz. É contra gente que estamos casando agora.
F0_BASE = {
    "male":   {"very low pitch": 95, "low pitch": 125, "moderate pitch": 155,
               "high pitch": 190, "very high pitch": 225},
    "female": {"very low pitch": 155, "low pitch": 185, "moderate pitch": 215,
               "high pitch": 255, "very high pitch": 300},
}
F0_IDADE = {"child": 55, "teenager": 25, "young adult": 0,
            "middle-aged": -5, "elderly": -10}

# Centroide de referência de uma voz adulta neutra; o formante do personagem
# escala esse alvo (corpo maior => centroide menor).
CENTROIDE_BASE = 2500.0


def _hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 16), b""):
            h.update(bloco)
    return h.hexdigest()[:16]


def medir(path):
    """Cinco eixos, na ordem em que o ELENCO_VOZES.md os define.

    `variacao` é a adição que faltava e a mais importante: o desvio do F0 em
    SEMITONS. É o que separa o rei do rato tendo os dois a mesma gravidade —
    autoridade é plana, bicho pequeno é cantado. Medir só altura e corpo fez
    todo o elenco soar parecido."""
    import librosa
    y, sr = librosa.load(path, sr=None, mono=True)
    dur = len(y) / sr
    if dur < 0.5:
        return None
    f, vf, _ = librosa.pyin(y.astype(float), fmin=60, fmax=450, sr=sr,
                            frame_length=2048)
    v = f[~np.isnan(f)]
    f0 = float(np.median(v)) if len(v) else 0.0
    # desvio em semitons em torno da própria mediana (escala do ouvido)
    variacao = (float(np.std(12 * np.log2(np.clip(v, 1, None) / max(f0, 1))))
                if len(v) > 8 else 0.0)
    # tempo: ataques por segundo — quantas sílabas/notas a voz dispara
    try:
        onsets = librosa.onset.onset_detect(y=y, sr=sr, units="time")
        taxa = len(onsets) / dur
    except Exception:
        taxa = 0.0
    # textura: achatamento espectral. Voz limpa é harmônica (baixo); voz
    # soprada ou áspera tem mais ruído entre os harmônicos (alto).
    textura = float(np.mean(librosa.feature.spectral_flatness(y=y)))
    return {
        "dur": round(dur, 2),
        "f0": round(f0, 1),
        "variacao": round(variacao, 2),
        "centroide": round(float(np.mean(
            librosa.feature.spectral_centroid(y=y, sr=sr))), 0),
        "taxa": round(float(taxa), 2),
        "textura": round(textura, 4),
        "vozeado": round(float(np.mean(vf)), 3),
        "rms": round(float(np.sqrt((y ** 2).mean())), 4),
    }


def inventariar(forcar=False, verbose=True):
    """Mede todos os áudios candidatos. O resultado é cacheado: medir 150
    arquivos com pyin leva minutos e não muda entre execuções."""
    cache = {}
    if os.path.exists(CACHE) and not forcar:
        try:
            cache = json.load(open(CACHE, encoding="utf-8"))
        except json.JSONDecodeError:
            cache = {}
    arquivos = []
    for pasta in PASTAS:
        arquivos += sorted(glob.glob(os.path.join(pasta, "*.wav")))
    novos = 0
    for p in arquivos:
        chave = os.path.relpath(p, APP).replace("\\", "/")
        if chave in cache and not forcar:
            continue
        try:
            m = medir(p)
        except Exception:
            continue
        if not m:
            continue
        m["hash"] = _hash(p)
        cache[chave] = m
        novos += 1
        if verbose and novos % 20 == 0:
            print(f"  ...{novos} medidos")
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), indent=1)
    if verbose:
        print(f"{len(cache)} arquivo(s) no inventário ({novos} novo(s)).")
    return cache


def candidatos(cache):
    """Filtra por qualidade e remove duplicatas exatas.

    Metade da pasta `vozes/` é `_ref_*`, cópias das vozes nomeadas guardadas
    pelo estúdio web — sem deduplicar, o mesmo timbre disputaria vários
    personagens."""
    vistos, saida = {}, []
    for caminho, m in cache.items():
        if m["vozeado"] < MIN_VOZEADO or not (MIN_SEG <= m["dur"] <= MAX_SEG):
            continue
        if m["f0"] <= 0:
            continue
        h = m.get("hash")
        if h and h in vistos:
            continue
        if h:
            vistos[h] = caminho
        saida.append((caminho, m))
    return saida


# ── Gênero e idioma do candidato ─────────────────────────────────────────────
# Casar só por F0 põe voz de mulher em personagem homem: `pai` casou com
# `af_sky.wav` e `principe` com `Nina (PT-F suave)`, porque a 155 Hz os números
# batem. Mas gênero percebido vem do timbre inteiro, não da altura — um homem e
# uma mulher no mesmo F0 não se confundem ao ouvido.
_MARCA_GENERO = [
    (r"(?:^|[_\-])(?:am|bm|pm|em|im|jm|zm|hm|ff)_", "male"),    # prefixos Kokoro
    (r"(?:^|[_\-])(?:af|bf|pf|ef|if|jf|zf|hf)_", "female"),
    (r"PT-M|\(M\)|[_\-]m[_\-]|masc", "male"),
    (r"PT-F|\(F\)|[_\-]f[_\-]|fem", "female"),
]
# Vozes de OUTRO idioma clonam com sotaque em português. No esquema de nomes do
# Kokoro a primeira letra é o idioma (a=inglês EUA, b=inglês GB, e=espanhol,
# f=francês, h=híndi, i=italiano, j=japonês, z=chinês, p=português) e a segunda
# é o gênero. Só `pf_`/`pm_` servem. A primeira versão barrava só `af/am/bf/bm`
# e deixou passar `zf_xiaoyi` (chinês) como voz do pássaro.
_MARCA_ESTRANGEIRA = r"(?:^|[_\-])(?:[abefhijz][fm])_"

# Saídas do laboratório de conversão de voz (seed-vc): já são áudio processado,
# não referência limpa — clonar em cima de conversão empilha artefato.
_MARCA_PROCESSADA = r"(?:^|[_\-])(?:vc|syn|out|conv)[_\-]"


def genero_do_arquivo(caminho, m):
    """('male'|'female', confiança). O nome do arquivo é a pista boa; a
    acústica só entra quando ele não diz nada, e aí com margem folgada."""
    import re
    nome = os.path.basename(caminho)
    for padrao, g in _MARCA_GENERO:
        if re.search(padrao, nome, re.IGNORECASE):
            return g, "arquivo"
    f0 = m.get("f0", 0)
    if f0 and f0 <= 145:
        return "male", "acustica"
    if f0 >= 200:
        return "female", "acustica"
    return None, "incerto"       # zona de sobreposição: não arrisca


def eh_ingles(caminho):
    """Nome mantido por compatibilidade: hoje barra qualquer idioma que não
    seja português, e também áudio já processado."""
    import re
    nome = os.path.basename(caminho)
    return bool(re.search(_MARCA_ESTRANGEIRA, nome, re.IGNORECASE)
                or re.search(_MARCA_PROCESSADA, nome, re.IGNORECASE))


# ── Elenco: alvos vindos do ELENCO_VOZES.md ─────────────────────────────────
#
# Expressos como POSIÇÃO RELATIVA dentro do acervo, não em Hz. Duas razões:
# não faz sentido eu chutar "3,7 ataques por segundo" sem conhecer a
# distribuição real das gravações; e o que importa para o ouvinte é o contraste
# ENTRE personagens, não o valor absoluto de cada um.
#
# Os percentis são calculados por gênero — a distribuição de F0 masculina e
# feminina são outras, e comparar as duas na mesma régua foi o que pôs voz de
# mulher no pai na primeira tentativa.
NIVEL = {"mto_baixo": 0.08, "baixo": 0.25, "medio": 0.50,
         "alto": 0.75, "mto_alto": 0.92}


def _p(genero, f0, variacao, corpo, tempo):
    return dict(genero=genero, f0=f0, variacao=variacao, corpo=corpo,
                tempo=tempo)


# Lido diretamente do documento de direção. Cada linha é uma frase de lá.
ELENCO = {
    # realeza — autoridade é plana
    "rei":       _p("male",   "mto_baixo", "mto_baixo", "baixo",     "baixo"),
    "rainha":    _p("female", "baixo",     "baixo",     "medio",     "baixo"),
    "principe":  _p("male",   "medio",     "medio",     "medio",     "alto"),
    "princesa":  _p("female", "alto",      "alto",      "alto",      "medio"),
    # família — mãe e madrasta: mesma altura, variação oposta
    "mae":       _p("female", "baixo",     "medio",     "medio",     "baixo"),
    "madrasta":  _p("female", "baixo",     "mto_baixo", "baixo",     "medio"),
    "pai":       _p("male",   "baixo",     "baixo",     "medio",     "medio"),
    "madrinha":  _p("female", "medio",     "medio",     "medio",     "baixo"),
    "filho":     _p("male",   "alto",      "alto",      "alto",      "alto"),
    "filha":     _p("female", "alto",      "alto",      "alto",      "alto"),
    "irmao":     _p("male",   "medio",     "alto",      "medio",     "alto"),
    "esposa":    _p("female", "medio",     "medio",     "medio",     "medio"),
    "menina":    _p("female", "mto_alto",  "mto_alto",  "mto_alto",  "alto"),
    "menino":    _p("male",   "mto_alto",  "mto_alto",  "mto_alto",  "alto"),
    "lila":      _p("female", "mto_alto",  "mto_alto",  "mto_alto",  "alto"),
    "clara":     _p("female", "mto_alto",  "mto_alto",  "mto_alto",  "alto"),
    "sofia":     _p("female", "alto",      "alto",      "alto",      "alto"),
    "pequeno":   _p("male",   "mto_alto",  "mto_alto",  "mto_alto",  "mto_alto"),
    # povo — homens do campo falam pouco e sem ornamento
    "velhinha":  _p("female", "alto",      "medio",     "baixo",     "mto_baixo"),
    "velho":     _p("male",   "mto_baixo", "baixo",     "baixo",     "mto_baixo"),
    "senhor":    _p("male",   "baixo",     "baixo",     "medio",     "baixo"),
    "senhora":   _p("female", "medio",     "medio",     "medio",     "baixo"),
    "pastor":    _p("male",   "mto_baixo", "mto_baixo", "baixo",     "mto_baixo"),
    "moleiro":   _p("male",   "baixo",     "baixo",     "baixo",     "baixo"),
    "lenhador":  _p("male",   "mto_baixo", "mto_baixo", "baixo",     "baixo"),
    "campones":  _p("male",   "baixo",     "mto_baixo", "baixo",     "baixo"),
    "cacador":   _p("male",   "baixo",     "baixo",     "baixo",     "medio"),
    "homem":     _p("male",   "medio",     "medio",     "medio",     "medio"),
    "soldado":   _p("male",   "baixo",     "baixo",     "medio",     "alto"),
    # o alfaiate é pequeno, rápido e vaidoso
    "alfaiate":  _p("male",   "alto",      "mto_alto",  "alto",      "mto_alto"),
    "criada":    _p("female", "medio",     "medio",     "medio",     "alto"),
    "joao":      _p("male",   "medio",     "medio",     "medio",     "medio"),
    "pedro":     _p("male",   "alto",      "alto",      "alto",      "alto"),
    "lucas":     _p("male",   "baixo",     "medio",     "medio",     "medio"),
    # vilões — ameaça é calma, não rosnado
    "lobo":      _p("male",   "mto_baixo", "mto_baixo", "mto_baixo", "mto_baixo"),
    "bruxa":     _p("female", "mto_baixo", "mto_alto",  "baixo",     "medio"),
    "diabo":     _p("male",   "mto_baixo", "mto_baixo", "baixo",     "mto_baixo"),
    "gigante":   _p("male",   "mto_baixo", "baixo",     "mto_baixo", "mto_baixo"),
    # bichos — tamanho no corpo, temperamento na variação
    "sapo":      _p("male",   "mto_baixo", "medio",     "mto_baixo", "baixo"),
    "burro":     _p("male",   "baixo",     "mto_baixo", "baixo",     "mto_baixo"),
    "cachorro":  _p("male",   "medio",     "mto_alto",  "medio",     "mto_alto"),
    "gato":      _p("female", "alto",      "medio",     "alto",      "medio"),
    "raposa":    _p("female", "medio",     "baixo",     "medio",     "alto"),
    "galo":      _p("male",   "mto_alto",  "mto_alto",  "mto_alto",  "mto_alto"),
    "galinha":   _p("female", "alto",      "mto_alto",  "alto",      "alto"),
    "rato":      _p("male",   "mto_alto",  "mto_alto",  "mto_alto",  "mto_alto"),
    "passaro":   _p("female", "mto_alto",  "mto_alto",  "mto_alto",  "mto_alto"),
    "cavalo":    _p("male",   "baixo",     "baixo",     "baixo",     "baixo"),
    "urso":      _p("male",   "mto_baixo", "baixo",     "mto_baixo", "mto_baixo"),
    "coelhinho": _p("male",   "alto",      "alto",      "alto",      "alto"),
    # mágicos
    "fada":      _p("female", "mto_alto",  "mto_alto",  "alto",      "alto"),
    "anao":      _p("male",   "alto",      "medio",     "mto_alto",  "medio"),
}

# Peso de cada eixo na distância. A VARIAÇÃO pesa tanto quanto a altura: é ela
# que separa o rei do lobo e a mãe da madrasta.
PESOS = {"f0": 1.0, "variacao": 1.0, "corpo": 0.8, "tempo": 0.6}


def escalas(pool):
    """Distribuição de cada eixo no acervo, separada por gênero."""
    import collections
    eixos = {"f0": "f0", "variacao": "variacao", "corpo": "centroide",
             "tempo": "taxa"}
    dados = collections.defaultdict(lambda: collections.defaultdict(list))
    for caminho, m in pool:
        g, _ = genero_do_arquivo(caminho, m)
        for eixo, campo in eixos.items():
            val = m.get(campo)
            if val:
                dados[g or "?"][eixo].append(val)
                dados["todos"][eixo].append(val)
    return dados


def alvo_de(nome, esc=None):
    """Alvo de um personagem em valores absolutos, resolvido contra o acervo."""
    perfil = ELENCO.get(resolver_alias(nome))
    if not perfil:
        return None
    eixos = {"f0": "f0", "variacao": "variacao", "corpo": "corpo",
             "tempo": "tempo"}
    alvo = {"genero": perfil["genero"]}
    for eixo in eixos:
        amostras = (esc or {}).get(perfil["genero"], {}).get(eixo) \
            or (esc or {}).get("todos", {}).get(eixo) or []
        if not amostras:
            alvo[eixo] = None
            continue
        alvo[eixo] = float(np.percentile(amostras, 100 * NIVEL[perfil[eixo]]))
    return alvo


_CAMPO = {"f0": "f0", "variacao": "variacao", "corpo": "centroide",
          "tempo": "taxa"}


def _percentil(valor, amostras):
    """Onde `valor` cai dentro da distribuição do acervo, de 0 a 1."""
    if not amostras or valor is None:
        return None
    return float(np.mean(np.asarray(amostras) <= valor))


def _distancia(m, perfil, esc):
    """Distância nos quatro eixos, medida em PERCENTIL.

    Comparar em percentil e não em Hz é o que permite pôr altura, variação,
    corpo e tempo na mesma régua — as unidades são incomparáveis, mas "está no
    topo da distribuição" significa a mesma coisa em todas."""
    g = perfil["genero"]
    total = peso_total = 0.0
    detalhe = {}
    for eixo, campo in _CAMPO.items():
        amostras = esc.get(g, {}).get(eixo) or esc.get("todos", {}).get(eixo)
        p_cand = _percentil(m.get(campo), amostras)
        if p_cand is None:
            continue
        p_alvo = NIVEL[perfil[eixo]]
        w = PESOS[eixo]
        total += w * abs(p_cand - p_alvo)
        peso_total += w
        detalhe[eixo] = (p_cand, p_alvo)
    return (total / peso_total if peso_total else 9.9), detalhe


def coocorrencias():
    """{personagem: conjunto de quem divide história com ele}.

    Duas vozes só precisam ser diferentes se o ouvinte as ouvir na mesma
    história. Fora disso, reusar a mesma referência é inofensivo — e necessário,
    já que o acervo tem 8 vozes masculinas para cerca de 20 papéis de homem."""
    import glob as _glob
    import json as _json
    mapa = {}
    for p in _glob.glob(os.path.join(base.ROTEIROS, "*.json")):
        try:
            d = _json.load(open(p, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        elenco = {resolver_alias(n) for n in d.get("elenco", [])}
        for n in elenco:
            mapa.setdefault(n, set()).update(elenco - {n})
    return mapa


def casar(minimo=2, top=3, permitir_en=False, verbose=True):
    """Para cada personagem do acervo, os melhores candidatos.

    Um arquivo não é oferecido a dois personagens: o casamento é guloso, na
    ordem de importância (quem aparece em mais histórias escolhe primeiro)."""
    cache = inventariar(verbose=False)
    pool = candidatos(cache)
    el = personagens.levantar(verbose=False)
    ordem = sorted({resolver_alias(n): len(d["historias"]) for n, d in el.items()
                    if len(d["historias"]) >= minimo}.items(),
                   key=lambda x: -x[1])
    if verbose:
        print(f"{len(pool)} candidato(s) úteis de {len(cache)} arquivos "
              f"medidos · {len(ordem)} personagem(ns)\n")

    esc = escalas(pool)

    # Quem contracena com quem. Reusar a mesma referência em dois personagens é
    # aceitável — com 8 vozes masculinas para 20 papéis não há alternativa —
    # DESDE QUE eles nunca apareçam na mesma história.
    juntos = coocorrencias()

    # Ordem de escolha por ESPECIFICIDADE, não por frequência. Ordenar por
    # número de histórias fazia `pai`, `rei` e `homem` consumirem as vozes
    # graves, e sobrava para o lobo e o diabo — que são exatamente os papéis
    # que dependem de gravidade — o que ninguém quis. Um "homem" genérico
    # aceita qualquer voz; um lobo, não. Quem tem exigência extrema escolhe
    # primeiro.
    def especificidade(nome):
        p = ELENCO.get(resolver_alias(nome))
        if not p:
            return 0.0
        return sum(abs(NIVEL[p[e]] - 0.5) for e in _CAMPO)

    ordem = sorted(ordem, key=lambda x: -especificidade(x[0]))

    usados, escolhas = {}, {}
    for nome, n_hist in ordem:
        perfil = ELENCO.get(resolver_alias(nome))
        if not perfil:
            continue
        contracenam = juntos.get(nome, set())
        ranking = []
        for caminho, m in pool:
            # bloqueia só se a voz já foi para alguém que divide cena com este
            donos = usados.get(caminho, set())
            if donos & contracenam:
                continue
            g, _fonte = genero_do_arquivo(caminho, m)
            if g and g != perfil["genero"]:
                continue                      # nunca voz de mulher em homem
            if not permitir_en and eh_ingles(caminho):
                continue                      # outro idioma ou áudio processado
            d, det = _distancia(m, perfil, esc)
            if g is None:
                d += 0.15                     # gênero incerto: desempate contra
            ranking.append((d, caminho, m, det))
        ranking.sort(key=lambda x: x[0])
        if not ranking:
            continue
        escolhas[nome] = ranking[:top]
        usados.setdefault(ranking[0][1], set()).add(nome)
        if verbose:
            alvos = " ".join(f"{e}={NIVEL[perfil[e]]:.2f}" for e in _CAMPO)
            print(f"{nome}  ({n_hist}h, {perfil['genero']})  alvo: {alvos}")
            for i, (d, caminho, m, det) in enumerate(ranking[:top]):
                marca = "->" if i == 0 else "  "
                obtido = " ".join(f"{e}={det[e][0]:.2f}" for e in _CAMPO
                                  if e in det)
                print(f"  {marca} {os.path.basename(caminho)[:30]:32} "
                      f"d={d:.3f}  {obtido}")
            print()
    return escolhas


def aplicar(escolhas, verbose=True):
    """Grava a primeira opção de cada personagem no mapa de vozes."""
    mapa = personagens.carregar_mapa()
    n = travados = 0
    for nome, ranking in escolhas.items():
        if not ranking:
            continue
        # Voz que o usuário já ouviu e aprovou não é sobrescrita por um
        # casamento novo. Sem esta trava, uma rodada do casador apagou a voz
        # Kokoro do `rato` — que tinha sido aprovada de ouvido — e a trocou por
        # um arquivo que os números preferiam. Mesmo princípio do
        # `fonte_adaptacao == "manual"` nas adaptações escritas à mão.
        if (mapa.get(nome) or {}).get("travado"):
            travados += 1
            continue
        caminho = os.path.join(APP, ranking[0][1])
        pasta = os.path.join(base.VOZES_PERS, nome)
        os.makedirs(pasta, exist_ok=True)
        reg = mapa.setdefault(nome, {})
        reg["voz_arquivo"] = caminho          # referência externa, não copiada
        reg["voz"] = None                     # anula a semente desenhada
        reg["origem"] = "acervo_local"
        n += 1
    personagens.gravar_mapa(mapa)
    if verbose:
        print(f"{n} personagem(ns) apontando para voz do acervo local"
              + (f" · {travados} preservado(s) por já estarem aprovados."
                 if travados else "."))
    return n


def audicao(nome, top=5, frase=None, verbose=True):
    """Sintetiza a MESMA frase com os N melhores candidatos de um personagem.

    O casador escolhe por número, mas quem decide é o ouvido — e até aqui só
    dava para ouvir a escolha dele, nunca as alternativas. Isto gera um arquivo
    único com as opções em sequência, numeradas na saída do terminal, para
    escolher por audição e travar com `personagens.py --definir`."""
    import soundfile as sf
    import motor_v2 as mot

    frase = frase or "Bom dia! Quem está aí, escondido atrás daquela árvore grande?"
    esc = casar(minimo=1, top=top, verbose=False)
    ranking = esc.get(resolver_alias(nome))
    if not ranking:
        print(f"Sem candidatos para '{nome}'.")
        return None

    mot.descarregar_gemma()
    m = mot.carregar_omni()
    cfg = mot._cfg()
    silencio = np.zeros(int(0.9 * mot.SR), dtype=np.float32)
    partes = []
    print(f"\nOpções para '{nome}' (na ordem em que serão ouvidas):")
    for i, (d, caminho, med, _det) in enumerate(ranking, 1):
        completo = os.path.join(APP, caminho)
        try:
            perfil = mot.perfil_voz(completo)
            seg = mot._gerar_um(m, cfg, mot._criar_prompt_voz(m, perfil),
                                frase, perfil["base_speed"], 1.0, 1.0)
        except Exception as e:
            print(f"  {i}. {os.path.basename(caminho)} — falhou ({e})")
            continue
        partes += [seg, silencio]
        print(f"  {i}. {os.path.basename(caminho):<28} "
              f"F0={med['f0']:6.1f} var={med['variacao']:4.2f} "
              f"corpo={med['centroide']:5.0f}  d={d:.3f}")
    if not partes:
        return None
    base.garantir_pastas()
    destino = os.path.join(base.AUDIOS, f"_opcoes_{resolver_alias(nome)}.wav")
    sf.write(destino, np.concatenate(partes), mot.SR)
    print(f"\n-> {destino}")
    print(f"Escolheu a opção N? Trave com:\n"
          f"   python -m acervo.personagens --definir {nome} --voz <arquivo da opção N>")
    return destino


def main():
    ap = argparse.ArgumentParser(description="Casa personagens com o áudio já existente")
    ap.add_argument("--inventario", action="store_true")
    ap.add_argument("--forcar", action="store_true")
    ap.add_argument("--casar", action="store_true")
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--top", type=int, default=3)
    ap.add_argument("--audicao", metavar="PERSONAGEM",
                    help="gera as N melhores opcoes de voz para ouvir")
    ap.add_argument("--minimo", type=int, default=2)
    ap.add_argument("--permitir-en", action="store_true",
                    help="aceita vozes treinadas em ingles (clonam com sotaque)")
    a = ap.parse_args()
    base.console_utf8()

    if a.audicao:
        audicao(a.audicao, a.top)
        return
    if a.inventario:
        inventariar(a.forcar)
        return
    if a.casar:
        esc = casar(a.minimo, a.top, a.permitir_en)
        if a.aplicar:
            aplicar(esc)
        return
    ap.print_help()


if __name__ == "__main__":
    main()
