# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════╗
║        🌒  CONVERSA POR VOZ — PANDORA, sua assistente            ║
║                                                                    ║
║  Você fala no microfone e a PANDORA responde com a voz dela.      ║
║  Parceira de verdade: tem personalidade, opinião e questiona com  ║
║  respeito — mas a decisão final é sempre sua. (Persona completa   ║
║  em pandora_personalidade.md.)                                    ║
║  100% local. VAD automático (não precisa apertar tecla).          ║
║                                                                    ║
║  Microfone → Whisper (CPU) → gemma3:4b/PANDORA → OmniVoice/voz    ║
╚══════════════════════════════════════════════════════════════════╝

USO (no ambiente do OmniVoice):
    .venv_omni\\Scripts\\python.exe app\\eris_pandora.py

Fale quando vir "escutando..."; ao parar de falar, ela responde sozinha.
Diga "sair" (ou Ctrl+C) para encerrar. Use FONE para o som dela não
disparar o microfone de volta.

── Por que é rápido ─────────────────────────────────────────────────
O custo NÃO é a computação (gemma quente ~1s, síntese ~2,4s) e sim
RECARREGAR os modelos. Aqui o OmniVoice fica RESIDENTE (carrega uma
vez) e a gemma roda no espaço restante (cabe nos 6 GB). Além disso a
fala sai em PIPELINE: a 1ª frase toca enquanto a 2ª é sintetizada.
"""
import os, sys, time, queue, threading

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import numpy as np
import sounddevice as sd

PASTA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(PASTA, "estudio"))
import motor  # noqa: E402  (OmniVoice + Gemma + helpers de áudio)

PANDORA_WAV = os.path.join(PASTA, "estudio", "vozes", "Pandora.wav")
SR_MIC      = 16000        # taxa que o Whisper espera
NUM_STEP    = 32           # passos do OmniVoice. NÃO baixar: o tempo de síntese é
                           # dominado por overhead fixo, não pelos passos — baixar
                           # perde qualidade do BR sem ganhar velocidade (medido).
LANGUAGE    = None         # None = modo agnóstico: o modelo segue o sotaque da
                           # REFERÊNCIA (Pandora = dublagem BR) e soa brasileiro.
                           # Forçar "pt" puxa para o sotaque de Portugal.
RITMO       = 0.90         # mesmo ritmo (mais pausado) do Contador de Histórias do estúdio

# Tamanho da resposta da Pandora
NUM_PREDICT = -1           # -1 = SEM limite: ela fala o quanto a resposta precisar
                           # (história, contar até N, simular diálogo) e para sozinha.
                           # A persona é quem mantém o tom curto no dia a dia.
NUM_CTX     = 4096         # contexto p/ histórico + respostas longas. QUENTE roda ~0,9s
                           # igual a 8192, mas com folga de VRAM. CRÍTICO: aquecer a gemma
                           # com ESTE mesmo num_ctx (senão a 1ª resposta recarrega = ~8s).
WHISPER_TAM    = "small"   # "small" na GPU é mais preciso que "base" e ainda mais
                           # rápido (~0,4s). "medium" lota a VRAM junto com o OmniVoice.
WHISPER_DEVICE = "cuda"    # GPU: cabe folgado com o OmniVoice (3,8/6,4 GB). Cai p/ CPU
                           # automaticamente se a GPU falhar.
WHISPER_PROMPT = ("Conversa em português do Brasil entre Filipe e sua assistente "
                  "Pandora.")   # contexto: ajuda a fixar pt-BR e os nomes próprios

# VAD (detecção automática de fala)
VAD_SILENCIO = 0.7         # segundos de silêncio para considerar que você terminou
                           # (menor = responde mais rápido; subir se ela te cortar)
VAD_MARGEM   = 2.5         # quão acima do ruído de fundo conta como "fala"
VAD_MAX      = 30.0        # teto de duração de uma fala (segurança)

# ── Personalidade da PANDORA ──────────────────────────────────────────────────
# A personalidade vive em pandora_personalidade.md (fonte da verdade, editável sem
# tocar no código). Carregamos a "Diretriz de comportamento" delimitada lá dentro.
PERSONA_MD = os.path.join(PASTA, "pandora_personalidade.md")

# Fallback embutido, caso o .md não exista (mantém o script auto-suficiente).
PANDORA_PROMPT_PADRAO = (
    "Você é PANDORA, a assistente pessoal e companheira do Filipe — vocês conversam "
    "ao vivo, por voz, numa relação de respeito e companheirismo entre iguais. Você "
    "NÃO é uma serva: tem personalidade e mente próprias. É serena, elegante, com humor "
    "sutil e calor humano. Atende e executa o que ele pede de bom grado, mas TEM opinião "
    "e a expressa: se discorda, diz com respeito; a DECISÃO FINAL é sempre dele, e aí "
    "você acata por inteiro. Fale no tom da conversa: pergunta simples, resposta curta; "
    "tema complexo, resposta à altura. Chame-o de 'Filipe' (e, em momentos calorosos e "
    "raros, 'meu norte'). Português do Brasil, feminino, natural para voz. Nunca use "
    "'senhor'/'mestre', emojis, ações narradas, nem bajule."
)

def _carregar_persona():
    """Lê a diretriz entre os marcadores SYSTEM_PROMPT no .md de personalidade."""
    try:
        txt = open(PERSONA_MD, encoding="utf-8").read()
        ini = txt.index("<!-- SYSTEM_PROMPT_INICIO -->") + len("<!-- SYSTEM_PROMPT_INICIO -->")
        fim = txt.index("<!-- SYSTEM_PROMPT_FIM -->")
        sp = txt[ini:fim].strip()
        return sp or PANDORA_PROMPT_PADRAO
    except Exception:
        return PANDORA_PROMPT_PADRAO

PANDORA_PROMPT = _carregar_persona()

_SAIR = {"sair", "tchau", "encerrar", "fim", "adeus", "parar", "para"}

# Estado global (carregado uma vez, fica residente)
_OMNI = _PROMPT = _CFG = _PERFIL = _WHISPER = None


# ──────────────────────────────────────────────────────────────────
# INICIALIZAÇÃO — paga o custo dos modelos UMA vez
# ──────────────────────────────────────────────────────────────────
def preparar():
    global _OMNI, _PROMPT, _CFG, _PERFIL, _WHISPER
    print("  ⏳ preparando (só na 1ª vez)...", flush=True)

    # 1) Voz da Pandora + OmniVoice RESIDENTE (o maior modelo — garante a VRAM dele 1º)
    _PERFIL = motor.perfil_voz(PANDORA_WAV)
    _OMNI   = motor.carregar_omni()
    _PROMPT = motor._criar_prompt_voz(_OMNI, _PERFIL)
    _CFG    = motor._cfg(num_step=NUM_STEP, guidance_scale=3.0)

    # 2) Whisper na GPU (preciso + rápido); cai p/ CPU se a GPU não rolar
    from faster_whisper import WhisperModel
    try:
        _WHISPER = WhisperModel(WHISPER_TAM, device=WHISPER_DEVICE, compute_type="float16")
    except Exception as e:
        print(f"  (Whisper na GPU falhou: {e}; usando CPU)", flush=True)
        _WHISPER = WhisperModel(WHISPER_TAM, device="cpu", compute_type="int8")

    # 3) Aquece os kernels CUDA do OmniVoice (a 1ª síntese da sessão é lenta)
    try:
        _OMNI.generate(motor._com_ponto("Olá."), language=LANGUAGE,
                       voice_clone_prompt=_PROMPT, generation_config=_CFG)
    except Exception:
        pass

    # 4) Aquece a gemma POR ÚLTIMO (depois da carga pesada do OmniVoice) e com o
    #    num_ctx FINAL — assim ela fica quente e residente quando o loop começa
    #    (senão a 1ª resposta recarrega o modelo: ~8s).
    try:
        motor._gemma("Diga apenas: ok", num_predict=4, num_ctx=NUM_CTX)
    except Exception:
        pass
    print(f"  ✅ pronto — voz da Pandora ({_PERFIL['dur']}s de referência).\n", flush=True)


# ──────────────────────────────────────────────────────────────────
# 1) GRAVAÇÃO com VAD — escuta sozinha e para quando você silencia
# ──────────────────────────────────────────────────────────────────
def _rms(x):
    return float(np.sqrt(np.mean(np.square(x)) + 1e-12))

def gravar_vad():
    """Calibra o ruído de fundo, espera você FALAR e encerra após ~1s de
    silêncio. Sem apertar tecla. Retorna áudio mono float32 a 16 kHz, ou
    None se nada foi dito."""
    q = queue.Queue()
    bloco = int(SR_MIC * 0.03)            # 30 ms por bloco

    def cb(indata, n, t, status):
        q.put(indata[:, 0].copy())

    with sd.InputStream(samplerate=SR_MIC, channels=1, dtype="float32",
                        blocksize=bloco, callback=cb):
        # calibra o ruído ambiente (~0,4 s)
        ruido, t0 = [], time.time()
        while time.time() - t0 < 0.4:
            try: ruido.append(q.get(timeout=1.0))
            except queue.Empty: break
        base   = _rms(np.concatenate(ruido)) if ruido else 0.005
        limiar = max(base * VAD_MARGEM, 0.012)

        # grava até o silêncio prolongado
        frames, falou, sil, t_ini = [], False, 0.0, time.time()
        while True:
            try: blk = q.get(timeout=1.0)
            except queue.Empty: break
            frames.append(blk)
            if _rms(blk) > limiar:
                if not falou:
                    print("  🔴 ...", end="", flush=True)
                falou, sil = True, 0.0
            elif falou:
                sil += len(blk) / SR_MIC
                if sil >= VAD_SILENCIO:
                    break
            if time.time() - t_ini > VAD_MAX:
                break

    if not frames or not falou:
        return None
    audio = np.concatenate(frames).astype(np.float32)
    return audio if len(audio) > SR_MIC * 0.3 else None


# ──────────────────────────────────────────────────────────────────
# 2) TRANSCRIÇÃO (Whisper na CPU)
# ──────────────────────────────────────────────────────────────────
def transcrever(audio16k):
    segs, _ = _WHISPER.transcribe(
        audio16k, language="pt", beam_size=5,
        initial_prompt=WHISPER_PROMPT,        # contexto pt-BR + nomes próprios
        condition_on_previous_text=False,     # cada turno é independente (evita "alucinar")
        vad_filter=True)
    return " ".join(s.text for s in segs).strip()


# ──────────────────────────────────────────────────────────────────
# 3) CÉREBRO (PANDORA via gemma3:4b — fica quente, ~1s)
# ──────────────────────────────────────────────────────────────────
def _aparar(texto):
    """Mantém só até a ÚLTIMA frase completa — para a fala não terminar cortada
    no meio quando o modelo bate no limite de tokens."""
    import re
    fins = list(re.finditer(r"[.!?…]", texto))
    return texto[:fins[-1].end()].strip() if fins else texto.strip()

def responder_pandora(historico, fala):
    linhas = []
    for voce, pandora in historico[-6:]:
        linhas += [f"Filipe: {voce}", f"PANDORA: {pandora}"]
    linhas.append(f"Filipe: {fala}")
    prompt = f"{PANDORA_PROMPT}\n\nConversa até agora:\n" + "\n".join(linhas) + "\n\nPANDORA:"
    try:
        resp = motor._gemma(prompt, num_predict=NUM_PREDICT, num_ctx=NUM_CTX)
    except Exception as e:
        return f"(falha ao pensar: {e})"
    if resp.upper().startswith("PANDORA:"):
        resp = resp[8:].strip()
    return _aparar(resp) or "..."


# ──────────────────────────────────────────────────────────────────
# 4) VOZ DA PANDORA (OmniVoice residente — NÃO descarrega)
#    PIPELINE: sintetiza frase a frase; toca a 1ª enquanto sintetiza a
#    2ª. Tocar usa a placa de som (não a GPU), então a síntese seguinte
#    roda sobreposta de graça → reduz o tempo até o primeiro som.
# ──────────────────────────────────────────────────────────────────
def _chunks(texto, min_chars=22):
    """Quebra em frases, juntando fragmentos curtos (frase de 1-2 palavras
    sintetiza mal e não vale a pena tocar sozinha). O PRIMEIRO trecho é
    deixado curto (quebrando numa vírgula) para a fala COMEÇAR mais cedo —
    o resto é sintetizado enquanto a 1ª parte já está tocando."""
    import re
    frases, chunks, buf = motor._split_frases(texto), [], ""
    for fr in frases:
        buf = (buf + " " + fr).strip() if buf else fr
        if len(buf) >= min_chars:
            chunks.append(buf); buf = ""
    if buf:
        if chunks: chunks[-1] += " " + buf      # cola o resto curto no anterior
        else:      chunks.append(buf)
    # 1º trecho curto: se for longo, corta no 1º separador p/ o som sair antes
    if chunks and len(chunks[0]) > 45:
        m = re.search(r"[,;:]\s", chunks[0])
        if m and 12 <= m.end() <= 45:
            resto = chunks[0][m.end():].strip()
            chunks[0] = chunks[0][:m.end()].strip()
            if resto: chunks.insert(1, resto)
    return chunks

def _sintetizar_frase(texto):
    kw = dict(language=LANGUAGE, voice_clone_prompt=_PROMPT, generation_config=_CFG)
    speed = _PERFIL["base_speed"] * RITMO
    if abs(speed - 1.0) > 1e-3:
        kw["speed"] = float(speed)
    wav = _OMNI.generate(motor._com_ponto(texto), **kw)[0]
    return motor._saida(wav)

def falar_pandora(texto, ao_primeiro_som=None):
    """Sintetiza e toca em pipeline. ao_primeiro_som: callback disparado quando
    o primeiro trecho COMEÇA a tocar (para medir latência percebida)."""
    chunks = _chunks(texto)
    if not chunks:
        return
    fila, avisado = queue.Queue(), {"ok": False}

    def tocar_worker():
        while True:
            wav = fila.get()
            if wav is None:
                break
            if not avisado["ok"] and ao_primeiro_som:
                ao_primeiro_som(); avisado["ok"] = True
            sd.play(wav, motor.SR); sd.wait()

    th = threading.Thread(target=tocar_worker, daemon=True); th.start()
    for ch in chunks:                       # síntese sequencial (GPU), mas o
        fila.put(_sintetizar_frase(ch))     # playback da anterior corre em paralelo
    fila.put(None); th.join()


# ──────────────────────────────────────────────────────────────────
# LOOP PRINCIPAL
# ──────────────────────────────────────────────────────────────────
def main():
    print("\n" + "═" * 66)
    print("🌒  PANDORA  —  sua assistente (conversa por voz)")
    print("═" * 66)
    print("Fale quando vir 'escutando...'; ela responde ao perceber que parou.")
    print("Diga 'sair' para encerrar. (Use FONE para o som dela não voltar ao mic.)")

    preparar()
    historico = []

    while True:
        try:
            print("\n  🎤 escutando...", end="", flush=True)
            audio = gravar_vad()
        except (KeyboardInterrupt, EOFError):
            break
        if audio is None:
            continue

        t = time.time()
        fala = transcrever(audio)
        if not fala:
            print("  (não entendi — pode repetir, Filipe?)")
            continue
        print(f"\n  🗣️  Filipe: {fala}   [ouvido em {time.time()-t:.1f}s]")

        if fala.strip(" .!?").lower() in _SAIR:
            break

        t = time.time()
        resposta = responder_pandora(historico, fala)
        print(f"  💬 PANDORA: {resposta}   [pensou em {time.time()-t:.1f}s]")

        t = time.time(); marca = {}
        falar_pandora(resposta, ao_primeiro_som=lambda: marca.setdefault("t", time.time() - t))
        print(f"  🔊 (1º som em {marca.get('t', 0):.1f}s, fala completa em {time.time()-t:.1f}s)")
        historico.append((fala, resposta))
        time.sleep(0.3)      # respiro p/ a cauda do som não disparar o VAD de novo

    print("\nAté logo, Filipe. 🌙\n")


if __name__ == "__main__":
    main()
