#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════╗
║              🎙️  TRÊS VOZES — versão definitiva                   ║
║                                                                    ║
║  3 IAs conversam num bar, se interrompendo e sentindo de verdade: ║
║  sarcasmo, tristeza, surpresa, carinho, reflexão... 100% grátis.  ║
║                                                                    ║
║  Cérebro : Ollama (mistral)  — local, ilimitado                   ║
║  Voz     : edge-tts          — neural, com emoção via ritmo/tom   ║
║  Áudio   : MediaPlayer do Windows, com falas sobrepostas          ║
╚══════════════════════════════════════════════════════════════════╝

USO:  python tres_vozes.py
"""

import sys
import os
import re
import random
import asyncio
import threading
import queue
import subprocess
import tempfile
import unicodedata
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
MODELO = "gemma3:4b"   # trocado de llama3.2: portugues e reacao bem melhores (jun/2026)
PASTA = os.path.dirname(os.path.abspath(__file__))
PLAYER_DIALOGO = os.path.join(PASTA, "tocar_dialogo.ps1")
PLAYER_FUNDO = os.path.join(PASTA, "tocar_fundo.ps1")
ARQ_FUNDO = os.path.join(PASTA, "fundo_bar.wav")

MIN_FALAS = 12          # antes disso, nem checa se a conversa acabou
MAX_FALAS = 24          # teto de segurança (conversa longa)
PROB_INTERRUPCAO = 0.6  # programa de zoeira: todo mundo se atropela
VOLUME_FUNDO = "0.12"

# Personagens de rádio-humor (estilo Pânico)
IAS = {
    "ÉRIS": {
        "voz": "pt-BR-FranciscaNeural", "rate": 5, "pitch": 0,
        "persona": "Você é ÉRIS, uma MULHER: a apresentadora ácida e debochada do programa. Comanda "
                   "a pauta, mete sarcasmo no assunto e adora um escândalo — mas tem coração.",
        "jeito": "Voz firme e debochada, fala rápido e ri da própria maldade. Bordões: "
                 "'Ô loco!', 'Gente, eu não acredito!', 'Para tudo!'."
    },
    "LYRA": {
        "voz": "pt-BR-ThalitaNeural", "rate": 6, "pitch": 2,
        "persona": "Você é LYRA, uma MULHER: a zoeira escrachada do programa, gargalhada fácil e "
                   "piada na ponta da língua. Faz humor de tudo e não leva nada a sério.",
        "jeito": "Risada alta e contagiante, comenta tudo rindo. Bordões: 'kkkk para com "
                 "isso!', 'Gente, eu não aguento!', 'Aí já é demais!'."
    },
    "NOVA": {
        "voz": "pt-BR-AntonioNeural", "rate": -6, "pitch": -2,
        "persona": "Você é NOVA, um HOMEM: o malandro galanteador e contador de vantagem, voz mansa "
                   "de quem se acha o bom. Joga charme, se gaba e sempre tem uma história mirabolante.",
        "jeito": "Voz macia e cheia de si, arrasta as palavras todo charmoso. Bordões: 'Calma, "
                 "minha filha...', 'Deixa eu te falar uma coisa...', 'Ó, eu já fiz isso mil vezes'."
    },
}

# Emoção -> deltas de (velocidade%, tom Hz, volume%) somados à voz-base.
# Valores mais fortes = emoções mais vivas e contrastadas.
EMOCOES = {
    "neutro":         (0, 0, 0),
    "alegria":        (22, 14, 4),
    "tristeza":       (-26, -12, -18),
    "sarcasmo":       (-11, 7, 0),
    "confianca":      (7, -2, 9),
    "incisivo":       (14, -6, 15),
    "surpresa":       (26, 17, 7),
    "preocupacao":    (-15, -6, -9),
    "carinho":        (-14, 6, -12),
    "reflexao":       (-19, -4, -12),
    "questionamento": (-4, 10, 0),
    "concordancia":   (-3, 6, 2),
    "irritacao":      (16, -7, 16),
}
LISTA_EMOCOES = ("alegria, tristeza, sarcasmo, confiança, incisivo, surpresa, preocupação, "
                 "carinho, reflexão, questionamento, concordância, irritação, neutro")


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


# ──────────────────────────────────────────────────────────────────
# CÉREBRO (Ollama)
# ──────────────────────────────────────────────────────────────────

def _ollama(prompt: str, temperatura: float = 0.9, max_tokens: int = 80) -> str:
    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": MODELO, "prompt": prompt, "stream": False,
                  "keep_alive": "10m",   # mantém o modelo quente entre as falas
                  "options": {"temperature": temperatura, "num_predict": max_tokens}},
            timeout=60,
        )
        if r.status_code == 200:
            return r.json().get("response", "").strip()
    except requests.exceptions.ConnectionError:
        print("\n[ERRO] Ollama parou de responder. Abra o app Ollama e tente de novo.")
        sys.exit(1)
    except Exception as e:
        print(f"[ERRO Ollama] {e}")
    return ""


_RE_REMOVE_EMOCAO = re.compile(r'emo[çc][aã]o\s*[:=]\s*[a-zA-ZçÇãÃáÁéÉêÊíÍóÓúÚ]+', re.IGNORECASE)
# rótulos que o modelo às vezes coloca no começo da fala
_RE_ROTULO_INICIAL = re.compile(
    r'^\s*(frase\s*curta|frase|resposta|réplica|replica|fala|emo[çc][aã]o)\s*[:=]\s*',
    re.IGNORECASE)


_RE_ACOES = re.compile(r'\([^)]*\)|\[[^\]]*\]|\*[^*]*\*')   # (rindo), [pausa], *sorri*


def _limpar_fala(texto: str) -> str:
    """Remove rótulos, rubricas de ação (rindo), nome inicial e aspas — só a fala falada."""
    t = _RE_ACOES.sub(" ", texto)            # tira (rindo), (sorrindo), [pausa]...
    t = _RE_REMOVE_EMOCAO.sub("", t)
    t = " ".join(t.split())
    for _ in range(4):                       # tira rótulos iniciais empilhados
        novo = _RE_ROTULO_INICIAL.sub("", t).strip()
        if novo == t:
            break
        t = novo
    for nome in IAS:
        if t.upper().startswith(nome + ":"):
            t = t[len(nome) + 1:].strip()
    return t.strip().strip('"').strip()


# cada turno normal puxa um "movimento" diferente, pra conversa não ficar monótona
MOVIMENTOS = (
    "Solte uma piada ou um deboche na hora.",
    "Esculacha de leve uma das outras, na zoeira.",
    "Conte uma vantagem ou uma história mirabolante (pode inventar).",
    "Concorde rindo e exagere junto.",
    "Tire um sarro do que a outra acabou de dizer.",
    "Faça uma pergunta provocadora a ÉRIS, LYRA ou NOVA, pelo nome.",
    "Solte um bordão seu no meio da fala.",
    "Mude de assunto do nada com uma ideia doida.",
    "Defenda uma e ataque a outra, só pra ver a confusão.",
)

# quando esquenta, a próxima fala desarma na base da piada
ESFRIAR = (
    "Percebe que pegou pesado e disfarça com uma piada, fazendo as pazes.",
    "Dá uma de paz e amor, mas já solta outra alfinetada no fim.",
    "Concorda rindo só pra encerrar a discussão.",
)


def _instrucao(interrompe: bool, encerrando: bool, aquecido: bool = False) -> str:
    if interrompe:
        return ("Você CORTA na hora, atravessando quem falava. Solta uma reação rápida e "
                "debochada (poucas palavras) — uma zoeira, um 'peraí', um bordão ou um sarro.")
    if encerrando:
        return ("Fale ao vivo no programa, à vontade. Tá na hora de fechar o bloco: "
                "dá um arremate engraçado, no seu estilo.")
    if aquecido and random.random() < 0.6:
        return ("Fale ao vivo, à vontade. " + random.choice(ESFRIAR))
    return ("Fale ao vivo no programa de rádio-humor, no seu jeito e na zoeira, reagindo ao "
            "que acabou de ser dito. " + random.choice(MOVIMENTOS))


def gerar_fala(ia: str, tema: str, historico: list, interrompe: bool, encerrando: bool,
               aquecido: bool = False) -> str:
    """PASSO 1 — gera SÓ a fala. O prompt não menciona emoção: impossível vazar."""
    conversa = "\n".join(f"{nome}: {fala}" for nome, fala in historico[-8:])  # só as últimas
    contexto = f"\n\nNa mesa, até agora:\n{conversa}\n" if conversa else ""
    instrucao = _instrucao(interrompe, encerrando, aquecido)

    primeira = not historico
    abre = ("Você ABRE o programa: chama o tema na sua energia, sem citar ninguém (ninguém falou "
            "ainda).\n" if primeira else "")
    prompt = (
        f"{IAS[ia]['persona']}\nSeu jeito de falar: {IAS[ia]['jeito']}\n\n"
        "PROGRAMA DE RÁDIO-HUMOR ao vivo. Cada um traz a SUA energia cômica (o estilo descrito "
        "acima). Tom debochado, rápido e engraçado — humor brasileiro de rádio, fala de boteco, "
        "concreta, nada de filósofo. A graça vem do seu jeito e do TEMA, não de intimidade com os "
        "outros: vocês mal se conhecem, então a zoeira é com o ASSUNTO, sem apelido nem história "
        "em comum inventada.\n\n"
        "Exemplo só do TOM (pessoas quaisquer):\n"
        "A: Ô loco, isso aí é conversa pra boi dormir!\n"
        "B: kkkk eu não aguento, alguém segura essa!\n"
        "C: Calma, deixa eu te explicar como a coisa funciona de verdade...\n\n"
        f"Tema de hoje: {tema}{contexto}\n\n{abre}{instrucao}\n\n"
        "FIDELIDADE: comente só o que REALMENTE foi dito acima; não invente fala de ninguém nem "
        "intimidade que não existe. NÃO repita o que já foi dito. Traga piada nova SOBRE O TEMA. "
        "Não escreva rubricas como (rindo) — só a fala mesmo.\n\n"
        f"Escreva APENAS a fala de {ia}, no seu jeito e com seus bordões, em cima do TEMA "
        "(pode chamar alguém pelo nome). Português do Brasil natural e engraçado. Sem aspas, "
        "sem dizer o próprio nome."
    )
    fala = _limpar_fala(_ollama(prompt, max_tokens=140))
    if not fala:
        fala = _limpar_fala(_ollama(prompt, max_tokens=140)) or "..."
    return _aparar_frase(fala)


def _aparar_frase(fala: str) -> str:
    """Se a fala foi cortada no meio, apara no fim da última frase completa."""
    fala = fala.strip()
    if not fala or fala[-1] in ".!?…":
        return fala
    idx = max(fala.rfind("."), fala.rfind("!"), fala.rfind("?"), fala.rfind("…"))
    return fala[:idx + 1].strip() if idx >= 12 else fala


# pistas de cada emoção (texto normalizado, sem acento e minúsculo)
_LEXICO = {
    "alegria":      ["que bom", "adoro", "amei", "feliz", "otimo", "maravilh", "incrivel", "haha", "kkk", "rir"],
    "tristeza":     ["triste", "sozinh", "doi", " dor", "perda", "vazio", "cansad", "desist", "sinto falta", "magoa"],
    "carinho":      ["amiga", "juntas", "te amo", "abraco", "querida", "estou aqui", "calma", "cuida", "meu bem"],
    "preocupacao":  ["preocup", "cuidado", "perigo", "receio", "tenho medo", "sera que vai", "e se der errado"],
    "surpresa":     ["serio", "nossa", "uau", "espera", "como assim", "nao acredito", "jura", "ce ta brincando"],
    "irritacao":    ["chega", "basta", "para com", "absurdo", "que saco", "cansei", "me poupe", "pare de"],
    "incisivo":     ["nao e sobre", "e so isso", "ponto final", "escuta", "o fato e", "a verdade e", "simples assim"],
    "confianca":    ["com certeza", "tenho certeza", "sem duvida", "claro que", "garanto", "obviamente"],
    "concordancia": ["concordo", "verdade", "exato", "isso mesmo", "tambem acho", "pois e", "faz sentido"],
    "sarcasmo":     ["ah claro", "imagina", "sei...", "ah ta", "que otimo", "parabens", "ne?"],
    "reflexao":     ["talvez", "acho que", "no fundo", "penso que", "quem sabe", "as vezes", "sera"],
}


def detectar_emocao(fala: str) -> str:
    """PASSO 2 — emoção detectada LOCALMENTE (sem chamar o modelo): instantâneo."""
    t = _sem_acento(fala.lower())
    melhor, pontos = "neutro", 0
    for emo, pistas in _LEXICO.items():
        p = sum(1 for w in pistas if w in t)
        if p > pontos:
            melhor, pontos = emo, p
    if pontos == 0:                       # sem palavra-chave: usa a pontuação
        if "?" in t:
            return "questionamento"
        if "..." in t:
            return "reflexao"
    return melhor


def conversa_concluida(tema: str, historico: list) -> bool:
    conversa = "\n".join(f"{nome}: {fala}" for nome, fala in historico[-16:])
    prompt = (
        "Abaixo, uma conversa de bar entre ÉRIS, LYRA e NOVA.\n"
        f"Tema: {tema}\n\n{conversa}\n\n"
        "Só responda SIM se elas REALMENTE esgotaram o assunto: as discordâncias foram "
        "trabalhadas a fundo, todos os ângulos foram explorados e chegaram a uma síntese "
        "ou acordo genuíno. Se ainda há qualquer coisa a explorar, questionar ou provocar, "
        "responda NAO. Na dúvida, responda NAO.\n"
        "Responda APENAS com SIM ou NAO."
    )
    return _ollama(prompt, temperatura=0).strip().upper().startswith("SIM")


# ──────────────────────────────────────────────────────────────────
# VOZ (edge-tts) — emoção via ritmo/tom/volume
# ──────────────────────────────────────────────────────────────────

async def _sintetizar(texto: str, ia: str, emocao: str, caminho: str):
    base = IAS[ia]
    dr, dp, dv = EMOCOES.get(emocao, (0, 0, 0))
    # jitter leve por fala = voz menos mecânica, mais "viva"
    rate = max(-40, min(48, base["rate"] + dr + random.randint(-3, 3)))
    pitch = max(-15, min(24, base["pitch"] + dp + random.randint(-2, 2)))
    vol = max(-35, min(14, dv))
    com = edge_tts.Communicate(
        texto, base["voz"],
        rate=f"{rate:+d}%", pitch=f"{pitch:+d}Hz", volume=f"{vol:+d}%",
    )
    await com.save(caminho)


def sintetizar_um(texto: str, ia: str, emocao: str) -> str:
    caminho = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False).name
    asyncio.run(_sintetizar(texto, ia, emocao, caminho))
    return caminho


def tocar_lote(lote: list):
    """lote = [(caminho, interrompe), ...] — toca com sobreposição (interrupções)."""
    n = len(lote)
    itens = [f"{cam};{1 if (i + 1 < n and lote[i + 1][1]) else 0}"
             for i, (cam, _) in enumerate(lote)]
    subprocess.run(
        ["powershell", "-ExecutionPolicy", "Bypass", "-File", PLAYER_DIALOGO,
         "-Itens", "|".join(itens)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600,
    )
    for cam, _ in lote:
        try:
            os.remove(cam)
        except OSError:
            pass


# ──────────────────────────────────────────────────────────────────
# FUNDO DE BAR
# ──────────────────────────────────────────────────────────────────

def iniciar_fundo():
    try:
        from fundo_bar import garantir_fundo
        if garantir_fundo(ARQ_FUNDO):
            return subprocess.Popen(
                ["powershell", "-ExecutionPolicy", "Bypass", "-File", PLAYER_FUNDO,
                 "-Path", ARQ_FUNDO, "-Volume", VOLUME_FUNDO],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
    except Exception as e:
        print(f"[AVISO] Sem fundo de bar ({e}).")
    return None


def parar_fundo(proc):
    if proc:
        try:
            proc.terminate()
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────────
# CONDUÇÃO DA CONVERSA
# ──────────────────────────────────────────────────────────────────

def conduzir_conversa(tema: str):
    """Produz as falas numa thread e vai TOCANDO conforme saem (streaming)."""
    turnos = []          # [(ia, texto, interrompe, emocao), ...]
    fila = queue.Queue()
    parar = threading.Event()

    def produtor():
        ultimo, ultimo_int, aquecido = None, False, False
        while len(turnos) < MAX_FALAS and not parar.is_set():
            falante = (random.choice(list(IAS)) if ultimo is None
                       else random.choice([x for x in IAS if x != ultimo]))
            interrompe = (len(turnos) >= 1 and not ultimo_int
                          and random.random() < PROB_INTERRUPCAO)
            encerrando = len(turnos) >= MAX_FALAS - 4 and not interrompe

            hist = [(t[0], t[1]) for t in turnos]
            fala = gerar_fala(falante, tema, hist, interrompe, encerrando, aquecido)
            # evita repetir verbatim uma fala recente
            recentes = [_sem_acento(t[1].lower()) for t in turnos[-3:]]
            if _sem_acento(fala.lower()) in recentes:
                fala = gerar_fala(falante, tema, hist, interrompe, encerrando, aquecido)
            emocao = detectar_emocao(fala)          # local, instantâneo
            turnos.append((falante, fala, interrompe, emocao))

            marca = "╴" if interrompe else " "
            print(f"  {marca}{falante} ({emocao}): {fala}")

            fila.put((sintetizar_um(fala, falante, emocao), interrompe))
            ultimo, ultimo_int = falante, interrompe
            aquecido = emocao == "irritacao"   # só raiva de verdade esquenta o clima

            if len(turnos) >= MIN_FALAS and not interrompe and len(turnos) % 4 == 0:
                if conversa_concluida(tema, [(t[0], t[1]) for t in turnos]):
                    print("\n  🍻 (depois de muito debate, chegaram a uma conclusão)")
                    break
        fila.put(None)   # sinaliza fim

    threading.Thread(target=produtor, daemon=True).start()

    print("\n🔊 A conversa começa em instantes...\n")
    encerrado = False
    pendentes = []
    # buffer inicial: junta as primeiras falas antes de tocar (firma o ritmo)
    while len(pendentes) < 3 and not encerrado:
        it = fila.get()
        if it is None:
            encerrado = True
        else:
            pendentes.append(it)
    try:
        while pendentes:
            # despeja TUDO que já estiver pronto no mesmo bloco -> toca sem emendas
            while True:
                try:
                    it = fila.get_nowait()
                except queue.Empty:
                    break
                if it is None:
                    encerrado = True
                    break
                pendentes.append(it)
            tocar_lote(pendentes)
            pendentes = []
            if not encerrado:
                it = fila.get()            # espera a próxima ficar pronta
                if it is None:
                    encerrado = True
                else:
                    pendentes.append(it)
    finally:
        parar.set()


# ──────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────

def verificar_ollama():
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        modelos = [m["name"] for m in r.json().get("models", [])]
        if not any(MODELO in m for m in modelos):
            print(f"[AVISO] Modelo '{MODELO}' não encontrado. Rode: ollama pull {MODELO}")
            sys.exit(1)
    except requests.exceptions.ConnectionError:
        print("[ERRO] Ollama não está rodando. Abra o app Ollama e tente de novo.")
        sys.exit(1)


def main():
    verificar_ollama()
    fundo = iniciar_fundo()

    print("\n" + "═" * 68)
    print("🎙️  TRÊS VOZES — ÉRIS, LYRA e NOVA num bar (com emoção)")
    print("═" * 68)
    print("Digite um tema e ouça as três sentirem, cortarem e se entenderem.")
    print("Ctrl+C ou 'sair' para encerrar.\n")

    try:
        while True:
            tema = input("🎤 Tema ➜ ").strip()
            if tema.lower() in ("sair", "exit", "quit"):
                break
            if not tema:
                continue
            print("\n💭 Esquentando a mesa...\n")
            conduzir_conversa(tema)
            print("\n" + "─" * 68 + "\n")
    except KeyboardInterrupt:
        print("\n")
    finally:
        parar_fundo(fundo)
        print("Até a próxima rodada! 🍻\n")


if __name__ == "__main__":
    main()
