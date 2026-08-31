# -*- coding: utf-8 -*-
"""Armazenamento do acervo de histórias.

Formato: metadados em `acervo.jsonl` (uma linha JSON por história) e o texto em
arquivos separados. NÃO é CSV de propósito: histórias são feitas de vírgula,
aspas, travessão e quebra de linha — os caracteres que o CSV precisa escapar —
e `motor_v2._beats_historia()` depende de aspas e quebras de linha chegarem
intactas. Um round-trip por CSV mal configurado corrompe a segmentação em
silêncio, que é o pior tipo de bug.

    acervo.jsonl        índice: id, titulo, fonte, url, licenca, autor, status...
    brutos/<id>.txt     como veio da fonte, sem tocar
    textos/<id>.txt     limpo (sempre regerável a partir do bruto)
    roteiros/<id>.json  saída da fase 1 (motor_v2.roteirizar_historia)
    audios/<id>.wav

O bruto é sagrado: coleta-se uma vez e limpa-se cinquenta. O limpador vai ser
reajustado várias vezes (capitular, nota de rodapé, cabeçalho de digitalização)
e nada disso pode depender de bater na rede de novo.
"""
import hashlib
import json
import os
import re
import sys
import unicodedata

DIR       = os.path.dirname(os.path.abspath(__file__))
INDICE    = os.path.join(DIR, "acervo.jsonl")
BRUTOS    = os.path.join(DIR, "brutos")
TEXTOS    = os.path.join(DIR, "textos")
ADAPTADOS = os.path.join(DIR, "adaptados")
ROTEIROS  = os.path.join(DIR, "roteiros")
AUDIOS    = os.path.join(DIR, "audios")
# Uma subpasta por personagem, para guardar as referências de voz dele.
VOZES_PERS = os.path.join(DIR, "vozes_personagens")
MAPA_VOZES = os.path.join(DIR, "vozes_personagens", "mapa.json")

# Ciclo de vida de uma história. Cada passo do pipeline só olha o status que
# sabe tratar, então um lote interrompido retoma exatamente de onde parou.
STATUS = ("novo", "limpo", "classificado", "adaptado", "roteirizado",
          "aprovado", "sintetizado", "descartado")


def console_utf8():
    """Põe a saída do terminal em UTF-8.

    O console do Windows abre em cp1252, que não tem "→" nem "·" — imprimir um
    deles derruba o processo com UnicodeEncodeError no meio de um lote longo. E
    mesmo os acentos, que o cp1252 tem, saem trocados sem isto."""
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass


def garantir_pastas():
    for d in (BRUTOS, TEXTOS, ADAPTADOS, ROTEIROS, AUDIOS, VOZES_PERS):
        os.makedirs(d, exist_ok=True)


def slug(titulo):
    """Título → identificador de arquivo: sem acento, minúsculo, com hífens.
    Legível de propósito — dá para achar a história no disco sem consultar o
    índice."""
    s = unicodedata.normalize("NFKD", titulo or "").encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return (s or "sem-titulo")[:80]


def hash_texto(txt):
    """Impressão digital do conteúdo. Serve para detectar que a fonte mudou (ou
    que o texto foi editado à mão) sem comparar arquivos inteiros."""
    return hashlib.sha256((txt or "").encode("utf-8")).hexdigest()[:16]


def carregar_indice():
    """Lê o acervo.jsonl inteiro → {id: registro}. Linha corrompida é ignorada
    em vez de derrubar o processo: um lote de horas não pode morrer por causa
    de uma escrita interrompida."""
    idx = {}
    if not os.path.exists(INDICE):
        return idx
    with open(INDICE, encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            try:
                reg = json.loads(linha)
            except json.JSONDecodeError:
                continue
            if reg.get("id"):
                idx[reg["id"]] = reg
    return idx


def gravar_indice(idx):
    """Regrava o índice inteiro, ordenado por id. Escreve num temporário e só
    então substitui — assim um Ctrl+C no meio não deixa o índice pela metade."""
    tmp = INDICE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for _id in sorted(idx):
            f.write(json.dumps(idx[_id], ensure_ascii=False) + "\n")
    os.replace(tmp, INDICE)


def caminho(sub, _id, ext):
    return os.path.join(sub, f"{_id}.{ext}")


def ler_bruto(_id):
    p = caminho(BRUTOS, _id, "txt")
    return open(p, encoding="utf-8").read() if os.path.exists(p) else None


def ler_texto(_id):
    p = caminho(TEXTOS, _id, "txt")
    return open(p, encoding="utf-8").read() if os.path.exists(p) else None


def escrever(sub, _id, ext, conteudo):
    garantir_pastas()
    p = caminho(sub, _id, ext)
    with open(p, "w", encoding="utf-8") as f:
        f.write(conteudo)
    return p
