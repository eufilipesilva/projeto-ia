# -*- coding: utf-8 -*-
"""Gerador de Paródia — Fase 1 (letra com métrica).

Pega uma música, transcreve a letra original com o tempo de cada verso
(faster-whisper), mede a métrica (nº de sílabas por verso, via pyphen pt-BR) e
pede pro Gemma reescrever a letra sobre um tema novo RESPEITANDO essa métrica,
com um verificador que reconta as sílabas e manda o Gemma corrigir os versos
que ficaram fora.

Isto é só a parte de TEXTO. Fazer o cantor cantar a letra nova na melodia
antiga (síntese de canto / SVS) é uma fase futura — ver memória do projeto
"canto-lab-voz-musica" e a discussão da máquina de paródias.

Rodar teste:
    python parodia.py <musica.mp3> "tema da paródia"
"""
import os, re, sys

PASTA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PASTA)

_WHISPER = None
_DIC = None

# Tolerância de sílabas por verso: a contagem gramatical (pyphen) não é igual à
# contagem poética (que tem elisão/sinalefa entre vogais), então exigir bater
# exato seria irreal. ±1 sílaba soa bem quando cantado.
TOLERANCIA_SILABAS = 1


def _carregar_whisper(tamanho="small"):
    """faster-whisper em CPU int8 (não disputa a VRAM com Demucs/OmniVoice; o
    modelo 'small' transcreve uma música inteira em ~1x o tempo real)."""
    global _WHISPER
    if _WHISPER is None:
        from faster_whisper import WhisperModel
        _WHISPER = WhisperModel(tamanho, device="cpu", compute_type="int8")
    return _WHISPER


def _dic():
    global _DIC
    if _DIC is None:
        import pyphen
        _DIC = pyphen.Pyphen(lang="pt_BR")
    return _DIC


def contar_silabas(linha):
    """Nº de sílabas gramaticais de um verso (soma por palavra via pyphen)."""
    d = _dic()
    total = 0
    for p in re.findall(r"[a-zA-Zà-úÀ-Ú]+", linha.lower()):
        total += d.inserted(p).count("-") + 1
    return total


# ── Rima ────────────────────────────────────────────────────────────────────
# Numa paródia, cada verso novo deve terminar com o MESMO som do verso original
# (rima) — assim o esquema de rimas cai nos mesmos lugares e soa familiar.
_VOGAIS = set("aeiou")
_TONICAS_ACENTUADAS = set("áéíóúâêôàãõ")


def _sem_acento(s):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def _chave_rima(palavra):
    """Terminação rímica de uma palavra: da vogal tônica até o fim, sem acento.
    A tônica vem do acento gráfico, ou da regra padrão do português (oxítona vs
    paroxítona pela terminação). Duas palavras rimam se têm a mesma chave."""
    p = re.sub(r"[^a-zà-ÿ]", "", palavra.lower())
    if not p:
        return ""
    idxv = [i for i, c in enumerate(p) if _sem_acento(c) in _VOGAIS]
    if not idxv:
        return _sem_acento(p)
    ton = None
    for i, c in enumerate(p):
        if c in _TONICAS_ACENTUADAS:
            ton = i
    if ton is None:
        term1, term2 = p[-1], p[-2:]
        paroxitona = (term1 in "ao" or term1 == "e"
                      or term2 in ("as", "es", "os", "am", "em", "ens", "ans")
                      or (term1 in "sm" and len(p) > 1 and p[-2] in "aeo"))
        ton = (idxv[-2] if (paroxitona and len(idxv) >= 2) else idxv[-1])
    return _sem_acento(p[ton:])


def _ultima_palavra(verso):
    palavras = re.findall(r"[a-zA-Zà-úÀ-Ú]+", verso)
    return palavras[-1] if palavras else ""


def rimam(verso_a, verso_b):
    """True se os dois versos terminam com o mesmo som (rima)."""
    ka, kb = _chave_rima(_ultima_palavra(verso_a)), _chave_rima(_ultima_palavra(verso_b))
    return bool(ka) and ka == kb


# Quebra de versos: o Whisper devolve FRASES longas (às vezes 3-4 linhas
# musicais juntas), inúteis pra métrica. Reparte em versos curtos usando as
# pausas entre palavras e um teto de sílabas — assim cada "verso" vira uma
# linha cantável de verdade, com uma contagem de sílabas que o Gemma consegue
# respeitar.
PAUSA_VERSO = 0.40      # segundos de silêncio entre palavras que fecham um verso
MAX_SILABAS_VERSO = 11  # teto de sílabas antes de forçar a quebra


def _palavras_para_versos(palavras):
    versos, atual = [], []
    for i, w in enumerate(palavras):
        pausa = (w.start - palavras[i - 1].end) if atual else 0.0
        texto_atual = "".join(x.word for x in atual)
        if atual and (pausa > PAUSA_VERSO or contar_silabas(texto_atual) >= MAX_SILABAS_VERSO):
            versos.append(atual); atual = []
        atual.append(w)
    if atual:
        versos.append(atual)
    saida = []
    for grupo in versos:
        texto = "".join(x.word for x in grupo).strip()
        if texto:
            saida.append({"texto": texto, "inicio": round(grupo[0].start, 2),
                          "fim": round(grupo[-1].end, 2), "silabas": contar_silabas(texto)})
    return saida


def transcrever_letra(vocal_path, idioma="pt", progresso=lambda *a: None):
    """Transcreve o vocal isolado em versos CURTOS com tempo, quebrados por
    pausa. Retorna lista de {texto, inicio, fim, silabas}. Use o VOCAL já
    separado (Demucs), não a música inteira — o Whisper erra menos sem o
    instrumental por cima."""
    progresso(0.1, "Transcrevendo a letra (Whisper)...")
    model = _carregar_whisper()
    segmentos, _info = model.transcribe(
        vocal_path, language=idioma, word_timestamps=True, vad_filter=True)
    palavras = []
    for seg in segmentos:
        for w in (seg.words or []):
            if w.word.strip():
                palavras.append(w)
    return _palavras_para_versos(palavras)


def _bloco_metrico(versos):
    """Formata os versos originais numerados com a contagem de sílabas E a
    palavra final (rima a manter), pra servir de molde no prompt do Gemma."""
    linhas = []
    for i, v in enumerate(versos, 1):
        rima = _ultima_palavra(v["texto"])
        linhas.append(f'{i:2d}. ({v["silabas"]} sílabas, rima com "{rima}") {v["texto"]}')
    return "\n".join(linhas)


def _limpar_verso(s):
    """Tira o lixo de formatação que o Gemma gruda nos versos: numeração,
    marcadores, aspas e o sufixo '(N sílabas)' — que, se ficasse, seria contado
    como se fizesse parte da letra."""
    s = s.strip()
    s = re.sub(r"^\s*\d+[\.\)\-:]\s*", "", s)                    # "3. " / "3) "
    s = re.sub(r"^[\-\*•]\s*", "", s)                             # marcadores
    s = re.sub(r"\s*[\(\[]\s*\d+\s*s[íi]labas?\s*[\)\]]\s*$", "", s, flags=re.I)  # (9 sílabas)
    s = s.strip().strip('"“”\'`').strip()                        # aspas
    return s


def _extrair_versos(texto_llm, n):
    """Pega as `n` primeiras linhas não-vazias da resposta do Gemma, já
    limpas do lixo de formatação."""
    linhas = []
    for ln in texto_llm.splitlines():
        limpo = _limpar_verso(ln)
        if limpo:
            linhas.append(limpo)
    return linhas[:n]


def gerar_parodia(versos, tema, tentativas=3, progresso=lambda *a: None):
    """Gera a letra da paródia sobre `tema`, respeitando a métrica dos `versos`
    originais. Faz até `tentativas` passes: gera, reconta as sílabas de cada
    verso e, se algum estourar a TOLERANCIA, pede ao Gemma pra reescrever só
    aqueles versos. Retorna {versos: [...], erros: [...], relatorio: str}."""
    import motor_v2
    alvos = [v["silabas"] for v in versos]
    n = len(versos)
    molde = _bloco_metrico(versos)

    progresso(0.4, "Gemma escrevendo a paródia...")
    prompt = (
        "Você é um letrista de paródias em português do Brasil. Reescreva a "
        f"letra abaixo com um tema novo: \"{tema}\".\n\n"
        "REGRAS IMPORTANTES:\n"
        "- Mantenha EXATAMENTE o mesmo número de versos.\n"
        "- Cada verso novo deve ter o MESMO número de sílabas indicado, pra "
        "encaixar na melodia.\n"
        "- Cada verso deve TERMINAR rimando com a palavra indicada (mesmo som "
        "final), pra manter as rimas da música.\n"
        "- Escreva SÓ os versos novos, um por linha, sem numerar, sem aspas, "
        "sem comentários e SEM escrever a contagem de sílabas.\n\n"
        f"LETRA ORIGINAL (sílabas e rima de cada verso):\n{molde}\n\n"
        "PARÓDIA (só os versos, um por linha):"
    )
    resposta = motor_v2._gemma(prompt, num_predict=600, num_ctx=4096, temperature=0.9)
    novos = _extrair_versos(resposta, n)

    def _problemas(i):
        """Lista o que está errado no verso i: métrica e/ou rima."""
        probs = []
        s = contar_silabas(novos[i])
        if abs(s - alvos[i]) > TOLERANCIA_SILABAS:
            probs.append(("silabas", s))
        if not rimam(novos[i], versos[i]["texto"]):
            probs.append(("rima", None))
        return probs

    for tent in range(tentativas):
        while len(novos) < n:            # completa se veio menos versos
            novos.append("")
        fora = [i for i in range(n) if _problemas(i)]
        if not fora or tent == tentativas - 1:
            break
        progresso(0.5 + 0.13 * tent, f"Ajustando métrica e rima ({len(fora)} versos)...")
        pedidos = []
        for i in fora:
            partes = []
            for tipo, val in _problemas(i):
                if tipo == "silabas":
                    partes.append(f"tem {val} sílabas, precisa de {alvos[i]} (±{TOLERANCIA_SILABAS})")
                else:
                    partes.append(f'precisa RIMAR com "{_ultima_palavra(versos[i]["texto"])}"')
            pedidos.append(f'- Verso {i+1}: "{novos[i]}" — ' + "; ".join(partes) +
                           f'. Reescreva mantendo o tema "{tema}".')
        prompt_fix = (
            "Corrija SÓ os versos abaixo (português do Brasil), ajustando sílabas "
            "e rima como pedido, mantendo o tema. Responda no formato "
            "'N: verso corrigido', um por linha.\n\n" + "\n".join(pedidos))
        fix = motor_v2._gemma(prompt_fix, num_predict=500, num_ctx=4096, temperature=0.9)
        for ln in fix.splitlines():
            m = re.match(r"\s*(\d+)\s*[:\.\)]\s*(.+)", ln.strip())
            if m:
                idx = int(m.group(1)) - 1
                if 0 <= idx < n:
                    novos[idx] = _limpar_verso(m.group(2))

    motor_v2.descarregar_gemma()

    erros_finais, linhas_rel = [], []
    for i in range(n):
        s = contar_silabas(novos[i])
        met_ok = abs(s - alvos[i]) <= TOLERANCIA_SILABAS
        rim_ok = rimam(novos[i], versos[i]["texto"])
        if not (met_ok and rim_ok):
            erros_finais.append(i)
        marca = "✓" if (met_ok and rim_ok) else "✗"
        tags = ("S" if met_ok else "s") + ("R" if rim_ok else "r")  # maiúscula = ok
        linhas_rel.append(f'{marca} [{tags}] ({s}/{alvos[i]} síl.) {novos[i]}')
    progresso(1.0, "Paródia pronta!")
    return {"versos": novos, "erros": erros_finais, "relatorio": "\n".join(linhas_rel)}


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # console Windows é cp1252
    except Exception:
        pass
    if len(sys.argv) < 3:
        print('Uso: python parodia.py <musica.mp3> "tema da paródia"')
        sys.exit(1)
    musica, tema = sys.argv[1], sys.argv[2]

    def prog(p, msg): print(f"[{p*100:4.0f}%] {msg}", flush=True)

    import canto_musica
    print("Separando vocal (Demucs)...", flush=True)
    vocal_path, inst_path, _y, _sr = canto_musica.separar_vocal_instrumental(musica, prog)
    try:
        versos = transcrever_letra(vocal_path, progresso=prog)
        print(f"\n=== LETRA ORIGINAL ({len(versos)} versos) ===")
        print(_bloco_metrico(versos))
        print(f"\n=== PARÓDIA: \"{tema}\" ===")
        res = gerar_parodia(versos, tema, progresso=prog)
        print(res["relatorio"])
        print(f"\nVersos fora da métrica: {len(res['erros'])}/{len(versos)}")
    finally:
        canto_musica._limpar(vocal_path, inst_path)
