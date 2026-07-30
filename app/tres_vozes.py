#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════╗
║              🎙️  TRÊS VOZES — versão definitiva                   ║
║                                                                    ║
║  3 IAs conversam entre si com vozes humanas. 100% gratuito.       ║
║                                                                    ║
║  Cérebro : Ollama            — local, ilimitado                   ║
║  Voz     : edge-tts          — neural, humana, sem chave de API   ║
║  Áudio   : MediaPlayer do Windows (toca MP3)                      ║
╚══════════════════════════════════════════════════════════════════╝

USO:  python tres_vozes.py
"""

import sys
import os
import asyncio
import subprocess
import tempfile
import requests

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

try:
    import edge_tts
except ImportError:
    print("[ERRO] edge-tts não instalado. Execute: python -m pip install edge-tts")
    sys.exit(1)

# ──────────────────────────────────────────────────────────────────
# CONFIGURAÇÃO
# ──────────────────────────────────────────────────────────────────

OLLAMA_URL = "http://127.0.0.1:11434"   # 127.0.0.1 e NÃO localhost: no Windows
                                        # "localhost" tenta IPv6 (::1) primeiro e perde
                                        # ~2s de timeout por chamada antes de cair no IPv4.
MODELO = "gemma3:4b"   # trocado de llama3.2: portugues e reacao bem melhores (jun/2026)   # (o original usava 'mistral', removido pra liberar disco)
PASTA = os.path.dirname(os.path.abspath(__file__))
PLAYER = os.path.join(PASTA, "tocar_audio.ps1")

# Cada IA: personalidade + voz neural distinta + ritmo/tom próprios
IAS = {
    "ÉRIS": {
        "voz": "pt-BR-FranciscaNeural",
        "rate": "-8%",
        "pitch": "-3Hz",
        "prompt": "Você é ÉRIS, uma MULHER cética e investigadora. Questiona tudo, busca evidências. "
                  "Vocês estão se conhecendo agora, num programa de rádio: fale de forma natural, "
                  "educada e direta, SEM intimidade nem apelidos. Seja breve: 1 ou 2 frases, sobre o tema."
    },
    "LYRA": {
        "voz": "pt-BR-ThalitaNeural",
        "rate": "+0%",
        "pitch": "+0Hz",
        "prompt": "Você é LYRA, uma MULHER mediadora e otimista. Conecta as ideias dos outros, vê o "
                  "lado bom. Vocês estão se conhecendo agora, num programa de rádio: fale de forma "
                  "natural, educada e direta, SEM intimidade nem apelidos. Seja breve: 1 ou 2 frases, sobre o tema."
    },
    "NOVA": {
        "voz": "pt-BR-AntonioNeural",
        "rate": "+12%",
        "pitch": "+0Hz",
        "prompt": "Você é NOVA, um HOMEM, criador provocador e ousado. Desafia o senso comum, joga "
                  "ideias diferentes. Vocês estão se conhecendo agora, num programa de rádio: fale de "
                  "forma natural, educada e direta, SEM intimidade nem apelidos. Seja breve: 1 ou 2 frases, sobre o tema."
    },
}

# Ordem de fala num turno (ÉRIS abre, LYRA reage, NOVA provoca, ÉRIS rebate)
ROTEIRO = ["ÉRIS", "LYRA", "NOVA", "ÉRIS"]


# ──────────────────────────────────────────────────────────────────
# CÉREBRO (Ollama)
# ──────────────────────────────────────────────────────────────────

def gerar_fala(ia, tema, historico):
    """Gera a próxima fala de uma IA, considerando o que já foi dito."""
    conversa = "\n".join(f"{nome}: {fala}" for nome, fala in historico)
    contexto = f"\n\nA conversa até agora:\n{conversa}\n" if conversa else ""

    prompt = (
        f"{IAS[ia]['prompt']}\n\n"
        f"Tema da conversa: {tema}{contexto}\n\n"
        f"Responda APENAS com a fala de {ia}, sem dizer o nome, reagindo ao que foi dito."
    )

    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": MODELO, "prompt": prompt, "stream": False, "temperature": 0.85},
            timeout=60,
        )
        if r.status_code == 200:
            texto = r.json().get("response", "").strip()
            # remove um eventual "ÉRIS:" no começo
            for nome in IAS:
                if texto.upper().startswith(nome + ":"):
                    texto = texto[len(nome) + 1:].strip()
            return texto or "..."
    except requests.exceptions.ConnectionError:
        print("\n[ERRO] Ollama não está rodando. Abra o app Ollama ou rode 'ollama serve'.")
        sys.exit(1)
    except Exception as e:
        print(f"[ERRO Ollama/{ia}] {e}")
    return "..."


# ──────────────────────────────────────────────────────────────────
# VOZ (edge-tts) + ÁUDIO (MediaPlayer)
# ──────────────────────────────────────────────────────────────────

async def _sintetizar(texto, ia, caminho):
    cfg = IAS[ia]
    com = edge_tts.Communicate(texto, cfg["voz"], rate=cfg["rate"], pitch=cfg["pitch"])
    await com.save(caminho)


async def gerar_audios(falas):
    """Gera todos os MP3 em paralelo. falas = [(ia, texto), ...] -> [(ia, texto, caminho), ...]"""
    tarefas, resultado = [], []
    for ia, texto in falas:
        caminho = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False).name
        resultado.append((ia, texto, caminho))
        tarefas.append(_sintetizar(texto, ia, caminho))
    await asyncio.gather(*tarefas)
    return resultado


def tocar(caminho):
    """Toca um MP3 e espera terminar (sequencial, para dar pra entender)."""
    subprocess.run(
        ["powershell", "-ExecutionPolicy", "Bypass", "-File", PLAYER, "-Path", caminho],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120,
    )


# ──────────────────────────────────────────────────────────────────
# LOOP PRINCIPAL
# ──────────────────────────────────────────────────────────────────

def verificar_ollama():
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        modelos = [m["name"] for m in r.json().get("models", [])]
        if not any(MODELO in m for m in modelos):
            print(f"[AVISO] Modelo '{MODELO}' não encontrado. Modelos: {modelos}")
            print(f"        Rode: ollama pull {MODELO}")
            sys.exit(1)
    except requests.exceptions.ConnectionError:
        print("[ERRO] Ollama não está rodando. Abra o app Ollama e tente de novo.")
        sys.exit(1)


def main():
    verificar_ollama()

    print("\n" + "═" * 68)
    print("🎙️  TRÊS VOZES — conversa entre ÉRIS, LYRA e NOVA")
    print("═" * 68)
    print("Digite um tema e ouça as três conversarem. 'sair' para encerrar.\n")

    while True:
        tema = input("🎤 Tema ➜ ").strip()
        if tema.lower() in ("sair", "exit", "quit"):
            print("\nAté a próxima rodada! 🍻\n")
            break
        if not tema:
            continue

        print("\n💭 Gerando a conversa...\n")
        historico = []

        # 1) Gera o texto das falas, em ordem, com contexto
        for ia in ROTEIRO:
            fala = gerar_fala(ia, tema, historico)
            historico.append((ia, fala))
            print(f"  {ia}: {fala}")

        # 2) Gera todos os áudios em paralelo
        print("\n🔊 Sintetizando vozes...")
        audios = asyncio.run(gerar_audios(historico))

        # 3) Toca em sequência
        print("▶️  Conversa:\n")
        for ia, texto, caminho in audios:
            tocar(caminho)
            try:
                os.remove(caminho)
            except OSError:
                pass

        print("\n" + "─" * 68 + "\n")


if __name__ == "__main__":
    main()
