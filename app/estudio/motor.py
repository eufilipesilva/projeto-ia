# -*- coding: utf-8 -*-
"""Motor do Estúdio — OmniVoice + Gemma (Ollama).
Ciclo de memória: gemma infere → descarrega → OmniVoice sintetiza → descarrega.
Roda com 6 GB VRAM (RTX 2060) — os dois modelos nunca coexistem.
"""
import os, sys, re, json, gc, random, unicodedata, urllib.request
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
import warnings; warnings.filterwarnings("ignore")
import numpy as np, soundfile as sf, torch

PASTA = os.path.dirname(os.path.abspath(__file__))
SR    = 24000

OLLAMA     = "http://127.0.0.1:11434"
MODELO_LLM = "gemma3:4b"

# ── OmniVoice ────────────────────────────────────────────────────────────────
_MODEL = None

def carregar_omni():
    global _MODEL
    if _MODEL is None:
        from omnivoice import OmniVoice
        print("Carregando OmniVoice...", flush=True)
        _MODEL = OmniVoice.from_pretrained(
            "k2-fsa/OmniVoice",
            device_map="auto",
            dtype=torch.float16,
            load_asr=False,   # load_asr=True requer FFmpeg (torchcodec) — não disponível aqui
            token=False,
        )
    return _MODEL

def descarregar_omni():
    global _MODEL
    if _MODEL is not None:
        _MODEL = None; gc.collect(); torch.cuda.empty_cache()

def _cfg(num_step=32, guidance_scale=3.0):
    from omnivoice import OmniVoiceGenerationConfig
    return OmniVoiceGenerationConfig(
        num_step=num_step,
        guidance_scale=guidance_scale,
        class_temperature=0.0,
        postprocess_output=False,   # o postproc do OmniVoice apara a cauda — cortamos nós, preservando o fim
    )

# ── Gemma (Ollama REST) ──────────────────────────────────────────────────────
def _gemma(prompt, num_predict=256, num_ctx=2048, temperature=0):
    body = json.dumps({"model": MODELO_LLM, "prompt": prompt, "stream": False,
                       "options": {"temperature": temperature, "num_predict": num_predict,
                                   "num_ctx": num_ctx}}).encode()
    req = urllib.request.Request(OLLAMA + "/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())["response"].strip()

def descarregar_gemma():
    import subprocess, time
    try:
        body = json.dumps({"model": MODELO_LLM, "keep_alive": 0}).encode()
        urllib.request.urlopen(
            urllib.request.Request(OLLAMA + "/api/generate", data=body,
                                   headers={"Content-Type": "application/json"}),
            timeout=30).read()
    except Exception: pass
    try:
        subprocess.run(["ollama", "stop", MODELO_LLM], timeout=10,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception: pass
    time.sleep(2)
    torch.cuda.empty_cache()

# ── Emoções ──────────────────────────────────────────────────────────────────
EMO = {
    # s=velocidade  p=pitch  vol=volume  brilho=espectro  tremolo=depth  eco=reverb leve
    "alegria":     dict(s=1.05, p=1.04, vol=1.10, brilho=1.25, tremolo=0.0,  eco=False),
    "tristeza":    dict(s=0.90, p=0.95, vol=0.90, brilho=0.72, tremolo=0.0,  eco=False),
    "raiva":       dict(s=1.06, p=0.98, vol=1.12, brilho=1.30, tremolo=0.0,  eco=False),
    "medo":        dict(s=1.04, p=1.03, vol=0.90, brilho=0.88, tremolo=0.12, eco=False),
    "surpresa":    dict(s=1.05, p=1.06, vol=1.16, brilho=1.20, tremolo=0.0,  eco=False),
    "nojo":        dict(s=0.95, p=0.97, vol=0.95, brilho=0.82, tremolo=0.0,  eco=False),
    "empolgacao":  dict(s=1.10, p=1.06, vol=1.30, brilho=1.40, tremolo=0.0,  eco=False),
    "ternura":     dict(s=0.92, p=1.00, vol=0.85, brilho=1.00, tremolo=0.0,  eco=False),
    "serenidade":  dict(s=0.88, p=0.99, vol=0.88, brilho=0.88, tremolo=0.0,  eco=False),
    "confianca":   dict(s=0.97, p=0.98, vol=1.02, brilho=1.05, tremolo=0.0,  eco=False),
    "ansiedade":   dict(s=1.10, p=1.03, vol=0.98, brilho=1.10, tremolo=0.09, eco=False),
    "frustracao":  dict(s=0.96, p=0.97, vol=1.00, brilho=1.12, tremolo=0.0,  eco=False),
    "sarcasmo":    dict(s=0.96, p=1.01, vol=0.98, brilho=1.02, tremolo=0.0,  eco=False),
    "curiosidade": dict(s=0.99, p=1.02, vol=1.00, brilho=1.10, tremolo=0.0,  eco=False),
    "melancolia":  dict(s=0.88, p=0.96, vol=0.90, brilho=0.68, tremolo=0.0,  eco=True),
    "arrogancia":  dict(s=0.94, p=0.99, vol=1.04, brilho=1.05, tremolo=0.0,  eco=False),
    "timidez":     dict(s=0.95, p=1.02, vol=0.78, brilho=0.88, tremolo=0.07, eco=False),
    "urgencia":    dict(s=1.14, p=1.04, vol=1.10, brilho=1.25, tremolo=0.0,  eco=False),
    "neutra":      dict(s=1.00, p=1.00, vol=1.00, brilho=1.00, tremolo=0.0,  eco=False),
    "suspenso":    dict(s=0.86, p=0.97, vol=0.95, brilho=0.75, tremolo=0.0,  eco=True),
    "misterio":    dict(s=0.89, p=0.98, vol=0.92, brilho=0.72, tremolo=0.0,  eco=True),
}
EMO_LISTA = list(EMO.keys())

# paleta de timbres para personagens (Contador de Histórias)
PALETA = [
    dict(speed=1.03, P=1.12),
    dict(speed=0.90, P=0.80),
    dict(speed=0.92, P=1.06),
    dict(speed=0.98, P=0.87),
    dict(speed=1.06, P=1.20),
    dict(speed=0.95, P=0.92),
]

# ── Helpers de áudio ─────────────────────────────────────────────────────────
def _pitch(x, P):
    if abs(P - 1.0) < 1e-3 or len(x) < 2: return x
    idx = np.arange(0, len(x), P)
    return np.interp(idx, np.arange(len(x)), x).astype(np.float32)

def _rms(x):
    return float(np.sqrt(np.mean(x**2) + 1e-9))

def _envelope(x, win):
    n = len(x) // win
    if n < 1: return np.array([_rms(x)])
    return np.sqrt((x[:n*win]**2).reshape(n, win).mean(axis=1) + 1e-12)

def _fade_in_cos(x, ms=45):
    f = min(int(SR * ms / 1000), len(x))
    if f > 1: x[:f] *= 0.5 * (1 - np.cos(np.linspace(0, np.pi, f)))
    return x

def _fade_exp(x, ms):
    """Fade-out exponencial (1→~0): imita o decaimento natural da voz (não corte seco).
    Expoente menor = decaimento mais gradual/suave."""
    f = min(int(SR * ms / 1000), len(x))
    if f > 1:
        g = np.exp(-4.0 * np.linspace(0, 1, f)); g = (g - g[-1]) / (g[0] - g[-1])
        x[-f:] *= g
    return x

def _zcr(x):
    """Taxa de cruzamento por zero. Baixa = som vozeado/vogal; alta = consoante/fricativa."""
    if len(x) < 2: return 0.0
    return float(np.mean(np.abs(np.diff(np.sign(x + 1e-12))) > 0))

def finalizar(x):
    """Corta o silêncio morto das pontas PRESERVANDO a cauda fonética da última
    palavra, e aplica fade-out exponencial adaptativo — para o fim não soar cortado.
    Termina em VOGAL (vozeado, sustenta energia) → fade ainda mais longo, pra a vogal
    morrer gradual como na fala real (consoantes já decaem sozinhas)."""
    x = np.asarray(x, dtype=np.float32)
    win = int(0.02 * SR)                                  # janelas de 20ms
    env = _envelope(x, win); pico = env.max() or 1.0
    fala = np.where(env > pico * 10**(-35/20))[0]         # -35 dB: pega até fricativas suaves (s, f)
    if len(fala):
        fim = min(len(x), (fala[-1] + 1) * win + int(0.09 * SR))   # fim da fala + 90ms de cauda
        ini = max(0, fala[0] * win - int(0.008 * SR))
        x = x[ini:fim]
    cauda = x[-int(0.04 * SR):] if len(x) > int(0.04 * SR) else x
    abr = min(1.0, (_rms(cauda) / pico) / 0.45)           # quão abrupto é o fim
    fade_ms = 260 + 220 * abr                             # 260ms (decai só) → ~480ms (corte forte)
    if _zcr(cauda) < 0.12:                                # cauda vozeada = vogal → fade mais longo
        fade_ms *= 1.25
    fade_ms = min(fade_ms, 620)
    return _fade_exp(_fade_in_cos(x), fade_ms)

def _roomtone(n):
    w = np.random.randn(n).astype(np.float32); k = np.ones(80, dtype=np.float32) / 80
    rt = np.convolve(w, k, mode="same"); return rt / (np.max(np.abs(rt)) or 1) * 0.0035

def _sussurro(x):
    """Sussurro/ASMR por 'whisperização': mantém a envoltória ESPECTRAL (formantes, que
    tornam o sussurro inteligível) e troca a FASE por ruído — isso remove o tom/pitch
    e vira excitação aspirada, como um sussurro real. Bem melhor que ruído modulado
    por amplitude (que vira só chiado)."""
    x = np.asarray(x, dtype=np.float32)
    if x.size < 1024:
        return x
    try:
        import librosa
    except Exception:
        return x
    n_fft, hop = 1024, 256
    S = librosa.stft(x, n_fft=n_fft, hop_length=hop)
    mag = np.abs(S)
    # envoltória espectral: suaviza a magnitude na frequência → apaga os HARMÔNICOS (o pitch)
    # mas mantém os FORMANTES (a forma do trato vocal, que dá inteligibilidade)
    try:
        from scipy.ndimage import uniform_filter1d
        env = uniform_filter1d(mag, size=25, axis=0)
    except Exception:
        k = np.ones(25, dtype=np.float32) / 25
        env = np.stack([np.convolve(mag[:, c], k, mode="same") for c in range(mag.shape[1])], axis=1)
    ruido = np.random.rand(*mag.shape).astype(np.float32) + 0.5     # excitação aspirada (sem harmônicos)
    fase  = np.exp(2j * np.pi * np.random.rand(*mag.shape).astype(np.float32))
    y = librosa.istft(env * ruido * fase, hop_length=hop, length=len(x)).astype(np.float32)
    return y / (np.max(np.abs(y)) or 1) * 0.8


def _brilho(x, fator):
    """Espectro brilhante (fator>1) via pré-ênfase ou escuro (fator<1) via de-ênfase.
    Filtro de 1ª ordem; normaliza RMS para não alterar volume."""
    if abs(fator - 1.0) < 0.03 or len(x) < 4:
        return x
    try:
        from scipy.signal import lfilter
        a = float(np.clip((fator - 1.0) * 0.55, -0.85, 0.85))
        y = lfilter([1.0, -a], [1.0], x).astype(np.float32)
        rms_y = _rms(y)
        if rms_y > 1e-9:
            y *= _rms(x) / rms_y
        return y
    except Exception:
        return x

def _tremolo(x, depth=0.10, freq=5.0):
    """Vibração de amplitude (tremolo) — medo, ansiedade, timidez."""
    if depth < 0.01 or len(x) < 2:
        return x
    t = np.arange(len(x), dtype=np.float32) / SR
    return (x * (1.0 + depth * np.sin(2.0 * np.pi * freq * t))).astype(np.float32)

def _eco(x, delay_ms=38, decay=0.22):
    """Eco suave para suspense / mistério / melancolia."""
    delay = int(SR * delay_ms / 1000)
    if delay >= len(x):
        return x
    y = x.copy()
    y[delay:] += x[: len(x) - delay] * decay
    pico = np.max(np.abs(y)) or 1.0
    return (y / pico * (np.max(np.abs(x)) or 1.0)).astype(np.float32)


def _montar(segs, quem=None):
    """Junta os segmentos SEM sobrepor (pra não atropelar a cauda da vogal, que decai
    no fade-out longo). Mesmo responsável em beats seguidos → respiração curta, soa
    contínuo; troca de locutor → pausa maior."""
    if not segs:
        return np.zeros(1, dtype=np.float32)
    p_mesmo = np.zeros(int(0.09 * SR), dtype=np.float32)   # respiração curta (fala contínua)
    p_troca = np.zeros(int(0.24 * SR), dtype=np.float32)   # pausa de troca de locutor
    partes = [np.asarray(segs[0], dtype=np.float32)]
    for i in range(1, len(segs)):
        mesmo = quem is not None and quem[i] == quem[i - 1]
        partes.append((p_mesmo if mesmo else p_troca).copy())
        partes.append(np.asarray(segs[i], dtype=np.float32))
    voz = np.concatenate(partes)
    mix = voz + _roomtone(len(voz))
    return (mix / (np.max(np.abs(mix)) or 1) * 0.95).astype(np.float32)

def _carregar_fundo(path, volume):
    """Carrega um áudio de fundo (MP3/WAV/etc) via librosa (suporta MP3 no Windows),
    em mono na taxa do estúdio, normalizado para o volume pedido (bem baixo = sutil)."""
    try:
        import librosa
        wav, _ = librosa.load(path, sr=SR, mono=True)
        wav = wav.astype(np.float32)
        return (wav / (np.max(np.abs(wav)) or 1.0)) * float(volume)
    except Exception as e:
        print(f"[fundo] não carregou '{path}': {e}", flush=True)
        return None

def _misturar_fundo(voz, fundo, cauda_seg=0.0):
    """Loopa o fundo até cobrir a narração e mistura com fade-in/out.
    cauda_seg: segundos extras em que o fundo continua tocando SOZINHO depois que
    a voz acaba (o fade-out do fundo acontece nessa cauda)."""
    if fundo is None or len(fundo) == 0:
        return voz
    cauda  = max(0, int(round(cauda_seg * SR)))
    voz_ext = np.concatenate([voz, np.zeros(cauda, dtype=np.float32)])   # voz + silêncio
    n = len(voz_ext)
    bg = np.tile(fundo, n // len(fundo) + 2)[:n].astype(np.float32)
    fade_in = min(int(SR * 4), n // 2)
    if fade_in > 1:
        bg[:fade_in] *= np.linspace(0, 1, fade_in)
    # fade-out: cabe na cauda (fundo cheio durante a voz, some só depois); sem cauda, 4s no fim
    fade_out = min(int(SR * 4), cauda) if cauda > 0 else min(int(SR * 4), n // 2)
    if fade_out > 1:
        bg[-fade_out:] *= np.linspace(1, 0, fade_out)
    mix = voz_ext + bg
    return (mix / (np.max(np.abs(mix)) or 1) * 0.95).astype(np.float32)

# ── Sonoplastia (modalidade Comédia / auditório) ──────────────────────────────
PASTA_SFX = os.path.join(PASTA, "sonoplastia")
PASTA_EMO = os.path.join(PASTA, "vozes", "emocoes")   # clips de referência por emoção
_PLATEIA_NOMES = ("plateia", "auditorio", "audiencia")

# Dicas de uso p/ nomes-chave comuns — guiam o "sonoplasta" (Gemma). Para nomes fora
# desta lista, a Gemma se guia pelo próprio nome do arquivo (são auto-descritivos).
DESCR_SFX = {
    "aplauso":  "aprovação, acerto, elogio, final triunfal (geralmente DEPOIS)",
    "risada":   "piada, situação engraçada (geralmente DEPOIS)",
    "rufar":    "suspense antes de uma revelação/resultado (geralmente ANTES)",
    "tambor":   "suspense antes de revelar (geralmente ANTES)",
    "suspense": "tensão antes de algo importante (geralmente ANTES)",
    "buzina":   "erro, resposta errada, vexame (geralmente DEPOIS)",
    "trombone": "fracasso, deu ruim, deboche (geralmente DEPOIS)",
    "apito":    "interrupção, chamar atenção",
    "vinheta":  "transição entre partes",
    "grilo":    "silêncio constrangedor, ninguém riu (geralmente DEPOIS)",
    "plateia":  "murmúrio/risadinha de auditório (FUNDO contínuo, nunca pontual)",
}

# Posição FIXA por tipo de efeito (mais confiável que deixar a Gemma decidir):
# reação vem DEPOIS da fala; suspense vem ANTES.
POSICAO_SFX = {
    "aplauso": "depois", "risada": "depois", "buzina": "depois", "trombone": "depois",
    "grilo": "depois", "vinheta": "depois",
    "rufar": "antes", "tambor": "antes", "tabor": "antes", "suspense": "antes", "apito": "antes",
}
DUR_SFX_MAX = 2.5    # efeitos pontuais cortados a no máximo 2,5s (com fade) — mais ágil

def _norm_sfx(nome):
    """Normaliza nome de efeito: sem acento, minúsculo, separadores → espaço."""
    q = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode().lower()
    q = re.sub(r"[_\-]+", " ", q)
    q = re.sub(r"[^a-z0-9 ]", "", q).strip()
    return re.sub(r"\s+", " ", q)

def _catalogo_sfx():
    """Escaneia app/estudio/sonoplastia/ e devolve {nome_chave: caminho} (nome = arquivo
    sem extensão, normalizado). Usa só o que existir na pasta."""
    cat = {}
    if not os.path.isdir(PASTA_SFX):
        return cat
    for f in sorted(os.listdir(PASTA_SFX)):
        base, ext = os.path.splitext(f)
        if ext.lower() not in (".wav", ".mp3", ".ogg", ".flac", ".m4a"):
            continue
        nome = _norm_sfx(base)
        if nome and nome not in cat:
            cat[nome] = os.path.join(PASTA_SFX, f)
    return cat

def _carregar_sfx(path, ganho=1.0, max_seg=0):
    """Carrega um efeito (mono, SR) normalizado p/ o ganho. max_seg>0 corta o efeito
    (com fade-out) — efeitos pontuais curtos deixam o show mais ágil; a plateia (fundo)
    carrega sem corte (max_seg=0)."""
    wav = _carregar_fundo(path, ganho)
    if wav is None:
        return None
    if max_seg and len(wav) > int(max_seg * SR):
        wav = wav[:int(max_seg * SR)].copy()
        f = min(int(0.18 * SR), len(wav) // 4)
        if f > 1: wav[-f:] *= np.linspace(1, 0, f)
    return wav

def _montar_comedia(segs, quem_seg, sfx_seq, catalogo, vol_sfx=0.6,
                    plateia_wav=None, vol_plateia=0.06):
    """Monta voz + sonoplastia PONTUAL (antes/depois/sob) e mistura a PLATEIA de fundo.
    sfx_seq: lista [(efeito, posicao)] por beat; catalogo: {nome: caminho}."""
    if not segs:
        return np.zeros(1, dtype=np.float32)
    cache = {}
    def sfx(nome):
        if not nome or nome == "nenhum":
            return None
        if nome not in cache:
            cam = catalogo.get(nome)
            cache[nome] = _carregar_sfx(cam, vol_sfx, DUR_SFX_MAX) if cam else None
        return cache[nome]
    p_mesmo = np.zeros(int(0.09 * SR), dtype=np.float32)   # respiração (mesmo locutor)
    p_troca = np.zeros(int(0.24 * SR), dtype=np.float32)   # pausa (troca de locutor)
    p_sfx   = np.zeros(int(0.12 * SR), dtype=np.float32)   # respiro ao redor do efeito pontual
    partes = []
    for i, seg in enumerate(segs):
        seg = np.asarray(seg, dtype=np.float32)
        efe, pos = sfx_seq[i] if i < len(sfx_seq) else ("nenhum", "depois")
        s = sfx(efe)
        if i > 0:
            mesmo = quem_seg is not None and quem_seg[i] == quem_seg[i - 1]
            partes.append((p_mesmo if mesmo else p_troca).copy())
        if s is not None and pos == "antes":
            partes.append(s); partes.append(p_sfx.copy())
        if s is not None and pos == "sob":                 # sobrepõe ao começo do beat
            seg = seg.copy(); L = min(len(seg), len(s)); seg[:L] = seg[:L] + s[:L]
        partes.append(seg)
        if s is not None and pos == "depois":
            partes.append(p_sfx.copy()); partes.append(s)
    voz = np.concatenate(partes) if partes else np.zeros(1, dtype=np.float32)
    mix = voz + _roomtone(len(voz))
    if plateia_wav is not None and len(plateia_wav) > 0:   # plateia por baixo de tudo (loop)
        return _misturar_fundo(mix, plateia_wav)           # já normaliza
    return (mix / (np.max(np.abs(mix)) or 1) * 0.95).astype(np.float32)

def _normalizar_fala(txt):
    """Converte travessões de diálogo (–, —, ' - ') em vírgula — o OmniVoice não
    vocaliza em-dash e acaba 'comendo' o texto entre eles. Preserva hífen de
    palavras compostas (guarda-chuva), pois ali não há espaços ao redor."""
    txt = (txt or "")
    txt = txt.replace("—", " , ").replace("–", " , ")   # em/en dash → vírgula
    txt = re.sub(r"(?<=\s)-(?=\s)", ",", txt)            # hífen entre espaços = travessão
    txt = re.sub(r"^[\s,;:.\-]+", "", txt)               # remove marcação no início da fala
    txt = re.sub(r"\s+([,.!?;:])", r"\1", txt)           # cola pontuação à palavra anterior
    txt = re.sub(r"([:;.!?])\s*,", r"\1", txt)           # ':' + ',' → ':' (evita pausa dupla)
    txt = re.sub(r"(,\s*){2,}", ", ", txt)               # colapsa vírgulas repetidas
    return re.sub(r"\s+", " ", txt).strip()

def _com_ponto(txt):
    """Normaliza diálogo e garante pontuação final — sem ela o modelo corta a última palavra."""
    txt = _normalizar_fala(txt)
    return txt if (txt and txt[-1] in ".!?…") else txt + "."

def _saida(wav):
    """Limpa as pontas (preservando a cauda) e normaliza para entrega (peak ~0.95)."""
    wav = finalizar(wav)
    if wav.size < 2:
        return np.zeros(1, dtype=np.float32)
    return (wav / (np.max(np.abs(wav)) or 1.0) * 0.95).astype(np.float32)

# ── Voz de referência ─────────────────────────────────────────────────────────
def estimar_ritmo(wav, sr):
    win = int(0.02 * sr); n = len(wav) // win
    if n < 3: return 0.95
    env = np.sqrt((wav[:n*win]**2).reshape(n, win).mean(axis=1) + 1e-9)
    thr = env.mean()
    picos = int(np.sum((env[1:-1] > thr) & (env[1:-1] >= env[:-2]) & (env[1:-1] > env[2:])))
    taxa = picos / max(len(wav) / sr, 0.5)
    return float(np.clip(0.90 + (taxa - 4.5) * 0.025, 0.85, 1.04))

def perfil_voz(ref_path, ref_text=None, base_speed=None):
    """Analisa voz de referência. Lê .txt ao lado do .wav como transcrição."""
    w, sr = sf.read(ref_path)
    if w.ndim > 1: w = w.mean(axis=1)
    w = w.astype(np.float32)
    dur = len(w) / sr
    if dur < 3.0:
        raise ValueError(f"A voz tem só {dur:.1f}s — precisa de pelo menos 3 segundos.")
    if dur > 12: w = w[:int(12 * sr)]
    import hashlib
    nome = "_ref_" + hashlib.md5(os.path.abspath(ref_path).encode()).hexdigest()[:8] + ".wav"
    mono = os.path.join(PASTA, "vozes", nome); sf.write(mono, w, sr, subtype="PCM_16")
    if base_speed is None: base_speed = estimar_ritmo(w, sr)
    txt_cache = os.path.splitext(os.path.abspath(ref_path))[0] + ".txt"
    if not ref_text and os.path.exists(txt_cache):
        cached = open(txt_cache, encoding="utf-8").read().strip()
        if cached: ref_text = cached
    return {
        "ref":        mono,
        "base_speed": float(base_speed),
        "ref_text":   ref_text.strip() if ref_text else None,
        "txt_cache":  txt_cache,
        "dur":        round(dur, 1),
    }

def _criar_prompt_voz(m, perfil):
    """Cria voice clone prompt. Nunca passa None — evita crash por torchcodec."""
    ref_text = perfil.get("ref_text")
    if not ref_text:
        cache = perfil.get("txt_cache")
        if cache and os.path.exists(cache):
            cached = open(cache, encoding="utf-8").read().strip()
            if cached:
                ref_text = cached; perfil["ref_text"] = cached
    return m.create_voice_clone_prompt(ref_audio=perfil["ref"], ref_text=ref_text or "")

def _carregar_prompts_emocao(m, perfil_base):
    """Pré-carrega voice-clone prompts por emoção a partir de vozes/emocoes/{emo}.wav.
    OmniVoice copia prosódia do clip de referência → emoção genuína na voz.
    Retorna {nome_emo: prompt}; silencioso se a pasta não existir ainda."""
    prompts = {}
    if not os.path.isdir(PASTA_EMO):
        return prompts
    for f in os.listdir(PASTA_EMO):
        nome, ext = os.path.splitext(f.lower())
        if ext != ".wav":
            continue
        try:
            p = perfil_voz(os.path.join(PASTA_EMO, f))
            prompts[nome] = _criar_prompt_voz(m, p)
        except Exception:
            pass
    return prompts

# ── Síntese de um trecho (bloco interno — usado no Contador de Histórias) ─────
def _gerar_um(m, cfg, prompt, txt, speed, tom, vol, language="pt"):
    """Sintetiza um trecho e aplica o timbre do personagem (pitch/volume)."""
    if not txt or not txt.strip():
        return np.zeros(int(0.08 * SR), dtype=np.float32)
    wav = m.generate(_com_ponto(txt), language=language, voice_clone_prompt=prompt,
                     speed=speed / tom, generation_config=cfg)[0]
    wav = np.asarray(wav, dtype=np.float32).squeeze()
    if wav.size < int(0.05 * SR):
        return np.zeros(int(0.08 * SR), dtype=np.float32)
    wav = _pitch(wav, tom)
    wav = wav / _rms(wav) * 0.05 * vol
    return finalizar(wav)

# ── API pública ───────────────────────────────────────────────────────────────
def sintetizar_clone(perfil, texto, language="pt",
                     num_step=32, guidance_scale=3.0, speed_mult=1.0,
                     progresso=lambda *a: None):
    """Lê o texto com a voz clonada — uma única geração (como o notebook de referência)."""
    if not (texto or "").strip():
        return np.zeros(1, dtype=np.float32)
    m      = carregar_omni()
    prompt = _criar_prompt_voz(m, perfil)
    cfg    = _cfg(num_step, guidance_scale)
    speed  = perfil["base_speed"] * speed_mult
    progresso(0.1, "Gerando áudio...")
    kw = dict(language=language, voice_clone_prompt=prompt, generation_config=cfg)
    if abs(speed - 1.0) > 1e-3:
        kw["speed"] = float(speed)
    wav = m.generate(_com_ponto(texto), **kw)[0]
    descarregar_omni()
    return _saida(wav)

def sintetizar_design(instruct, texto, language="pt",
                      num_step=32, guidance_scale=3.0, speed_mult=1.0,
                      progresso=lambda *a: None):
    """Voz projetada via instruct, sem áudio de referência — uma única geração."""
    if not (texto or "").strip():
        return np.zeros(1, dtype=np.float32)
    m   = carregar_omni()
    cfg = _cfg(num_step, guidance_scale)
    progresso(0.1, "Gerando áudio...")
    kw = dict(language=language, generation_config=cfg)
    if instruct:
        kw["instruct"] = instruct
    if abs(speed_mult - 1.0) > 1e-3:
        kw["speed"] = float(speed_mult)
    wav = m.generate(_com_ponto(texto), **kw)[0]
    descarregar_omni()
    return _saida(wav)

def sintetizar_historia(perfil, texto, ritmo=1.0, sussurro=False,
                        musica_path=None, vol_fundo=0.03, cauda_fundo=0.0,
                        progresso=lambda *a: None):
    """Contador de Histórias: separa falas (entre travessões) da narração; a gemma
    atribui personagem + emoção; cada personagem ganha uma voz distinta.
    ritmo: multiplicador de velocidade (<1 = mais devagar, clima de história).
    sussurro: aplica modo sussurro/ASMR (sopro aéreo no lugar do tom).
    musica_path/vol_fundo: áudio de fundo opcional (loop + fade), bem baixo.
    cauda_fundo: segundos em que o fundo segue tocando após a voz acabar."""
    beats = _beats_historia(texto)
    if not beats:
        return np.zeros(1, dtype=np.float32), []
    progresso(0.05, "Lendo a história (quem fala + emoção)...")
    tags = _classificar_beats(beats)
    descarregar_gemma()
    vozes = {}
    def voz_de(quem):
        if quem in ("narrador", "narradora", "narra", ""):
            return dict(speed=perfil["base_speed"], P=1.0, narr=True)
        if quem not in vozes: vozes[quem] = PALETA[len(vozes) % len(PALETA)]
        v = vozes[quem]; return dict(speed=v["speed"], P=v["P"], narr=False)
    m      = carregar_omni()
    prompt = _criar_prompt_voz(m, perfil)
    cfg    = _cfg(); segs = []; roteiro = []; quem_seg = []
    for i, ((eh_fala, txt), (quem, emo)) in enumerate(zip(beats, tags)):
        v = voz_de(quem); d = EMO.get(emo, EMO["neutra"])
        if v["narr"]:
            speed = v["speed"]; tom = 1.0; vol = float(np.clip(d["vol"], 0.82, 1.08))
        else:
            speed = v["speed"] * d["s"]; tom = v["P"] * d["p"]; vol = d["vol"]
        speed *= ritmo                                     # controle global de ritmo da narração
        if i == 0:
            speed *= 0.82                                  # 1ª frase: mais lenta e lúdica ("Era uma vez...")
        elif i == len(beats) - 1:
            speed *= 0.85                                  # última frase: desacelera p/ fechar a história
        progresso(0.10 + 0.85 * i / max(1, len(beats)),
                  f"Gerando {i+1}/{len(beats)} [{quem}:{emo}]")
        seg = _gerar_um(m, cfg, prompt, txt, speed, tom, vol)
        if sussurro:
            seg = _sussurro(seg)
        segs.append(seg)
        roteiro.append((quem, emo, txt)); quem_seg.append(quem)
    descarregar_omni()
    audio = _montar(segs, quem_seg)
    if musica_path and vol_fundo > 0:
        progresso(0.98, "Misturando áudio de fundo...")
        audio = _misturar_fundo(audio, _carregar_fundo(musica_path, vol_fundo), cauda_fundo)
    return audio, roteiro

# ── "Hora da loucura": a IA inventa um roteiro de programa inteiro ─────────────
# Convidados do SUBMUNDO (sem nada musical — a IA não canta).
_LOUCURA_CONVIDADOS = [
    "um lobisomem desempregado que não assusta mais ninguém",
    "um fantasma que morre de medo do escuro",
    "uma bruxa cujas poções sempre dão errado",
    "um vampiro vegetariano com anemia",
    "um zumbi que vive perdendo os próprios membros",
    "um diabinho estagiário muito atrapalhado",
    "uma alma penada reclamona que acha tudo um saco",
    "um esqueleto que cai aos pedaços a cada movimento",
    "um capeta aposentado que virou coach de positividade",
    "uma múmia com uma terrível dor nas costas",
    "um ceifador que perdeu a própria foice",
    "um gato preto que só dá azar para si mesmo",
]

def _limpar_roteiro(txt):
    """Deixa só o roteiro: tira markdown (**, *, #), rubricas de ação entre parênteses
    (o TTS as leria), cercas de código e linhas de preâmbulo."""
    out = []
    for ln in (txt or "").splitlines():
        s = ln.replace("```", "")
        s = re.sub(r"[*_#`]+", "", s)              # markdown
        s = re.sub(r"\([^)]*\)", "", s)            # rubricas de ação: (canta), (cai)...
        s = re.sub(r"\s+", " ", s).strip()
        if not s:
            continue
        if re.match(r"^(claro|aqui está|aqui vai|segue|com certeza|roteiro)\b", s, re.I) and len(s) < 45:
            continue                               # preâmbulo da IA
        out.append(s)
    return "\n".join(out).strip()

def gerar_roteiro_comedia(num_predict=1400):
    """Inventa um roteiro de programa de auditório (estilo Ratinho) no formato com rótulos
    (apresentador SEM rótulo; convidado 'NOME: fala'). Varia a cada clique (temperatura alta
    + 3 convidados sorteados). Usado pelo botão 'Hora da loucura' do estúdio."""
    ideias = "; ".join(random.sample(_LOUCURA_CONVIDADOS, 3))
    p = ("Escreva o roteiro de um programa de auditório de comédia do SUBMUNDO, apresentado pela "
         "PANDORA, a secretária e sacerdotisa do senhor Hades. Tom sombrio e macabro, MAS muito "
         "engraçado, debochado e sarcástico.\n\n"
         "A PANDORA:\n"
         "- É ULTRA animada e elétrica — ela 'bota fogo' na plateia (afinal, é o inferno).\n"
         "- Tem um lado fúnebre e maligno, mas é piadista e SARCÁSTICA com os convidados, rindo "
         "das desgraças deles e fazendo da vida deles um inferno.\n"
         "- No INÍCIO ela SE APRESENTA (nome e cargo no submundo) e anima a plateia de almas penadas.\n"
         "- No FIM ela manda um RECADO macabro e engraçado e se despede.\n\n"
         "FORMATO OBRIGATÓRIO:\n"
         "- As falas da PANDORA (apresentadora) vão em linhas normais, SEM rótulo.\n"
         "- As falas de um CONVIDADO começam com o NOME em MAIÚSCULAS e dois-pontos, ex.: "
         "'RUFUS: Boa noite...'. Nomes curtos, de uma palavra só. NÃO ponha rótulo na Pandora.\n"
         "- Uma fala por linha. NÃO escreva ações entre parênteses, NÃO use asteriscos.\n\n"
         "O QUE PRECISA TER:\n"
         "- 2 ou 3 convidados (almas/criaturas do submundo), cada um com uma ATRAÇÃO e um "
         "PROBLEMA cômico (algo dá muito errado).\n"
         "- A Pandora atormentando e zoando cada convidado com tiradas afiadas.\n"
         "- PODE ter um quadro de jogo macabro (ex.: a Roleta do Hades).\n"
         "- PROIBIDO qualquer atração musical ou personagem cantando (não temos canto).\n"
         f"- Convidados de inspiração (invente os nomes próprios): {ideias}.\n"
         "Escreva de 30 a 45 linhas. Português do Brasil. Responda SÓ o roteiro, sem comentários.\n\n"
         "ROTEIRO:\n")
    txt = _gemma(p, num_predict=num_predict, num_ctx=4096, temperature=1.0)
    descarregar_gemma()
    return _limpar_roteiro(txt)

# ── Game Show EDUCATIVO a partir de PDF (aba separada; reusa a Comédia) ────────
MAX_PDF_CHARS = 8000     # a Gemma 4B tem contexto limitado — pega o começo do material

def _ler_pdf(path):
    """Extrai o texto de um PDF (pypdf). Retorna (texto, n_paginas, truncado)."""
    from pypdf import PdfReader
    reader = PdfReader(path)
    partes = []
    for pg in reader.pages:
        try:
            t = pg.extract_text() or ""
        except Exception:
            t = ""
        if t.strip():
            partes.append(t)
    texto = re.sub(r"[ \t]+", " ", "\n".join(partes))
    texto = re.sub(r"\n{3,}", "\n\n", texto).strip()
    truncado = len(texto) > MAX_PDF_CHARS
    return (texto[:MAX_PDF_CHARS] if truncado else texto), len(reader.pages), truncado

def gerar_gameshow_educativo(conteudo, faixa="crianças de 7 a 10 anos",
                             n_perguntas=5, num_predict=1800):
    """Cria um roteiro de QUIZ GAME SHOW educativo a partir do conteúdo (texto de um PDF),
    apresentado pela Pandora (sarcástica/macabra, MAS ensinando certo). Mesmo formato com
    rótulos da Comédia (Pandora sem rótulo; convidado 'NOME: fala'). Reusa _limpar_roteiro."""
    conteudo = (conteudo or "").strip()
    if not conteudo:
        return ""
    p = ("Você vai criar o roteiro de um GAME SHOW de quiz EDUCATIVO para " + faixa + ", "
         "apresentado pela PANDORA, a secretária do senhor Hades — sombria, debochada e "
         "sarcástica, mas que ENSINA de verdade e com carinho pelas crianças.\n\n"
         "MATERIAL DE ESTUDO (baseie-se SOMENTE nos fatos abaixo; NÃO invente informação):\n"
         '"""\n' + conteudo + '\n"""\n\n'
         "COMO É O PROGRAMA:\n"
         "- A Pandora abre se apresentando e anunciando o tema do material, de um jeito divertido.\n"
         "- Ela ENSINA os pontos principais do material, de forma clara e correta para " + faixa + ".\n"
         f"- Ela faz {n_perguntas} PERGUNTAS de quiz sobre o material, uma de cada vez.\n"
         "- Convidados (personagens engraçados) respondem: alguns ACERTAM, outros ERRAM. A Pandora "
         "zoa quem erra (sarcasmo leve, nada cruel) e SEMPRE diz a resposta CERTA e explica "
         "rapidinho — a criança precisa aprender de verdade.\n"
         "- No fim, ela faz um resuminho do que foi aprendido e manda um recado divertido.\n\n"
         "FORMATO OBRIGATÓRIO:\n"
         "- Falas da PANDORA (apresentadora): linhas normais, SEM rótulo.\n"
         "- Falas de um CONVIDADO: comece com o NOME em MAIÚSCULAS e dois-pontos, ex.: "
         "'TODD: É o Sol!'. Nomes curtos, uma palavra. NÃO rotule a Pandora.\n"
         "- Uma fala por linha. NADA de ações entre parênteses, NADA de asteriscos, NADA musical.\n\n"
         "Português do Brasil. Responda SÓ o roteiro.\n\nROTEIRO:\n")
    txt = _gemma(p, num_predict=num_predict, num_ctx=8192, temperature=0.7)
    descarregar_gemma()
    return _limpar_roteiro(txt)

def sintetizar_comedia(perfil, texto, ritmo=1.0, vol_sfx=0.6, vol_plateia=0.06,
                       intensidade=1.0, abertura_path=None, vol_abertura=0.85,
                       progresso=lambda *a: None):
    """Versão COMÉDIA — programa de auditório (estilo Ratinho) com SONOPLASTIA.
    Roteiro com RÓTULO de falante: 'NOME: fala' = convidado (voz própria, consistente);
    linha SEM rótulo = apresentador (voz base). `_beats_comedia` parseia; a Gemma dá só a
    EMOÇÃO (`_emocao_lote`) e marca os efeitos (`_classificar_sfx`) antes de descarregar;
    o OmniVoice sintetiza; `_montar_comedia` intercala os efeitos + plateia de fundo.
    Os efeitos vêm de app/estudio/sonoplastia/ (usa só o que existir).
    Retorna (audio, roteiro), roteiro = [(quem, emocao, texto, efeito)]."""
    beats, falantes = _beats_comedia(texto)
    if not beats:
        return np.zeros(1, dtype=np.float32), []
    catalogo    = _catalogo_sfx()
    disponiveis = list(catalogo.keys())
    progresso(0.05, "Lendo o quadro (emoção das falas)...")
    emos = _emocao_lote(beats)
    progresso(0.15, "Marcando a sonoplastia...")
    sfx_seq = (_classificar_sfx(beats, disponiveis, intensidade) if disponiveis
               else [("nenhum", "depois") for _ in beats])
    descarregar_gemma()
    # plateia de fundo (se houver arquivo com nome-chave de plateia)
    plateia_wav = None
    if vol_plateia > 0:
        for nome in _PLATEIA_NOMES:
            if nome in catalogo:
                plateia_wav = _carregar_sfx(catalogo[nome], vol_plateia); break
    vozes = {}
    def voz_de(quem):
        if quem in ("narrador", "narradora", "narra", ""):
            return dict(speed=perfil["base_speed"], P=1.0, narr=True)
        if quem not in vozes: vozes[quem] = PALETA[len(vozes) % len(PALETA)]
        v = vozes[quem]; return dict(speed=v["speed"], P=v["P"], narr=False)
    m           = carregar_omni()
    prompt_base = _criar_prompt_voz(m, perfil)
    emo_prompts = _carregar_prompts_emocao(m, perfil)   # {emo: prompt} de clips em vozes/emocoes/
    cfg         = _cfg(); segs = []; roteiro = []; quem_seg = []
    for i, ((eh_fala, txt), quem, emo) in enumerate(zip(beats, falantes, emos)):
        v = voz_de(quem); d = EMO.get(emo, EMO["neutra"])
        if v["narr"]:                          # apresentadora (Pandora): EXPRESSIVA e animada,
            speed = v["speed"] * d["s"]; tom = 1.0; vol = d["vol"]   # mas sem pitch (timbre fixo)
            prompt = emo_prompts.get(emo, prompt_base)  # clip emocional se disponível
        else:
            speed = v["speed"] * d["s"]; tom = v["P"] * d["p"]; vol = d["vol"]
            prompt = prompt_base
        speed *= ritmo
        if i == 0:               speed *= 0.82
        elif i == len(beats) - 1: speed *= 0.85
        progresso(0.20 + 0.75 * i / max(1, len(beats)),
                  f"Gerando {i+1}/{len(beats)} [{quem}:{emo}]")
        seg = _gerar_um(m, cfg, prompt, txt, speed, tom, vol)
        # DSP emocional: espectro + tremolo + eco (pós-síntese, custo zero de VRAM)
        b = d.get("brilho", 1.0)
        if b != 1.0:              seg = _brilho(seg, b)
        if d.get("tremolo", 0.0): seg = _tremolo(seg, d["tremolo"])
        if d.get("eco", False):   seg = _eco(seg)
        segs.append(seg); quem_seg.append(quem)
        efe = sfx_seq[i][0] if i < len(sfx_seq) else "nenhum"
        roteiro.append((quem, emo, txt, efe))
    descarregar_omni()
    audio = _montar_comedia(segs, quem_seg, sfx_seq, catalogo, vol_sfx, plateia_wav, vol_plateia)
    # música de abertura opcional (toca antes do programa, com fade-out)
    if abertura_path and vol_abertura > 0:
        ab = _carregar_fundo(abertura_path, vol_abertura)
        if ab is not None and len(ab):
            f = min(int(1.2 * SR), len(ab) // 3)
            if f > 1: ab[-f:] *= np.linspace(1, 0, f)
            gap = np.zeros(int(0.3 * SR), dtype=np.float32)
            audio = np.concatenate([ab.astype(np.float32), gap, audio]).astype(np.float32)
    return audio, roteiro

def salvar(audio, nome="saida.wav"):
    d = os.path.join(PASTA, "saidas"); os.makedirs(d, exist_ok=True)
    p = os.path.join(d, nome); sf.write(p, audio, SR, subtype="PCM_16"); return p

# ── Gemma — inferência para Contador de Histórias ────────────────────────────
def _achar_emocao(txt):
    t = txt.lower()
    for e in EMO_LISTA:
        if re.search(r"\b" + re.escape(e), t): return e
    return "neutra"

def _split_frases(t):
    t = (t or "").strip()
    return [s.strip() for s in re.split(r"(?<=[.!?…])\s+", t) if s.strip()]

def _beats_historia(texto):
    """Segmenta a história em beats por locutor. Reconhece diálogo por ASPAS
    (curvas “ ” ou retas ") e por TRAVESSÃO (–, —, ' - '): o que está dentro das
    aspas / entre travessões é fala de personagem; o resto (narração e tags de
    atribuição como 'perguntou o lobo') é narração, quebrada em frases.
    Retorna lista de (eh_fala, texto). Preserva as quebras de linha."""
    beats = []
    for bloco in texto.splitlines():
        bloco = bloco.strip()
        if not bloco:
            continue
        norm = re.sub(r'[“”„«»]', '"', bloco)              # aspas curvas/angulares → aspa reta
        if '"' in norm:                                     # diálogo por ASPAS
            for i, p in enumerate(norm.split('"')):
                if i % 2 == 1:                              # dentro das aspas = fala
                    p = p.strip()
                    if p: beats.append((True, p))
                else:                                       # fora das aspas = narração (em frases)
                    beats += [(False, fr) for fr in _split_frases(p)]
        else:
            n2 = norm.replace("—", "–")
            n2 = re.sub(r"(?<=\s)-(?=\s)", "–", n2)         # hífen entre espaços = travessão
            if "–" in n2:                                   # diálogo por TRAVESSÃO
                for i, p in enumerate(n2.split("–")):
                    p = p.strip(" ,;:")
                    if p: beats.append((i % 2 == 1, p))
            else:                                           # narração pura (em frases)
                beats += [(False, fr) for fr in _split_frases(n2)]
    return beats

# Roteiro de programa (modalidade Comédia): rótulo de falante por linha.
_ROTULO_RE   = re.compile(r"^\s*([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ .]{0,18}?):\s+(.+)$")
_FALANTE_BASE = {"apresentador", "apresentadora", "pandora", "narrador", "narradora",
                 "host", "animador", "animadora", "plateia", "publico", "auditorio", "audiencia"}

def _beats_comedia(texto):
    """Parser de roteiro de auditório. Linha 'NOME: fala' = convidado (voz própria,
    consistente); linha SEM rótulo = apresentador (voz base). Elimina a adivinhação de
    quem fala. Retorna (beats, falantes) — beats=[(eh_fala, texto)] paralelo a falantes."""
    beats, falantes = [], []
    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha:
            continue
        m = _ROTULO_RE.match(linha)
        nome = _norm_nome(m.group(1)) if m else ""
        # apresentador = sem rótulo, ou rótulo base (apresentador/narrador/plateia + typos)
        base = bool(nome) and (nome in _FALANTE_BASE or nome.startswith(("apres", "narr", "anim", "host")))
        if m and nome and not base:
            beats.append((True, m.group(2).strip())); falantes.append(nome)
        else:
            fala = m.group(2).strip() if (m and base) else linha
            for fr in _split_frases(fala):
                beats.append((False, fr)); falantes.append("narrador")
    return beats, falantes

def _ascii1(w):
    """Normaliza UMA palavra: sem acento, minúscula, só letras."""
    q = unicodedata.normalize("NFKD", w or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]", "", q)

def _norm_nome(quem):
    """Normaliza o nome do personagem p/ um timbre consistente: sem acento, sem
    artigo, só a primeira palavra (ex: 'o lobo disfarçado' → 'lobo')."""
    q = unicodedata.normalize("NFKD", quem or "").encode("ascii", "ignore").decode().lower()
    q = re.sub(r"[^a-z\s]", " ", q)
    q = re.sub(r"^\s*(?:o|a|os|as|um|uma|sua|seu|meu|minha)\s+", "", q).strip()
    return q.split()[0][:16] if q.split() else ""

# Extração determinística do falante a partir da tag de narração ("perguntou o lobo").
_VERBOS_FALA = ("disse|falou|respondeu|perguntou|gritou|exclamou|rosnou|murmurou|"
    "sussurrou|mentiu|agradeceu|continuou|retrucou|replicou|indagou|berrou|chamou|"
    "ordenou|pediu|contou|avisou|explicou|comentou|declarou|afirmou|sugeriu|repetiu|"
    "acrescentou|concluiu|completou|observou|insistiu|gemeu|chorou|riu|brincou|"
    "prosseguiu|emendou|imitou|prometeu|respondia|dizia|perguntava")
_ART_PREP = {"o","a","os","as","um","uma","sua","seu","suas","seus","meu","minha",
             "este","esta","aquele","aquela","ao","aos","de","da","do","das","dos",
             "com","em","para","que"}
_PRON_SUJ = {"ele","ela","eles","elas","lhe","me","se","te","nos","eu","tu","voce"}
# formas verbais dicendi (infinitivo/gerúndio) e adjuntos adverbiais — nunca são nome
_PULAR_NOME = {"perguntar","dizer","falar","responder","contar","gritar","exclamar",
    "rosnar","sussurrar","perguntando","dizendo","tentando","soar","ainda","dia","dias",
    "vez","noite","manha","tarde","hora","momento","instante","entao","depois","logo",
    "antes","assim","repente","seguida","enquanto","fim","partir"}

def _primeiro_nome(palavras):
    for w in palavras:
        n = _ascii1(w)
        if not n: continue
        if n in _PRON_SUJ: return ""        # sujeito pronominal → não dá p/ deduzir
        if n in _ART_PREP or n in _PULAR_NOME: continue
        return n[:16]
    return ""

def _falante_da_tag(tag, pos):
    """Extrai o personagem de uma tag de narração. pos='depois' → tag após a fala
    ('perguntou o lobo'); pos='antes' → tag antes da fala ('sua mãe disse:')."""
    t = (tag or "").strip()
    if pos == "depois":
        m = re.search(r"\b(?:" + _VERBOS_FALA + r")\b\s+(.+)", t, re.IGNORECASE)
        return _primeiro_nome(re.findall(r"[A-Za-zÀ-ÿ]+", m.group(1))) if m else ""
    m = re.search(r"^(.*?)\b(?:" + _VERBOS_FALA + r")\b", t, re.IGNORECASE)
    trecho = m.group(1) if m else t
    pals = re.findall(r"[A-Za-zÀ-ÿ]+", trecho)
    if any(_ascii1(w) in _PRON_SUJ for w in pals): return ""   # sujeito pronominal
    return _primeiro_nome(pals)

def _quem_fala_gemma(beats, i, elenco):
    """Pergunta FOCADA à gemma: quem pronuncia a fala do beat i, vendo o contexto
    ao redor. Usada só quando a tag não resolve (sujeito pronominal, imitação,
    disfarce). Instrui a gemma a apontar o IMPOSTOR, não quem ele finge ser."""
    ini = max(0, i - 8); fim = min(len(beats), i + 3)
    ctx = []
    for k in range(ini, fim):
        ef, t = beats[k]
        marca = ">>> FALA:" if k == i else ("fala:" if ef else "narracao:")
        ctx.append(f"{marca} {t}")
    lista = ", ".join(sorted(elenco)) if elenco else "(deduza pelo trecho)"
    p = ("Leia o trecho de uma história e diga QUEM pronuncia a fala marcada com '>>>'.\n"
         "Se um personagem IMITA ou se DISFARÇA de outro, responda quem REALMENTE fala "
         "(o impostor), não quem ele finge ser.\n"
         f"Personagens já conhecidos: {lista}. Se for OUTRO personagem que apareça no "
         "trecho (ex: caçador), pode responder o nome dele.\n"
         "Responda só o nome curto do personagem, em uma palavra.\n\n"
         + "\n".join(ctx) + "\n\nQuem fala a linha marcada com >>>? Nome:")
    try:
        return _norm_nome(_gemma(p, 12, num_ctx=2048))
    except Exception:
        return ""

_LOTE_CLASSIF = 12   # gemma3:4b perde precisão (e estoura contexto) com listas longas

def _classificar_beats(beats):
    """Decide (quem, emocao) de cada beat, em LOTES pequenos. Narração → 'narrador';
    para as falas, deduz o personagem pela tag vizinha. Nomes normalizados p/ manter
    o timbre consistente entre lotes."""
    if not beats: return []
    res = [("narrador", "neutra") for _ in beats]
    for ini in range(0, len(beats), _LOTE_CLASSIF):
        lote = beats[ini:ini + _LOTE_CLASSIF]
        enum = "\n".join(
            f"{j+1}. [{'FALA' if eh_fala else 'NARRACAO'}] {txt}"
            for j, (eh_fala, txt) in enumerate(lote))
        p = ("Você prepara uma história para narração com vozes.\n"
             "Para CADA item diga QUEM fala e a EMOÇÃO.\n"
             "Itens [NARRACAO] são do narrador: responda 'narrador'.\n"
             "Itens [FALA] são fala de um personagem: dê o nome curto do personagem "
             "(ex: lobo, chapeuzinho, mae, vovo, cacador), deduzindo pelo contexto e "
             "pelas tags de atribuição vizinhas (ex: 'perguntou o lobo').\n"
             f"EMOÇÃO = uma de: {', '.join(EMO_LISTA)}.\n"
             "Uma linha por item, no formato: NUMERO: quem ; emocao\n\n"
             + enum + "\n\nRespostas:")
        try:
            saida = _gemma(p, 16 * len(lote) + 40, num_ctx=4096)
        except Exception:
            continue
        for ln in saida.splitlines():
            m = re.match(r"\s*(\d+)\s*[:.)\-]\s*(.+)", ln)
            if not m: continue
            j = int(m.group(1)) - 1
            if not (0 <= j < len(lote)): continue
            corpo = m.group(2); quem, _, emo = corpo.partition(";")
            idx = ini + j; emocao = _achar_emocao(emo or corpo)
            if not lote[j][0]:                          # beat de narração → narrador
                res[idx] = ("narrador", emocao)
            else:
                res[idx] = (_norm_nome(quem) or "personagem", emocao)
    # passo 1: o 'quem' das falas vem da tag de narração vizinha (determinístico,
    # mais confiável que a gemma) e monta o elenco de personagens.
    falante = {}
    for i, (eh_fala, _) in enumerate(beats):
        if not eh_fala:
            continue
        nome = ""
        if i + 1 < len(beats) and not beats[i + 1][0]:               # tag depois da fala
            nome = _falante_da_tag(beats[i + 1][1], "depois")
        if not nome and i - 1 >= 0 and not beats[i - 1][0]:
            prev = beats[i - 1][1].rstrip()
            # tag antes (introduz com ':') ou fala continuada ('disse X. "...".')
            nome = _falante_da_tag(prev, "antes" if prev.endswith(":") else "depois")
        if nome:
            falante[i] = nome
    elenco = set(falante.values())

    # passo 2: falas sem tag clara → gemma FOCADA por caso (entende imitação/disfarce);
    # rastreio do personagem ativo em cena é o último fallback.
    ativo = ""
    for i, (eh_fala, txt) in enumerate(beats):
        if not eh_fala:
            for w in re.findall(r"[A-Za-zÀ-ÿ]+", txt):               # sujeito ≈ 1º nome do elenco citado
                if _ascii1(w) in elenco:
                    ativo = _ascii1(w); break
            continue
        nome = falante.get(i)
        if not nome:                                                 # tag não resolveu
            nome = _quem_fala_gemma(beats, i, elenco) or ativo
        if nome:
            res[i] = (nome, res[i][1])                               # mantém emoção da gemma
        ativo = nome or ativo
    return res

def _emocao_lote(beats):
    """Só a EMOÇÃO de cada beat (o falante já vem do rótulo do roteiro). Lotes de 12."""
    res = ["neutra" for _ in beats]
    for ini in range(0, len(beats), _LOTE_CLASSIF):
        lote = beats[ini:ini + _LOTE_CLASSIF]
        enum = "\n".join(f"{j+1}. {t}" for j, (ef, t) in enumerate(lote))
        p = ("Para cada fala de um programa de auditório, diga a EMOÇÃO dominante.\n"
             f"EMOÇÃO = uma de: {', '.join(EMO_LISTA)}.\n"
             "Uma linha por item, no formato: NUMERO: emocao\n\n" + enum + "\n\nRespostas:")
        try:
            saida = _gemma(p, 8 * len(lote) + 30, num_ctx=4096)
        except Exception:
            continue
        for ln in saida.splitlines():
            m = re.match(r"\s*(\d+)\s*[:.)\-]\s*(.+)", ln)
            if not m: continue
            j = int(m.group(1)) - 1
            if 0 <= j < len(lote): res[ini + j] = _achar_emocao(m.group(2))
    return res

def _classificar_sfx(beats, disponiveis, intensidade=1.0):
    """O 'sonoplasta' (Gemma): por beat, escolhe um efeito (dentre os DISPONÍVEIS) e a
    posição (antes/depois/sob), ou 'nenhum'. Lotes de 12, igual _classificar_beats.
    intensidade: 0..2 — regula a frequência (instrução + pós-filtro de densidade)."""
    vazio = [("nenhum", "depois") for _ in beats]
    pontuais = [d for d in disponiveis if d not in _PLATEIA_NOMES]
    if not beats or not pontuais:
        return vazio
    desc = "\n".join(
        f"- {d}: {DESCR_SFX.get(d.split()[0] if d.split() else d, 'use quando combinar com o nome')}"
        for d in pontuais)
    nivel = ("com MUITA frequência, programa bem animado"   if intensidade >= 1.5 else
             "com parcimônia, só nos momentos de impacto"    if intensidade <= 0.6 else
             "nos bons momentos, sem exagerar")
    res = list(vazio)
    for ini in range(0, len(beats), _LOTE_CLASSIF):
        lote = beats[ini:ini + _LOTE_CLASSIF]
        enum = "\n".join(f"{j+1}. [{'FALA' if ef else 'NARRACAO'}] {t}"
                         for j, (ef, t) in enumerate(lote))
        p = ("Você é o SONOPLASTA de um programa de auditório de comédia (estilo Ratinho).\n"
             "A apresentadora é debochada e MALDOSA: ela RI dos convidados e dos micos deles — "
             "use 'risada' bastante (depois das tiradas dela e das desgraças dos convidados). "
             "Quando a fala pede ou menciona palmas/aplauso, use 'aplauso'.\n"
             "Para CADA item, decida se entra um EFEITO e qual, escolhendo SÓ entre os "
             "disponíveis abaixo:\n" + desc + "\n"
             "Posição: 'antes' (suspense antes de revelar), 'depois' (reação à fala). "
             "Se não precisar, responda 'nenhum'.\n"
             f"Use efeitos {nivel}. Efeito demais cansa.\n"
             "Uma linha por item, no formato: NUMERO: efeito ; posicao\n\n"
             + enum + "\n\nRespostas:")
        try:
            saida = _gemma(p, 16 * len(lote) + 40, num_ctx=4096)
        except Exception:
            continue
        for ln in saida.splitlines():
            m = re.match(r"\s*(\d+)\s*[:.)\-]\s*(.+)", ln)
            if not m: continue
            j = int(m.group(1)) - 1
            if not (0 <= j < len(lote)): continue
            efe, _, pos = m.group(2).partition(";")
            efe = _norm_sfx(efe); pos = _norm_sfx(pos)
            pos = pos if pos in ("antes", "depois", "sob") else "depois"
            achou = ""
            for d in pontuais:                                  # casa contra os disponíveis
                if d == efe or (efe and (d in efe or efe in d)):
                    achou = d; break
            # posição FIXA por tipo (corrige "palmas tocando antes da fala")
            if achou:
                pos = POSICAO_SFX.get(achou.split()[0] if achou.split() else achou, pos)
            res[ini + j] = (achou or "nenhum", pos)
    # pós-filtro de densidade: evita efeitos colados (gap por intensidade)
    gap = 3 if intensidade <= 0.6 else (0 if intensidade >= 1.5 else 1)
    if gap:
        ult = -99
        for i, (e, pos) in enumerate(res):
            if e != "nenhum":
                if i - ult <= gap: res[i] = ("nenhum", pos)
                else:              ult = i
    # reforço DETERMINÍSTICO: quando a fala PEDE um efeito, força (mesmo se a Gemma falhou)
    _GATILHOS = [(("palma", "aplaus", "salva de"), "aplauso"),
                 (("suspense", "segura", "rufem", "prepar", "tambor"), "rufar"),
                 (("gargalha", "risada", "rir "), "risada")]
    for i, (eh, t) in enumerate(beats):
        tl = unicodedata.normalize("NFKD", t.lower()).encode("ascii", "ignore").decode()
        for chaves, efe in _GATILHOS:
            if any(k in tl for k in chaves):
                alvo = efe if efe in pontuais else next(
                    (d for d in pontuais if efe in d or d in efe), "")
                if alvo:
                    res[i] = (alvo, POSICAO_SFX.get(alvo, "depois"))
                break
    return res
