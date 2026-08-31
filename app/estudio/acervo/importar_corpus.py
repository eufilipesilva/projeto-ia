# -*- coding: utf-8 -*-
"""Importa um corpus de fala externo como banco de vozes de referência.

Pensado para o **Mozilla Common Voice** em português (CC0, ~3.800 falantes),
mas serve para qualquer corpus com a mesma forma: um TSV de metadados e uma
pasta de clipes.

Por que ele existe: nem o modo Design do OmniVoice nem os blends do Kokoro dão
variedade de TIMBRE humano — os dois produzem variações de um mesmo modelo. Voz
de gente tem grão, idade e sotaque que nenhum TTS inventa. O que falta ao
projeto é matéria-prima, e é isso que um corpus traz.

O trabalho aqui não é baixar, é **triar**. Um clipe de Common Voice tem ~5s,
microfone de celular e ruído de casa — a maior parte não serve como referência
de clone, porque o clonador copia o ruído junto. Este módulo:

  1. agrupa os clipes por `client_id` (o mesmo falante aparece várias vezes)
  2. emenda os clipes de cada falante até chegar a ~15s — bem acima dos 3s que
     o clone precisa, e o suficiente para o timbre se firmar
  3. mede e descarta o que tem pouca voz, pouco sinal ou ruído demais
  4. grava um .wav por falante, com o .txt da transcrição ao lado

A saída cai numa pasta que o `casar_vozes.py` já sabe ler — daí em diante é o
mesmo casamento por perfil do ELENCO_VOZES.md.

Onde conseguir o corpus (é preciso aceitar os termos no site):
    https://commonvoice.mozilla.org/pt/datasets

Uso:
    python -m acervo.importar_corpus --pasta D:/cv-corpus-pt --limite 200
    python -m acervo.importar_corpus --pasta D:/cv-corpus-pt --relatorio
"""
import argparse
import collections
import csv
import os
import sys
import warnings

import numpy as np
import soundfile as sf

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acervo import base  # noqa: E402

# Onde os falantes triados são gravados. `casar_vozes.PASTAS` deve incluir esta.
DESTINO = os.path.join(base.DIR, "vozes_corpus")

SEG_ALVO = 15.0      # duração desejada por falante, emendando clipes
SEG_MIN = 6.0        # abaixo disso o falante é descartado
MIN_VOZEADO = 0.55   # fração de quadros com pitch
MIN_RMS = 0.010      # sinal fraco demais = gravação ruim
# Achatamento espectral máximo. Calibrado contra as 149 referências que o
# projeto já usa, não escolhido no chute: elas vão de 0.003 (p10) a 0.072 (p90),
# com mediana 0.027 — e a própria `Pandora.wav`, a voz principal, marca 0.0348.
# O primeiro valor que usei aqui, 0.010, teria reprovado a Pandora por 3,5x, e
# de fato reprovou 100% dos locutores do MLS (que ficam entre 0.011 e 0.020,
# ou seja, mais limpos que ela). Limiar que reprova tudo é limiar errado.
MAX_PLANURA = 0.060  # entre o p75 e o p90 do acervo: aceita fala, corta ruído


# ── MLS (Multilingual LibriSpeech) ───────────────────────────────────────────
# Formato bem diferente do Common Voice, e melhor para o nosso caso:
#
#   metainfo.txt              SPEAKER | GENDER | PARTITION | MINUTES | BOOK ...
#   train|dev|test/
#     transcripts.txt         <id>\t<texto>
#     audio/<locutor>/<livro>/<id>.flac  (ou .opus)
#
# O `metainfo.txt` traz o GÊNERO declarado de cada locutor — resolve de graça o
# problema que no acervo local me obrigou a inferir gênero pela acústica (e que
# tinha posto voz de mulher no `pai`). E por vir de audiolivro, é fala LIDA, com
# projeção e sem ruído de casa: o registro certo para narração.
def _mls_generos(raiz):
    """{locutor: 'male'|'female'} a partir do metainfo.txt, se existir."""
    caminho = os.path.join(raiz, "metainfo.txt")
    if not os.path.exists(caminho):
        return {}
    generos = {}
    with open(caminho, encoding="utf-8") as f:
        for linha in f:
            partes = [p.strip() for p in linha.split("|")]
            if len(partes) < 2 or not partes[0].isdigit():
                continue
            g = partes[1].upper()
            generos[partes[0]] = ("male" if g.startswith("M") else
                                  "female" if g.startswith("F") else None)
    return generos


def eh_mls(raiz):
    return any(os.path.isdir(os.path.join(raiz, p, "audio"))
               for p in ("dev", "test", "train"))


def agrupar_mls(raiz, particoes=("dev", "test", "train"), minimo_clipes=2):
    """{locutor: [(caminho, frase), ...]} varrendo as partições do MLS.

    `dev` e `test` vêm antes de propósito: são bem menores, então dá para
    montar o banco de vozes sem varrer as dezenas de milhares de arquivos do
    `train` — e para referência de clone bastam alguns segundos por locutor."""
    por_locutor = collections.defaultdict(list)
    for part in particoes:
        base_part = os.path.join(raiz, part)
        trans = os.path.join(base_part, "transcripts.txt")
        pasta_audio = os.path.join(base_part, "audio")
        if not (os.path.exists(trans) and os.path.isdir(pasta_audio)):
            continue
        with open(trans, encoding="utf-8") as f:
            for linha in f:
                if "\t" not in linha:
                    continue
                _id, texto = linha.split("\t", 1)
                _id = _id.strip()
                pedacos = _id.split("_")
                if len(pedacos) < 3:
                    continue
                locutor, livro = pedacos[0], pedacos[1]
                for ext in (".flac", ".opus", ".wav"):
                    cam = os.path.join(pasta_audio, locutor, livro, _id + ext)
                    if os.path.exists(cam):
                        por_locutor[locutor].append((cam, texto.strip()))
                        break
    return {k: v for k, v in por_locutor.items() if len(v) >= minimo_clipes}


def _ler_tsv(caminho):
    """Common Voice usa TSV com colunas client_id, path, sentence, up_votes..."""
    with open(caminho, encoding="utf-8", newline="") as f:
        for linha in csv.DictReader(f, delimiter="\t"):
            yield linha


def _achar_tsv(pasta):
    """Prefere `validated.tsv` — são os clipes que a comunidade já conferiu."""
    for nome in ("validated.tsv", "train.tsv", "other.tsv"):
        p = os.path.join(pasta, nome)
        if os.path.exists(p):
            return p
    achados = [p for p in os.listdir(pasta) if p.endswith(".tsv")]
    return os.path.join(pasta, achados[0]) if achados else None


def _pasta_clipes(pasta):
    for nome in ("clips", "audio", "wav"):
        p = os.path.join(pasta, nome)
        if os.path.isdir(p):
            return p
    return pasta


def agrupar_falantes(pasta, minimo_clipes=3):
    """{client_id: [(caminho, frase), ...]} — só quem tem clipes suficientes
    para emendar até a duração alvo."""
    tsv = _achar_tsv(pasta)
    if not tsv:
        raise SystemExit(f"Nenhum .tsv encontrado em {pasta}")
    clipes = _pasta_clipes(pasta)
    por_falante = collections.defaultdict(list)
    for linha in _ler_tsv(tsv):
        cid = linha.get("client_id") or linha.get("speaker_id")
        arq = linha.get("path") or linha.get("audio")
        if not (cid and arq):
            continue
        # descarta o que a comunidade marcou como ruim
        try:
            if int(linha.get("down_votes") or 0) > 0:
                continue
        except ValueError:
            pass
        por_falante[cid].append((os.path.join(clipes, arq),
                                 (linha.get("sentence") or "").strip()))
    return {k: v for k, v in por_falante.items() if len(v) >= minimo_clipes}


def montar_falante(clipes, sr_alvo=24000):
    """Emenda clipes do mesmo falante até ~SEG_ALVO. Devolve (audio, texto)."""
    import librosa
    partes, frases, total = [], [], 0.0
    silencio = np.zeros(int(0.25 * sr_alvo), dtype=np.float32)
    for caminho, frase in clipes:
        if total >= SEG_ALVO:
            break
        try:
            y, _ = librosa.load(caminho, sr=sr_alvo, mono=True)
        except Exception:
            continue
        y, _ = librosa.effects.trim(y, top_db=30)
        if len(y) < int(0.8 * sr_alvo):
            continue
        partes.append(y.astype(np.float32))
        partes.append(silencio)
        frases.append(frase.rstrip(" .") + ".")
        total += len(y) / sr_alvo
    if total < SEG_MIN:
        return None, None
    audio = np.concatenate(partes)
    pico = float(np.max(np.abs(audio))) or 1.0
    return (audio / pico * 0.95).astype(np.float32), " ".join(frases)


def avaliar(audio, sr):
    """(ok, medidas). O corpus é caseiro: a triagem é o trabalho principal."""
    import librosa
    a = np.asarray(audio, dtype=float)
    f, vf, _ = librosa.pyin(a, fmin=60, fmax=450, sr=sr, frame_length=2048)
    v = f[~np.isnan(f)]
    m = {
        "f0": float(np.median(v)) if len(v) else 0.0,
        "vozeado": float(np.mean(vf)),
        "rms": float(np.sqrt((a ** 2).mean())),
        "planura": float(np.mean(librosa.feature.spectral_flatness(
            y=a.astype(np.float32)))),
        "dur": len(a) / sr,
    }
    ok = (m["vozeado"] >= MIN_VOZEADO and m["rms"] >= MIN_RMS
          and m["planura"] <= MAX_PLANURA and m["f0"] > 0)
    return ok, m


def importar(pasta, limite=200, verbose=True):
    os.makedirs(DESTINO, exist_ok=True)
    mls = eh_mls(pasta)
    if mls:
        falantes = agrupar_mls(pasta)
        generos = _mls_generos(pasta)
        prefixo = "mls"
        if verbose:
            print(f"Formato MLS · {len(generos)} locutor(es) com gênero "
                  f"declarado no metainfo.txt")
    else:
        falantes = agrupar_falantes(pasta)
        generos = {}
        prefixo = "cv"
    if verbose:
        print(f"{len(falantes)} falante(s) com clipes suficientes.")
    aceitos = rejeitados = 0
    for i, (cid, clipes) in enumerate(falantes.items()):
        if aceitos >= limite:
            break
        audio, texto = montar_falante(clipes)
        if audio is None:
            rejeitados += 1
            continue
        ok, m = avaliar(audio, 24000)
        if not ok:
            rejeitados += 1
            continue
        # O gênero entra no NOME do arquivo ("mls_m_1234"): é assim que
        # `casar_vozes.genero_do_arquivo` o lê, sem precisar adivinhar pela
        # acústica — que foi o que pôs voz de mulher no `pai`.
        g = generos.get(cid)
        marca = f"_{g[0]}_" if g else "_"
        nome = f"{prefixo}{marca}{cid[:12]}"
        sf.write(os.path.join(DESTINO, nome + ".wav"), audio, 24000)
        with open(os.path.join(DESTINO, nome + ".txt"), "w",
                  encoding="utf-8") as f:
            f.write(texto)
        aceitos += 1
        if verbose and aceitos % 25 == 0:
            print(f"  {aceitos} aceitos, {rejeitados} descartados...")
    if verbose:
        print(f"\n{aceitos} falante(s) em {DESTINO} · {rejeitados} descartado(s)")
        print("Acrescente essa pasta em casar_vozes.PASTAS e rode "
              "`--inventario --forcar`.")
    return aceitos


def main():
    ap = argparse.ArgumentParser(description="Importa corpus externo de vozes")
    ap.add_argument("--pasta", required=True, help="raiz do corpus baixado")
    ap.add_argument("--limite", type=int, default=200)
    a = ap.parse_args()
    base.console_utf8()
    importar(a.pasta, a.limite)


if __name__ == "__main__":
    main()
