# -*- coding: utf-8 -*-
"""Motor do Estúdio v2 — OmniVoice + Gemma (Ollama) — VERSÃO EXPANDIDA COM NOVAS ABAS
Ciclo de memória: gemma infere → descarrega → OmniVoice sintetiza → descarrega.
Roda com 6 GB VRAM (RTX 2060) — os dois modelos nunca coexistem.

NOVAS FUNÇÕES V2:
- interpretar_descricao_voz() — Design de voz com linguagem natural
- gerar_roteiro_trailer() — Trailer de cinema épico
- gerar_meditacao() — Meditação guiada com pausas
- gerar_radio() — Episódio de rádio completo (5 segmentos)
- gerar_batalha() — Duas vozes debatem
- responder_personagem() — Conversa interativa
- gerar_livro_capitulos() — Audiolivro por capítulos
- gerar_temporada() — N episódios com continuidade
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

def _esperar_vram_livre(min_gb=3.0, timeout=25):
    """Aguarda a VRAM livre subir acima de min_gb (ex.: após o Ollama liberar a
    Gemma) antes de carregar o OmniVoice. Evita o offload para CPU que deixa a
    síntese lentíssima na RTX 2060 6GB. Se estourar o timeout, segue mesmo assim."""
    import time
    if not torch.cuda.is_available():
        return
    alvo = min_gb * (1024 ** 3)
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            free, _total = torch.cuda.mem_get_info()
        except Exception:
            time.sleep(1); continue
        if free >= alvo:
            return
        time.sleep(1)
    livre_gb = free / (1024 ** 3) if 'free' in dir() else 0
    print(f"[vram] timeout esperando VRAM livre (~{livre_gb:.1f}GB) — seguindo assim mesmo.", flush=True)

def carregar_omni():
    global _MODEL
    if _MODEL is None:
        from omnivoice import OmniVoice
        print("Carregando OmniVoice...", flush=True)
        _MODEL = OmniVoice.from_pretrained(
            "k2-fsa/OmniVoice",
            device_map="auto",
            dtype=torch.float16,
            load_asr=False,
            token=False,
            attn_implementation="sdpa",  # +24% mais rápido (testado na RTX 2060)
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
        postprocess_output=False,
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
    torch.cuda.empty_cache()
    # Espera a VRAM ser realmente liberada pelo Ollama (em vez de um sleep fixo)
    _esperar_vram_livre(min_gb=3.0, timeout=25)

# ── Emoções ──────────────────────────────────────────────────────────────────
EMO = {
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
    f = min(int(SR * ms / 1000), len(x))
    if f > 1:
        g = np.exp(-4.0 * np.linspace(0, 1, f)); g = (g - g[-1]) / (g[0] - g[-1])
        x[-f:] *= g
    return x

def _zcr(x):
    if len(x) < 2: return 0.0
    return float(np.mean(np.abs(np.diff(np.sign(x + 1e-12))) > 0))

def finalizar(x):
    x = np.asarray(x, dtype=np.float32)
    win = int(0.02 * SR)
    env = _envelope(x, win); pico = env.max() or 1.0
    fala = np.where(env > pico * 10**(-35/20))[0]
    if len(fala):
        fim = min(len(x), (fala[-1] + 1) * win + int(0.09 * SR))
        ini = max(0, fala[0] * win - int(0.008 * SR))
        x = x[ini:fim]
    cauda = x[-int(0.04 * SR):] if len(x) > int(0.04 * SR) else x
    abr = min(1.0, (_rms(cauda) / pico) / 0.45)
    fade_ms = 260 + 220 * abr
    if _zcr(cauda) < 0.12:
        fade_ms *= 1.25
    fade_ms = min(fade_ms, 620)
    return _fade_exp(_fade_in_cos(x), fade_ms)

def _roomtone(n):
    w = np.random.randn(n).astype(np.float32); k = np.ones(80, dtype=np.float32) / 80
    rt = np.convolve(w, k, mode="same"); return rt / (np.max(np.abs(rt)) or 1) * 0.0035

def _sussurro(x):
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
    try:
        from scipy.ndimage import uniform_filter1d
        env = uniform_filter1d(mag, size=25, axis=0)
    except Exception:
        k = np.ones(25, dtype=np.float32) / 25
        env = np.stack([np.convolve(mag[:, c], k, mode="same") for c in range(mag.shape[1])], axis=1)
    ruido = np.random.rand(*mag.shape).astype(np.float32) + 0.5
    fase  = np.exp(2j * np.pi * np.random.rand(*mag.shape).astype(np.float32))
    y = librosa.istft(env * ruido * fase, hop_length=hop, length=len(x)).astype(np.float32)
    return y / (np.max(np.abs(y)) or 1) * 0.8

def _brilho(x, fator):
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
    if depth < 0.01 or len(x) < 2:
        return x
    t = np.arange(len(x), dtype=np.float32) / SR
    return (x * (1.0 + depth * np.sin(2.0 * np.pi * freq * t))).astype(np.float32)

def _eco(x, delay_ms=38, decay=0.22):
    delay = int(SR * delay_ms / 1000)
    if delay >= len(x):
        return x
    y = x.copy()
    y[delay:] += x[: len(x) - delay] * decay
    pico = np.max(np.abs(y)) or 1.0
    return (y / pico * (np.max(np.abs(x)) or 1.0)).astype(np.float32)

def _montar(segs, quem=None):
    if not segs:
        return np.zeros(1, dtype=np.float32)
    p_mesmo = np.zeros(int(0.09 * SR), dtype=np.float32)
    p_troca = np.zeros(int(0.24 * SR), dtype=np.float32)
    partes = [np.asarray(segs[0], dtype=np.float32)]
    for i in range(1, len(segs)):
        mesmo = quem is not None and quem[i] == quem[i - 1]
        partes.append((p_mesmo if mesmo else p_troca).copy())
        partes.append(np.asarray(segs[i], dtype=np.float32))
    voz = np.concatenate(partes)
    mix = voz + _roomtone(len(voz))
    return (mix / (np.max(np.abs(mix)) or 1) * 0.95).astype(np.float32)

def _carregar_fundo(path, volume):
    try:
        import librosa
        wav, _ = librosa.load(path, sr=SR, mono=True)
        wav = wav.astype(np.float32)
        return (wav / (np.max(np.abs(wav)) or 1.0)) * float(volume)
    except Exception as e:
        print(f"[fundo] não carregou '{path}': {e}", flush=True)
        return None

def _misturar_fundo(voz, fundo, cauda_seg=0.0):
    if fundo is None or len(fundo) == 0:
        return voz
    cauda  = max(0, int(round(cauda_seg * SR)))
    voz_ext = np.concatenate([voz, np.zeros(cauda, dtype=np.float32)])
    n = len(voz_ext)
    bg = np.tile(fundo, n // len(fundo) + 2)[:n].astype(np.float32)
    fade_in = min(int(SR * 4), n // 2)
    if fade_in > 1:
        bg[:fade_in] *= np.linspace(0, 1, fade_in)
    fade_out = min(int(SR * 4), cauda) if cauda > 0 else min(int(SR * 4), n // 2)
    if fade_out > 1:
        bg[-fade_out:] *= np.linspace(1, 0, fade_out)
    mix = voz_ext + bg
    return (mix / (np.max(np.abs(mix)) or 1) * 0.95).astype(np.float32)

# ── Sonoplastia ──────────────────────────────────────────────────────────────
PASTA_SFX = os.path.join(PASTA, "sonoplastia")
PASTA_EMO = os.path.join(PASTA, "vozes", "emocoes")
_PLATEIA_NOMES = ("plateia", "auditorio", "audiencia")

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

POSICAO_SFX = {
    "aplauso": "depois", "risada": "depois", "buzina": "depois", "trombone": "depois",
    "grilo": "depois", "vinheta": "depois",
    "rufar": "antes", "tambor": "antes", "tabor": "antes", "suspense": "antes", "apito": "antes",
}
_GATILHOS = [(("palma", "aplaus", "salva de"), "aplauso"),
             (("suspense", "segura", "rufem", "prepar", "tambor"), "rufar"),
             (("gargalha", "risada", "rir "), "risada")]
DUR_SFX_MAX = 2.5

def _norm_sfx(nome):
    q = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode().lower()
    q = re.sub(r"[_\-]+", " ", q)
    q = re.sub(r"[^a-z0-9 ]", "", q).strip()
    return re.sub(r"\s+", " ", q)

_SFX_CATALOGO: "dict | None" = None

def _catalogo_sfx():
    global _SFX_CATALOGO
    if _SFX_CATALOGO is not None:
        return _SFX_CATALOGO
    cat = {}
    if os.path.isdir(PASTA_SFX):
        for f in sorted(os.listdir(PASTA_SFX)):
            base, ext = os.path.splitext(f)
            if ext.lower() not in (".wav", ".mp3", ".ogg", ".flac", ".m4a"):
                continue
            nome = _norm_sfx(base)
            if nome and nome not in cat:
                cat[nome] = os.path.join(PASTA_SFX, f)
    _SFX_CATALOGO = cat
    return _SFX_CATALOGO

def _carregar_sfx(path, ganho=1.0, max_seg=0):
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
    p_mesmo = np.zeros(int(0.09 * SR), dtype=np.float32)
    p_troca = np.zeros(int(0.24 * SR), dtype=np.float32)
    p_sfx   = np.zeros(int(0.12 * SR), dtype=np.float32)
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
        if s is not None and pos == "sob":
            seg = seg.copy(); L = min(len(seg), len(s)); seg[:L] = seg[:L] + s[:L]
        partes.append(seg)
        if s is not None and pos == "depois":
            partes.append(p_sfx.copy()); partes.append(s)
    voz = np.concatenate(partes) if partes else np.zeros(1, dtype=np.float32)
    mix = voz + _roomtone(len(voz))
    if plateia_wav is not None and len(plateia_wav) > 0:
        return _misturar_fundo(mix, plateia_wav)
    return (mix / (np.max(np.abs(mix)) or 1) * 0.95).astype(np.float32)

def _normalizar_fala(txt):
    txt = (txt or "")
    txt = txt.replace("—", " , ").replace("–", " , ")
    txt = re.sub(r"(?<=\s)-(?=\s)", ",", txt)
    txt = re.sub(r"^[\s,;:.\-]+", "", txt)
    txt = re.sub(r"\s+([,.!?;:])", r"\1", txt)
    txt = re.sub(r"([:;.!?])\s*,", r"\1", txt)
    txt = re.sub(r"(,\s*){2,}", ", ", txt)
    return re.sub(r"\s+", " ", txt).strip()

def _com_ponto(txt):
    txt = _normalizar_fala(txt)
    return txt if (txt and txt[-1] in ".!?…") else txt + "."

def _saida(wav):
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
    ref_text = perfil.get("ref_text")
    if not ref_text:
        cache = perfil.get("txt_cache")
        if cache and os.path.exists(cache):
            cached = open(cache, encoding="utf-8").read().strip()
            if cached:
                ref_text = cached; perfil["ref_text"] = cached
    return m.create_voice_clone_prompt(ref_audio=perfil["ref"], ref_text=ref_text or "")

def perfil_de_design(instruct, seed_text=None):
    """Cria um perfil de clone TRAVADO a partir de uma voz de DESIGN.
    O modo design (instruct) gera um timbre NOVO a cada chamada; para manter a
    MESMA voz em várias falas (ex.: um personagem do Battle, um convidado fixo),
    geramos uma frase-semente uma única vez com o instruct e usamos esse áudio
    como referência fixa de clone. Todas as falas seguintes clonam essa semente."""
    seed_text = seed_text or ("Olá. Este é o meu tom de voz natural para participar "
                              "desta conversa de hoje, com calma e bastante clareza.")
    audio = sintetizar_design(instruct or "moderate pitch", seed_text, "pt", 32, 3.0, 1.0)
    import tempfile
    pasta_tmp = os.path.join(PASTA, "saidas")
    os.makedirs(pasta_tmp, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav", dir=pasta_tmp)
    tmp.close()
    sf.write(tmp.name, np.asarray(audio, dtype=np.float32), SR)
    return perfil_voz(tmp.name, ref_text=seed_text)

def _carregar_prompts_emocao(m, perfil_base):
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

# ── Síntese de um trecho ─────────────────────────────────────────────────────
def _gerar_um(m, cfg, prompt, txt, speed, tom, vol, language="pt"):
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

# ── API pública (funções existentes) ────────────────────────────────────────
def sintetizar_clone(perfil, texto, language="pt",
                     num_step=32, guidance_scale=3.0, speed_mult=1.0,
                     progresso=lambda *a: None):
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
    # OmniVoice fica residente (recarga é cara) — liberado só quando a Gemma precisa.
    return _saida(wav)

# Curva de decaimento final extraída da Pandora.wav (referência humana) — usada
# para espelhar o "caimento" natural no fim das falas, em vez do corte seco do OmniVoice.
_CURVA_CAIMENTO = np.array([1.0, 0.78, 0.66, 0.43, 0.31, 0.13, 0.04, 0.02], dtype=np.float32)
_BINAURAL_SOS: "object" = None  # cached — recalcular é caro, parâmetros fixos

def _binaural_widen(y, sr=44100, delay_ms=0.35, lp_hz=9000):
    """Pseudo-estéreo binaural leve: canal R atrasado ~0.35ms + LP suave.
    Haas effect cria separação entre orelhas sem time-stretch ou reverb pesado.
    Entrada: mono float32 1-D. Saída: (T, 2) float32 estéreo."""
    global _BINAURAL_SOS
    from scipy.signal import butter, sosfilt
    if _BINAURAL_SOS is None:
        _BINAURAL_SOS = butter(2, lp_hz, btype='low', fs=sr, output='sos')
    delay_samp = max(1, int(sr * delay_ms / 1000))
    L = y.copy()
    R = np.concatenate([np.zeros(delay_samp, dtype=np.float32), y[:-delay_samp]])
    R = sosfilt(_BINAURAL_SOS, R).astype(np.float32)
    # _rms tem epsilon 1e-9 interno — sempre > 0, divisão segura sem guard
    R *= _rms(L) / _rms(R)
    return np.stack([L, R], axis=1).astype(np.float32)  # (T, 2)

def _caimento_pandora(w, ms=180):
    """Aplica a curva de decaimento da Pandora nos últimos ms do áudio."""
    w = np.asarray(w, dtype=np.float32)
    n = min(int(SR * ms / 1000), len(w))
    if n < 8:
        return w
    f = np.interp(np.linspace(0, len(_CURVA_CAIMENTO) - 1, n),
                  np.arange(len(_CURVA_CAIMENTO)), _CURVA_CAIMENTO)
    w = w.copy()
    w[-n:] *= f.astype(np.float32)
    return w

def sintetizar_clone_pandora(perfil, texto, speed=0.80,
                             num_step=32, guidance_scale=3.0, progresso=lambda *a: None):
    """Síntese clone com CAIMENTO natural estilo Pandora: gera um pouco mais devagar
    (vogal final mais longa) e aplica a curva de decaimento da referência. Resolve o
    corte seco que o OmniVoice faz no fim das frases (usado no Battle)."""
    if not (texto or "").strip():
        return np.zeros(1, dtype=np.float32)
    m      = carregar_omni()
    prompt = _criar_prompt_voz(m, perfil)
    cfg    = _cfg(num_step, guidance_scale)
    progresso(0.1, "Gerando áudio...")
    wav = m.generate(_com_ponto(texto), voice_clone_prompt=prompt,
                     generation_config=cfg, speed=float(speed))[0]
    w = np.asarray(wav, dtype=np.float32).squeeze()
    a = np.where(np.abs(w) > 0.006)[0]   # apara silêncio preservando a cauda
    if len(a):
        w = w[max(0, a[0] - int(SR * 0.01)) : min(len(w), a[-1] + int(SR * 0.19))]
    return _caimento_pandora(w, 180)

def sintetizar_clone_lote(perfil, textos, language=None, instruct=None,
                          num_step=32, guidance_scale=3.0, speed_mult=1.0,
                          progresso=lambda *a: None):
    """Sintetiza múltiplos textos com UMA única carga do OmniVoice em batch nativo.
    Passa todos os textos de uma vez para generate() → 3× mais rápido que loop
    sem custo extra de VRAM (testado: 2.04 GB antes e depois na RTX 2060).
    language=None preserva o sotaque natural do clone.
    instruct (ex.: 'whisper') aplica o estilo nativo (modo ASMR).
    Retorna lista de arrays numpy, um por texto."""
    textos = [t for t in textos if (t or "").strip()]
    if not textos:
        return []
    m      = carregar_omni()
    prompt = _criar_prompt_voz(m, perfil)
    cfg    = _cfg(num_step, guidance_scale)
    speed  = perfil["base_speed"] * speed_mult

    # Batch em chunks de 12: mantém o ganho de velocidade (~3×) e atualiza
    # o progresso a cada chunk (sem chunks, 51 segmentos ficam em silêncio ~2 min).
    CHUNK = 12
    resultados = []
    for i0 in range(0, len(textos), CHUNK):
        chunk = textos[i0:i0 + CHUNK]
        pct = 0.1 + 0.85 * (i0 / len(textos))
        i_fim = min(i0 + len(chunk), len(textos))
        progresso(pct, f"Sintetizando {i0+1}-{i_fim}/{len(textos)}...")
        kw = dict(voice_clone_prompt=[prompt] * len(chunk), generation_config=cfg)
        if language:
            kw["language"] = language
        if instruct:
            kw["instruct"] = instruct
        if abs(speed - 1.0) > 1e-3:
            kw["speed"] = float(speed)
        wavs = m.generate([_com_ponto(t) for t in chunk], **kw)
        resultados.extend(_saida(wav) for wav in wavs)
    progresso(0.95, "Finalizando áudio...")
    # OmniVoice fica residente — liberado só quando a Gemma precisa.
    return resultados

def sintetizar_design(instruct, texto, language="pt",
                      num_step=32, guidance_scale=3.0, speed_mult=1.0,
                      progresso=lambda *a: None):
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
    # OmniVoice fica residente — liberado só quando a Gemma precisa.
    return _saida(wav)

def sintetizar_historia(perfil, texto, ritmo=1.0, sussurro=False,
                        musica_path=None, vol_fundo=0.03, cauda_fundo=0.0,
                        progresso=lambda *a: None, vozes_map=None):
    """`vozes_map` (opcional): dict {NOME: perfil_de_voz} — personagens da
    história cujo nome está no mapa falam com uma voz SALVA (clone real) em vez
    da PALETA. O narrador continua sendo a voz da sessão (perfil)."""
    beats = _beats_historia(texto)
    if not beats:
        return np.zeros(1, dtype=np.float32), []
    descarregar_omni()  # libera VRAM para a Gemma classificar os beats
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
    # Detecta abertura clássica e alonga o primeiro fonema vogal no texto
    # Ex: "Era uma vez" → "Eera uma vez" — OmniVoice pronuncia naturalmente
    _ABERTURAS = (
        "era uma vez", "havia", "num reino", "numa terra", "muito tempo atrás",
        "certa vez", "certo dia", "antigamente", "em tempos remotos",
        "conta a lenda", "dizem que", "reza a lenda", "numa floresta",
        "num lugar muito distante", "há muitos anos",
    )
    _VOGAIS = "aeiouáéíóúàâêô"
    def _alongar_abertura(txt):
        """Duplica a primeira vogal da primeira palavra para alongar o fonema."""
        for j, ch in enumerate(txt):
            if ch.lower() in _VOGAIS:
                return txt[:j] + ch + txt[j:]   # "Era" → "Eera"
        return txt

    primeiro_txt = beats[0][1].strip().lower() if beats else ""
    eh_abertura = any(primeiro_txt.startswith(ab) for ab in _ABERTURAS)

    # Vozes salvas por personagem (multi-voz): prompts sob demanda, cacheados
    vmap = {_norm_nome(k): p for k, p in (vozes_map or {}).items() if p}
    prompts_pers: dict = {}
    cfg    = _cfg(); segs = []; roteiro = []; quem_seg = []
    for i, ((eh_fala, txt), (quem, emo)) in enumerate(zip(beats, tags)):
        v = voz_de(quem); d = EMO["neutra"]  # tom fixo — mais estável
        qn = _norm_nome(quem)
        prompt_seg = prompt
        if v["narr"]:
            speed = v["speed"]; tom = 1.0; vol = float(np.clip(d["vol"], 0.82, 1.08))
        elif qn in vmap:
            pp = vmap[qn]
            if qn not in prompts_pers:
                prompts_pers[qn] = _criar_prompt_voz(m, pp)
            prompt_seg = prompts_pers[qn]
            speed = pp["base_speed"] * d["s"]; tom = d["p"]; vol = d["vol"]
        else:
            speed = v["speed"] * d["s"]; tom = v["P"] * d["p"]; vol = d["vol"]
        speed *= ritmo
        if i == 0 and eh_abertura:
            txt   = _alongar_abertura(txt)  # alonga o fonema no texto
            speed *= 0.82                   # velocidade normal de abertura (sem exagero)
        elif i == 0:
            speed *= 0.82
        elif i == len(beats) - 1:
            speed *= 0.85
        progresso(0.10 + 0.85 * i / max(1, len(beats)),
                  f"Gerando {i+1}/{len(beats)} [{quem}:{emo}]")
        seg = _gerar_um(m, cfg, prompt_seg, txt, speed, tom, vol)
        if sussurro:
            seg = _sussurro(seg)
        segs.append(seg)
        roteiro.append((quem, emo, txt)); quem_seg.append(quem)
    # OmniVoice fica residente — liberado só quando a Gemma precisa.
    audio = _montar(segs, quem_seg)
    if musica_path and vol_fundo > 0:
        progresso(0.98, "Misturando áudio de fundo...")
        audio = _misturar_fundo(audio, _carregar_fundo(musica_path, vol_fundo), cauda_fundo)
    return audio, roteiro

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
    out = []
    for ln in (txt or "").splitlines():
        s = ln.replace("```", "")
        s = re.sub(r"\[[^\]]*\]", "", s)      # remove [marcações de imagem/cena]
        s = re.sub(r"\([^)]*\)", "", s)       # remove (rubricas/indicações)
        s = re.sub(r"[*_#`]+", "", s)         # remove markdown (**negrito**, #, etc.)
        s = re.sub(r"^\s*\d+[\.\)]\s*", "", s) # remove numeração "1. " / "2) "
        s = s.lstrip(":–- ").strip()          # sobra de pontuação no início
        s = re.sub(r"\s+", " ", s).strip()
        if not s:
            continue
        if not re.search(r"[A-Za-zÀ-ÿ]", s):  # linhas só com traços/pontuação (---)
            continue
        if re.match(r"^(claro|aqui está|aqui vai|segue|com certeza|roteiro|cenário|cenario|personagens?|debate)\b", s, re.I) and len(s) < 45:
            continue
        out.append(s)
    return "\n".join(out).strip()

def gerar_roteiro_comedia(num_predict=1400):
    descarregar_omni()  # libera VRAM para a Gemma
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

MAX_PDF_CHARS = 8000

def _ler_pdf(path):
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

def ler_pdf_completo(path):
    """Como _ler_pdf, mas SEM truncar — retorna (texto_inteiro, n_paginas).
    Use junto com destilar_conteudo() para materiais longos."""
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
    return texto, len(reader.pages)

def destilar_conteudo(texto, progresso=lambda *a: None, bloco_chars=7000):
    """Map-reduce pra ler um material MAIOR que o contexto da Gemma: divide o
    texto em blocos de ~7k chars, extrai de cada um a lista de FATOS/conceitos
    ensináveis (uma chamada Gemma por bloco), e devolve os fatos juntos — que
    cabem no prompt do game show. Assim o quiz cobre o material INTEIRO, não só
    o começo (antes: truncava em 8k chars). Custo: ~15-30s por bloco."""
    texto = (texto or "").strip()
    if len(texto) <= bloco_chars:
        return texto
    descarregar_omni()
    blocos = [texto[i:i + bloco_chars] for i in range(0, len(texto), bloco_chars)]
    fatos = []
    for i, b in enumerate(blocos):
        progresso(0.05 + 0.55 * i / len(blocos),
                  f"Lendo o material (parte {i+1}/{len(blocos)})...")
        p = ("Extraia do texto abaixo os FATOS e conceitos mais importantes e ensináveis, "
             "em português do Brasil. Um fato por linha, frases curtas e completas, sem "
             "numerar. SÓ o que está no texto — não invente.\n\n"
             '"""\n' + b + '\n"""\n\nFATOS:')
        try:
            fatos.append(_gemma(p, num_predict=500, num_ctx=8192, temperature=0))
        except Exception:
            continue  # bloco com falha não derruba o resto
    return "\n".join(fatos).strip() or texto[:bloco_chars]

def gerar_gameshow_duelo(conteudo, faixa="crianças de 7 a 10 anos", n_perguntas=5,
                         nome1="MAX", nome2="LILI", num_predict=2200,
                         progresso=lambda *a: None):
    """Game Show 2.0: a PANDORA apresenta um DUELO de quiz entre dois
    competidores nomeados, com PLACAR anunciado a cada rodada e um VENCEDOR no
    fim. As falas saem rotuladas ('NOME: fala') pra síntese dar uma voz salva
    a cada competidor (vozes_map em sintetizar_comedia)."""
    conteudo = (conteudo or "").strip()
    if not conteudo:
        return ""
    n1, n2 = (nome1 or "MAX").strip().upper(), (nome2 or "LILI").strip().upper()
    descarregar_omni()
    progresso(0.65, "Escrevendo o duelo...")
    p = ("Você vai criar o roteiro de um GAME SHOW de quiz EDUCATIVO para " + faixa + ", "
         "apresentado pela PANDORA, a secretária do senhor Hades — sombria, debochada e "
         "sarcástica, mas que ENSINA de verdade e com carinho.\n\n"
         "MATERIAL DE ESTUDO (baseie-se SOMENTE nos fatos abaixo; NÃO invente):\n"
         '"""\n' + conteudo + '\n"""\n\n'
         f"É um DUELO entre dois competidores: {n1} e {n2}.\n\n"
         "ESTRUTURA OBRIGATÓRIA DO PROGRAMA:\n"
         f"1. Pandora abre o programa, anuncia o tema e apresenta os dois duelistas "
         f"({n1} e {n2}), cada um responde a apresentação com uma fala de provocação leve.\n"
         f"2. São {n_perguntas} RODADAS. Em cada rodada a Pandora realiza uma pergunta sobre um aspecto do livro: personagens, tramas, situações, curiosidades, enredo, situações críticas que ocorrem no livro. "
         " alternando quem responde primeiro. Um competidor às vezes ACERTA, às vezes ERRA (varie de verdade!). "
         "A Pandora zoa quem erra (sarcasmo leve), diz a resposta CERTA e explica. É importante que a Pandora tenham interações com os competidores e o público em geral entre as perguntas, recheando o ambiente do game mas sem perder o foco da competição.\n"
         "os participantes do game show devem ser engraçados, leves e interagir com Pandora, a platéia e o adversário."
         "3. AO FIM DE CADA RODADA a Pandora anuncia o PLACAR ATUALIZADO, no formato "
         f"exato: 'Placar: {n1} X ponto(s), {n2} Y ponto(s)'. Conte 1 ponto por acerto, "
         "seja CONSISTENTE com quem acertou. \n"
         f"4. No final, a Pandora anuncia o placar final, declara o VENCEDOR (quem tiver "
         "mais pontos), o vencedor comemora com uma fala, o perdedor lamenta com humor, "
         "e a Pandora encerra com um resuminho do que foi aprendido.\n\n"
         "FORMATO OBRIGATÓRIO DAS FALAS:\n"
         "- Falas da PANDORA (apresentadora): linhas normais, SEM rótulo.\n"
         f"- Falas dos competidores: '{n1}: fala' ou '{n2}: fala' (nome em MAIÚSCULAS + "
         "dois-pontos). NÃO rotule a Pandora. NADA de parênteses, asteriscos ou música.\n"
         "- Uma fala por linha.\n\n"
         "Português do Brasil. Responda SÓ o roteiro.\n\nROTEIRO:\n")
    txt = _gemma(p, num_predict=num_predict, num_ctx=8192, temperature=0.7)
    descarregar_gemma()
    return _limpar_roteiro(txt)

def gerar_gameshow_educativo(conteudo, faixa="crianças de 7 a 10 anos",
                             n_perguntas=5, num_predict=1800):
    conteudo = (conteudo or "").strip()
    if not conteudo:
        return ""
    descarregar_omni()  # libera VRAM para a Gemma
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
                       progresso=lambda *a: None, vozes_map=None):
    """`vozes_map` (opcional): dict {NOME: perfil_de_voz} — personagens com nome
    no mapa falam com uma voz SALVA de verdade (clone), em vez da PALETA
    (variações de pitch da voz base). Usado pelo Game Show duelo e histórias
    multi-voz. Nomes são normalizados (_norm_nome) na comparação."""
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
    emo_prompts = _carregar_prompts_emocao(m, perfil)
    # Vozes salvas por personagem: prompts criados sob demanda e cacheados
    vmap = {_norm_nome(k): p for k, p in (vozes_map or {}).items() if p}
    prompts_pers: dict = {}
    cfg         = _cfg(); segs = []; roteiro = []; quem_seg = []
    for i, ((eh_fala, txt), quem, emo) in enumerate(zip(beats, falantes, emos)):
        v = voz_de(quem); d = EMO.get(emo, EMO["neutra"])
        qn = _norm_nome(quem)
        if v["narr"]:
            speed = v["speed"] * d["s"]; tom = 1.0; vol = d["vol"]
            prompt = emo_prompts.get(emo, prompt_base)
        elif qn in vmap:
            # personagem com voz SALVA: clone real, sem deslocar pitch (PALETA)
            pp = vmap[qn]
            if qn not in prompts_pers:
                prompts_pers[qn] = _criar_prompt_voz(m, pp)
            prompt = prompts_pers[qn]
            speed = pp["base_speed"] * d["s"]; tom = d["p"]; vol = d["vol"]
        else:
            speed = v["speed"] * d["s"]; tom = v["P"] * d["p"]; vol = d["vol"]
            prompt = prompt_base
        speed *= ritmo
        if i == 0:               speed *= 0.82
        elif i == len(beats) - 1: speed *= 0.85
        progresso(0.20 + 0.75 * i / max(1, len(beats)),
                  f"Gerando {i+1}/{len(beats)} [{quem}:{emo}]")
        seg = _gerar_um(m, cfg, prompt, txt, speed, tom, vol)
        b = d.get("brilho", 1.0)
        if b != 1.0:              seg = _brilho(seg, b)
        if d.get("tremolo", 0.0): seg = _tremolo(seg, d["tremolo"])
        if d.get("eco", False):   seg = _eco(seg)
        segs.append(seg); quem_seg.append(quem)
        efe = sfx_seq[i][0] if i < len(sfx_seq) else "nenhum"
        roteiro.append((quem, emo, txt, efe))
    descarregar_omni()
    audio = _montar_comedia(segs, quem_seg, sfx_seq, catalogo, vol_sfx, plateia_wav, vol_plateia)
    if abertura_path and vol_abertura > 0:
        ab = _carregar_fundo(abertura_path, vol_abertura)
        if ab is not None and len(ab):
            f = min(int(1.2 * SR), len(ab) // 3)
            if f > 1: ab[-f:] *= np.linspace(1, 0, f)
            gap = np.zeros(int(0.3 * SR), dtype=np.float32)
            audio = np.concatenate([ab.astype(np.float32), gap, audio]).astype(np.float32)
    return audio, roteiro

# ── Classificadores (Contador de Histórias e Comédia) ────────────────────────
def _achar_emocao(txt):
    t = txt.lower()
    for e in EMO_LISTA:
        if re.search(r"\b" + re.escape(e), t): return e
    return "neutra"

def _split_frases(t):
    t = (t or "").strip()
    return [s.strip() for s in re.split(r"(?<=[.!?…])\s+", t) if s.strip()]

def _beats_historia(texto):
    beats = []
    for bloco in texto.splitlines():
        bloco = bloco.strip()
        if not bloco:
            continue
        norm = re.sub(r'[""„«»]', '"', bloco)
        if '"' in norm:
            for i, p in enumerate(norm.split('"')):
                if i % 2 == 1:
                    p = p.strip()
                    if p: beats.append((True, p))
                else:
                    beats += [(False, fr) for fr in _split_frases(p)]
        else:
            n2 = norm.replace("—", "–")
            n2 = re.sub(r"(?<=\s)-(?=\s)", "–", n2)
            if "–" in n2:
                for i, p in enumerate(n2.split("–")):
                    p = p.strip(" ,;:")
                    if p: beats.append((i % 2 == 1, p))
            else:
                beats += [(False, fr) for fr in _split_frases(n2)]
    return beats

_ROTULO_RE   = re.compile(r"^\s*([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ .]{0,18}?):\s+(.+)$")
_FALANTE_BASE = {"apresentador", "apresentadora", "pandora", "narrador", "narradora",
                 "host", "animador", "animadora", "plateia", "publico", "auditorio", "audiencia"}

def _beats_comedia(texto):
    beats, falantes = [], []
    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha:
            continue
        m = _ROTULO_RE.match(linha)
        nome = _norm_nome(m.group(1)) if m else ""
        base = bool(nome) and (nome in _FALANTE_BASE or nome.startswith(("apres", "narr", "anim", "host")))
        if m and nome and not base:
            beats.append((True, m.group(2).strip())); falantes.append(nome)
        else:
            fala = m.group(2).strip() if (m and base) else linha
            for fr in _split_frases(fala):
                beats.append((False, fr)); falantes.append("narrador")
    return beats, falantes

def _ascii1(w):
    q = unicodedata.normalize("NFKD", w or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]", "", q)

def _norm_nome(quem):
    q = unicodedata.normalize("NFKD", quem or "").encode("ascii", "ignore").decode().lower()
    q = re.sub(r"[^a-z\s]", " ", q)
    q = re.sub(r"^\s*(?:o|a|os|as|um|uma|sua|seu|meu|minha)\s+", "", q).strip()
    return q.split()[0][:16] if q.split() else ""

_VERBOS_FALA = ("disse|falou|respondeu|perguntou|gritou|exclamou|rosnou|murmurou|"
    "sussurrou|mentiu|agradeceu|continuou|retrucou|replicou|indagou|berrou|chamou|"
    "ordenou|pediu|contou|avisou|explicou|comentou|declarou|afirmou|sugeriu|repetiu|"
    "acrescentou|concluiu|completou|observou|insistiu|gemeu|chorou|riu|brincou|"
    "prosseguiu|emendou|imitou|prometeu|respondia|dizia|perguntava")
_ART_PREP = {"o","a","os","as","um","uma","sua","seu","suas","seus","meu","minha",
             "este","esta","aquele","aquela","ao","aos","de","da","do","das","dos",
             "com","em","para","que"}
_PRON_SUJ = {"ele","ela","eles","elas","lhe","me","se","te","nos","eu","tu","voce"}
_PULAR_NOME = {"perguntar","dizer","falar","responder","contar","gritar","exclamar",
    "rosnar","sussurrar","perguntando","dizendo","tentando","soar","ainda","dia","dias",
    "vez","noite","manha","tarde","hora","momento","instante","entao","depois","logo",
    "antes","assim","repente","seguida","enquanto","fim","partir"}

def _primeiro_nome(palavras):
    for w in palavras:
        n = _ascii1(w)
        if not n: continue
        if n in _PRON_SUJ: return ""
        if n in _ART_PREP or n in _PULAR_NOME: continue
        return n[:16]
    return ""

def _falante_da_tag(tag, pos):
    t = (tag or "").strip()
    if pos == "depois":
        m = re.search(r"\b(?:" + _VERBOS_FALA + r")\b\s+(.+)", t, re.IGNORECASE)
        return _primeiro_nome(re.findall(r"[A-Za-zÀ-ÿ]+", m.group(1))) if m else ""
    m = re.search(r"^(.*?)\b(?:" + _VERBOS_FALA + r")\b", t, re.IGNORECASE)
    trecho = m.group(1) if m else t
    pals = re.findall(r"[A-Za-zÀ-ÿ]+", trecho)
    if any(_ascii1(w) in _PRON_SUJ for w in pals): return ""
    return _primeiro_nome(pals)

def _quem_fala_gemma(beats, i, elenco):
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

_LOTE_CLASSIF = 12

def _classificar_beats(beats):
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
            if not lote[j][0]:
                res[idx] = ("narrador", emocao)
            else:
                res[idx] = (_norm_nome(quem) or "personagem", emocao)
    falante = {}
    for i, (eh_fala, _) in enumerate(beats):
        if not eh_fala:
            continue
        nome = ""
        if i + 1 < len(beats) and not beats[i + 1][0]:
            nome = _falante_da_tag(beats[i + 1][1], "depois")
        if not nome and i - 1 >= 0 and not beats[i - 1][0]:
            prev = beats[i - 1][1].rstrip()
            nome = _falante_da_tag(prev, "antes" if prev.endswith(":") else "depois")
        if nome:
            falante[i] = nome
    elenco = set(falante.values())
    ativo = ""
    for i, (eh_fala, txt) in enumerate(beats):
        if not eh_fala:
            for w in re.findall(r"[A-Za-zÀ-ÿ]+", txt):
                if _ascii1(w) in elenco:
                    ativo = _ascii1(w); break
            continue
        nome = falante.get(i)
        if not nome:
            nome = _quem_fala_gemma(beats, i, elenco) or ativo
        if nome:
            res[i] = (nome, res[i][1])
        ativo = nome or ativo
    return res

def _emocao_lote(beats):
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
            for d in pontuais:
                if d == efe or (efe and (d in efe or efe in d)):
                    achou = d; break
            if achou:
                pos = POSICAO_SFX.get(achou.split()[0] if achou.split() else achou, pos)
            res[ini + j] = (achou or "nenhum", pos)
    gap = 3 if intensidade <= 0.6 else (0 if intensidade >= 1.5 else 1)
    if gap:
        ult = -99
        for i, (e, pos) in enumerate(res):
            if e != "nenhum":
                if i - ult <= gap: res[i] = ("nenhum", pos)
                else:              ult = i
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

# ── NOVAS FUNÇÕES V2 ────────────────────────────────────────────────────────

_OMNI_VALID_ITEMS = (
    "female, male, child, teenager, young adult, middle-aged, elderly, "
    "low pitch, moderate pitch, high pitch, very high pitch, very low pitch, whisper, "
    "american accent, australian accent, british accent, canadian accent, "
    "chinese accent, indian accent, japanese accent, korean accent, "
    "portuguese accent, russian accent"
)

# Cada categoria do OmniVoice aceita NO MÁXIMO um item — usado para deduplicar
# (ex.: a Gemma às vezes devolve "low pitch, moderate pitch" → conflito).
_OMNI_CATEGORIA = {
    "female": "gender", "male": "gender",
    "child": "age", "teenager": "age", "young adult": "age",
    "middle-aged": "age", "elderly": "age",
    "very low pitch": "pitch", "low pitch": "pitch", "moderate pitch": "pitch",
    "high pitch": "pitch", "very high pitch": "pitch",
    "whisper": "style",
}

_OMNI_VALID_SET = {item.strip() for item in _OMNI_VALID_ITEMS.split(",")}

def _dedup_instruct(instruct_raw: str) -> list:
    """Filtra a string bruta do OmniVoice: apenas itens válidos, 1 por categoria."""
    visto, out = set(), []
    for t in (s.strip() for s in instruct_raw.split(",")):
        if t not in _OMNI_VALID_SET:
            continue
        cat = _OMNI_CATEGORIA.get(t, "accent" if t.endswith("accent") else t)
        if cat not in visto:
            visto.add(cat); out.append(t)
    return out or ["female", "moderate pitch"]

def interpretar_descricao_voz(descricao, progresso=lambda *a: None):
    """Interpreta descrição em linguagem natural para instrução OmniVoice.
    Ex: 'professora de 55 anos, cansada' → 'female, middle-aged, low pitch'"""
    if not (descricao or "").strip():
        return None, "Descreva a voz que deseja."
    descarregar_omni()  # libera VRAM para a Gemma
    progresso(0.3, "Interpretando descrição...")
    p = (f"Translate this voice description into OmniVoice instruct attributes.\n"
         f"You MUST use ONLY items from this exact list (copy them verbatim, comma-separated):\n"
         f"{_OMNI_VALID_ITEMS}\n\n"
         f"Do NOT invent new items. Do NOT use: expressive, soft, raspy, breathy, strong, or anything not in the list.\n"
         f"Choose the closest matching items from the list only.\n\n"
         f"Voice description: {descricao}\n\n"
         f"Instruct (valid items only, comma-separated, no explanation):")
    try:
        instruct_raw = _gemma(p, 60, temperature=0.2)
        descarregar_gemma()
        tokens_validos = _dedup_instruct(instruct_raw)  # filtra, dedup, fallback
        instruct = ", ".join(tokens_validos)
        return instruct, f"✅ Instrução gerada: {instruct}"
    except Exception as e:
        return None, f"❌ Erro ao interpretar: {e}"

def gerar_roteiro_trailer(genero, logline, num_predict=800, progresso=lambda *a: None):
    """Gera roteiro épico de trailer de cinema (6-8 frases dramáticas)."""
    if not (logline or "").strip():
        return ""
    descarregar_omni()  # libera VRAM para a Gemma
    progresso(0.2, "Escrevendo roteiro de trailer...")
    generos_dicas = {
        "Terror": "assustador, perturbador, clima sombrio",
        "Ficção Científica": "épico, tecnológico, futuro ameaçador",
        "Romance": "emocional, apaixonado, conflito do coração",
        "Ação": "explosivo, adrenalina, confronto épico",
        "Comédia": "engraçado, absurdo, desfechos surpresa",
    }
    tom = generos_dicas.get(genero, "dramático")
    p = (f"Escreva o roteiro de um TRAILER DE CINEMA de {genero.lower()}, estilo blockbuster.\n"
         f"Logline: {logline}\n\n"
         f"Tom: {tom}. Estilo de trailer: frases curtas, dramáticas, pausas implícitas.\n"
         "8-10 frases no máximo, cada uma uma revelação ou impacto.\n"
         "Português do Brasil. Responda SÓ o roteiro, sem comentários.\n\nRoteiro:")
    try:
        roteiro = _gemma(p, num_predict, temperature=0.7)
        descarregar_gemma()
        # Remove [marcações], (rubricas), numeração e markdown — o narrador só fala as frases
        return _limpar_roteiro(roteiro)
    except Exception:
        return ""

def gerar_meditacao(tema, duracao_min, intensidade_sussurro, idioma="pt", progresso=lambda *a: None):
    """Gera script de meditação guiada com pausas progressivas baseadas em estrutura profissional.
    idioma='en' gera o roteiro em inglês (usado no modo ASMR com a voz Nicole).
    Retorna (script, pausas_em_segundos) para o pipeline processar.

    Estrutura aprendida de referência profissional (análise de áudio real):
    - 67% fala / 33% pausa
    - Pausas iniciais: 2-3s | Meio: 4-6s | Pico: 7-8s
    - Abertura curta (~20s) → primeira pausa longa (~5s) logo no início
    - Encerramento: bloco longo sem interrupção (~20-25s de fala)
    - Padrão: frase curta (5-8s de áudio) → pausa → repetir
    """
    if not (tema or "").strip():
        return "", []
    # Libera a VRAM do OmniVoice (se residente de uma geração anterior) para a
    # Gemma poder carregar — evita "A Gemma não gerou o script" na RTX 2060 6GB.
    descarregar_omni()
    # 67% do tempo é fala → ~100 palavras por minuto em ritmo lento
    n_palavras = int(duracao_min * 60 * 0.67 / 0.6)  # ~112 palavras/min lento
    # Mínimo robusto: relatório pede no mínimo 6 min funcionais
    n_frases_alvo = max(20, int(duracao_min * 4))  # ~4 frases por minuto
    progresso(0.2, "Gerando script de meditação...")
    if idioma == "en":
        # Roteiro em inglês para o modo ASMR (voz Nicole nativa, sem sotaque)
        p = (
            f"Write a LONG, COMPLETE guided MEDITATION script about '{tema}' "
            f"for {duracao_min} minutes.\n\n"
            "RULES:\n"
            "1. VERY SHORT sentences — max 8-10 words. One sentence per line.\n"
            f"2. Write AT LEAST {n_frases_alvo} sentences total.\n"
            "3. After EACH sentence add a pause marker: [pausa 3s], [pausa 5s] or [pausa 8s]\n"
            "4. PROGRESSIVE pauses: [pausa 3s] early, [pausa 5s] middle, [pausa 8s] deepest part.\n"
            "5. Use ellipses '...' INSIDE sentences for soft breathing micro-pauses.\n"
            "   Example: 'Close your eyes... and breathe deeply.'\n"
            "6. Soft, soothing, second person ('you'), present tense. Hypnotic, monotone, little intonation.\n"
            "7. Phases: welcome & posture, progressive body relaxation, guided imagery & countdown 10 to 1,\n"
            "   a moment of pure silence, then a gentle return.\n"
            "8. ENGLISH. No phase titles. Reply with ONLY the script.\n\n"
            "EXAMPLE:\n"
            "Close your eyes gently.\n"
            "[pausa 5s]\n"
            "Feel your body... grow heavy and calm.\n"
            "[pausa 8s]\n\n"
            "Script:"
        )
    else:
        p = (
        f"Escreva um script LONGO e COMPLETO de MEDITAÇÃO GUIADA sobre '{tema}' "
        f"para {duracao_min} minutos de duração.\n\n"
        "REGRAS OBRIGATÓRIAS:\n"
        "1. Frases MUITO CURTAS — máximo 8 a 10 palavras por frase. Uma frase por linha.\n"
        f"2. Escreva NO MÍNIMO {n_frases_alvo} frases no total — o roteiro precisa preencher os {duracao_min} minutos.\n"
        "3. Após CADA frase, insira um marcador de pausa: [pausa 3s], [pausa 5s] ou [pausa 8s]\n"
        "4. Pausas PROGRESSIVAS: use [pausa 3s] no início, [pausa 5s] no meio, [pausa 8s] na parte mais profunda.\n"
        "5. Use reticências '...' DENTRO das frases para micro-pausas de respiração.\n"
        "   Exemplo: 'Feche os olhos... e respire fundo.'\n"
        "6. Use suspiros de respiração organizados assim (NUNCA varie a grafia):\n"
        "   - [sigh] = respiração breve, em alguns pontos de relaxamento.\n"
        "   - [sigh] ahhhh = expiração ALONGADA, no início das frases de transição entre fases.\n"
        "   - [sigh]... [sigh] = suspiro de ALÍVIO, uma única vez, no ponto mais profundo da meditação.\n"
        "7. ESTRUTURA em 5 fases (siga as durações mínimas):\n"
        "   ABERTURA (~1 min, 4 frases): boas-vindas, orientação postural, primeiras respirações.\n"
        "   INDUÇÃO (~2 min, 8 frases): relaxamento progressivo — pés, pernas, abdômen, peito, ombros, rosto.\n"
        "   APROFUNDAMENTO (~3 min, 10 frases): imagens guiadas, afirmações, contagem regressiva de 10 a 1.\n"
        "   PERMANÊNCIA (1 frase): convide ao silêncio. Escreva apenas 'Apenas permaneça aqui... em silêncio.'\n"
        "   RETORNO (~1 min, 5 frases): retorno suave, orientação espacial, abertura dos olhos.\n"
        "8. Voz suave, segunda pessoa ('você'), presente do indicativo. Tom monótono e hipnótico, pouca entonação.\n"
        "9. Português do Brasil. Sem títulos de fase. Responda SÓ o script.\n\n"
        "EXEMPLO de formato correto:\n"
        "Feche os olhos suavemente.\n"
        "[pausa 5s]\n"
        "[sigh] ahhhh Sinta seu corpo... mais pesado.\n"
        "[pausa 8s]\n\n"
        "Script:"
    )
    try:
        # num_predict generoso: cada palavra ~5 chars + marcadores [pausa Xs] adicionam tokens extras
        num_predict = max(1200, n_palavras * 10)
        script = _gemma(p, num_predict, temperature=0.45)
        descarregar_gemma()

        pausas = re.findall(r'\[pausa (\d+)s\]', script)
        pausas_seg = [int(p) for p in pausas]

        return script, pausas_seg
    except Exception as e:
        return "", []

def gerar_radio(tema, progresso=lambda *a: None):
    """Gera episódio de rádio completo com 5 segmentos.
    Retorna dicionário com roteiros dos 5 segmentos."""
    descarregar_omni()  # libera VRAM para a Gemma
    progresso(0.1, "Criando abertura...")
    segmentos = {}

    p_abertura = (f"Escreva a ABERTURA de um programa de rádio cômico do submundo (estilo Pandora).\n"
                  f"Tema: {tema}. Duração: 2-3 frases. Entusiasmada, irreverente.\n"
                  "Português do Brasil. SÓ o texto.\n\nTexto:")
    segmentos['abertura'] = _gemma(p_abertura, 150, temperature=0.8)

    progresso(0.3, "Criando bloco de notícias...")
    p_noticias = (f"Escreva 3 NOTÍCIAS absurdas e engraçadas sobre '{tema}', do ponto de vista da Pandora.\n"
                  "Cada uma: 1-2 frases. Formato: NOTICIA 1: texto. NOTICIA 2: texto. NOTICIA 3: texto.\n"
                  "Português do Brasil.\n\nNotícias:")
    segmentos['noticias'] = _gemma(p_noticias, 250, temperature=0.9)

    progresso(0.5, "Criando entrevista...")
    p_entrevista = (f"Escreva o roteiro de uma ENTREVISTA rápida sobre '{tema}' entre a Pandora e um convidado.\n"
                    "Formato: PANDORA: fala. CONVIDADO: fala. (3-4 trocas). Engraçado, sarcástico.\n"
                    "Português do Brasil.\n\nRoteiro:")
    segmentos['entrevista'] = _gemma(p_entrevista, 300, temperature=0.8)

    progresso(0.7, "Criando quadro fixo...")
    p_quadro = (f"Escreva o 'Momento Filosófico do Submundo' sobre '{tema}'.\n"
                "Um aforismo macabro e engraçado da Pandora. 1 frase, máximo 2.\n"
                "Português do Brasil.\n\nAforismo:")
    segmentos['quadro'] = _gemma(p_quadro, 100, temperature=0.7)

    progresso(0.9, "Criando encerramento...")
    p_encerre = ("Escreva o ENCERRAMENTO de um programa de rádio cômico da Pandora.\n"
                 "Despedida sarcástica, 1-2 frases. Português do Brasil.\n\nTexto:")
    segmentos['encerramento'] = _gemma(p_encerre, 100, temperature=0.7)

    descarregar_gemma()
    return segmentos

def gerar_batalha(nome1, desc_ou_perfil1, nome2, desc_ou_perfil2, tema, modo, progresso=lambda *a: None):
    """Gera diálogo de debate entre dois personagens com vozes distintas."""
    descarregar_omni()  # libera VRAM para a Gemma
    progresso(0.2, "Interpretando vozes...")
    instruct1 = desc_ou_perfil1 if isinstance(desc_ou_perfil1, str) else desc_ou_perfil1.get("instruct", "")
    instruct2 = desc_ou_perfil2 if isinstance(desc_ou_perfil2, str) else desc_ou_perfil2.get("instruct", "")

    progresso(0.4, "Gerando debate...")
    modo_dica = "sério, bem argumentado" if modo == "sério" else "caótico, emoções à flor da pele"
    p = (f"Escreva um DEBATE entre dois personagens sobre '{tema}'.\n"
         f"Personagem 1 ({nome1}): {instruct1}\n"
         f"Personagem 2 ({nome2}): {instruct2}\n"
         f"Modo: {modo_dica}. Formato: NOME: fala (4-6 trocas). Português do Brasil.\n\nDebate:")
    roteiro = _gemma(p, 400, temperature=0.8 if modo == "caos" else 0.5)
    descarregar_gemma()
    # Limpa markdown (**NOME:**), cabeçalhos e rubricas para o parser achar as falas
    return _limpar_roteiro(roteiro)

def gerar_batalha_persona(nome1, persona1, nome2, persona2, tema, modo,
                          n_turnos=3, progresso=lambda *a: None):
    """Debate TURNO A TURNO: cada personagem é um 'agente' próprio, condicionado
    ao seu dossiê (identidade, valores, visão de mundo). Cada um responde EM
    CHARACTER ao argumento do outro. Retorna roteiro 'NOME: fala' (compatível
    com a síntese). Se um dossiê vier vazio, o personagem improvisa pelo nome."""
    descarregar_omni()  # libera VRAM para a Gemma
    persona1 = (persona1 or "").strip()[:2500]
    persona2 = (persona2 or "").strip()[:2500]
    estilo = "sério e bem argumentado" if modo == "sério" else "caótico, com emoções à flor da pele"
    historico = []  # [(nome, fala), ...]

    def _turno(nome, persona, oponente, abertura):
        ctx = "\n".join(f"{n}: {f}" for n, f in historico[-6:]) or "(o debate vai começar)"
        tarefa = ("Faça a sua ABERTURA sobre o tema, apresentando a sua posição"
                  if abertura else f"Responda diretamente ao último argumento de {oponente}")
        dossie = persona or "(sem dossiê — improvise uma personalidade coerente com o seu nome)"
        p = (f"Você é {nome}. Sua identidade, valores e visão de mundo:\n{dossie}\n\n"
             f"Você está num debate {estilo} com {oponente} sobre: \"{tema}\".\n"
             f"Debate até agora:\n{ctx}\n\n"
             f"{tarefa}. Fale EM CHARACTER, no seu jeito, curto (2 a 4 frases). "
             f"Português do Brasil. Escreva SÓ a sua fala, sem repetir o seu nome.")
        fala = _gemma(p, 170, temperature=0.7 if modo == "sério" else 0.95)
        fala = " ".join(_limpar_roteiro(fala).split("\n")).strip()
        # remove um eventual "Nome:" que o modelo coloque no começo
        fala = re.sub(rf"^{re.escape(nome)}\s*:\s*", "", fala, flags=re.I).strip()
        return fala

    total = max(1, n_turnos * 2)
    for t in range(n_turnos):
        progresso(0.15 + 0.7 * (2 * t) / total, f"{nome1} argumentando ({t+1}/{n_turnos})...")
        f1 = _turno(nome1, persona1, nome2, abertura=(t == 0))
        if f1: historico.append((nome1, f1))
        progresso(0.15 + 0.7 * (2 * t + 1) / total, f"{nome2} respondendo ({t+1}/{n_turnos})...")
        f2 = _turno(nome2, persona2, nome1, abertura=False)
        if f2: historico.append((nome2, f2))
    descarregar_gemma()
    return "\n".join(f"{n}: {f}" for n, f in historico)

def responder_personagem(personagem_json, historico, fala_usuario, progresso=lambda *a: None):
    """Conversa interativa com personagem salvo. Retorna resposta (texto) e emoção."""
    descarregar_omni()  # libera VRAM para a Gemma
    progresso(0.2, "Pensando na resposta...")
    personalidade = personagem_json.get("personalidade", "neutro")
    quirks = personagem_json.get("quirks", "")
    tom_padrao = personagem_json.get("tom_emocional", "neutra")

    ctx = "\n".join(f"Você: {u}\n{personagem_json['nome']}: {r}" for u, r in historico[-5:])

    p = (f"Você é {personagem_json['nome']}, com essa personalidade:\n{personalidade}\n"
         f"Seus maneirismos: {quirks}\n"
         f"Tom emocional padrão: {tom_padrao}\n\n"
         f"Histórico recente:\n{ctx}\n\n"
         f"O usuário disse: {fala_usuario}\n\n"
         f"Responda em uma frase, no seu jeito. Apenas a fala, sem rótulo.")
    try:
        resposta = _gemma(p, 100, temperature=0.7)
        # Não descarrega aqui — a Gemma ainda é usada para classificar a emoção abaixo
        emo_p = (f"Qual a emoção de quem diz isso? (escolha uma):\n{', '.join(EMO_LISTA)}\n"
                 f"Frase: {resposta}\n\nEmoção (uma palavra):")
        emoção = _achar_emocao(_gemma(emo_p, 20, temperature=0))
        descarregar_gemma()

        return resposta.strip(), emoção
    except Exception:
        return "...", "neutra"

def gerar_livro_capitulos(texto, perfil, progresso=lambda *a: None):
    """Processa história/livro dividido por capítulos (marcados com === CAPÍTULO N ===).
    Retorna dict com {capitulo: audio_array}."""
    capitulos_texto = re.split(r'(?:===\s*)?[Cc][Aa][Pp][ÍíI][Tt][Uu][Ll][Oo]\s+(\d+|[A-Za-z]+)(?:\s*===)?', texto)
    if len(capitulos_texto) < 2:
        capitulos_texto = [("Único", texto)]
    else:
        capitulos_texto = [(capitulos_texto[i], capitulos_texto[i+1]) for i in range(1, len(capitulos_texto), 2)]

    resultado = {}
    for i, (num, txt) in enumerate(capitulos_texto):
        progresso(0.1 + 0.8 * i / len(capitulos_texto), f"Gerando capítulo {num}...")
        try:
            audio, _ = sintetizar_historia(perfil, txt, ritmo=1.0, sussurro=False,
                                          musica_path=None, vol_fundo=0, cauda_fundo=0)
            resultado[f"cap_{num}"] = audio
        except Exception as e:
            print(f"Erro no capítulo {num}: {e}")

    return resultado

def gerar_temporada(perfil, n_eps, tema_base, progresso=lambda *a: None):
    """Gera N episódios de programa com continuidade narrativa entre eles."""
    resultado = {}
    contexto_acumulado = f"Tema base da temporada: {tema_base}."

    for ep in range(1, n_eps + 1):
        progresso(0.1 + 0.8 * (ep-1) / n_eps, f"Gerando episódio {ep}/{n_eps}...")

        p = (f"{contexto_acumulado}\n"
             f"Episódio {ep} de {n_eps}. Gere um roteiro de programa de auditório (estilo Pandora).\n"
             "Mantenha personagens recorrentes, piadas internas, arco da temporada.\n"
             "Formato: NOME: fala (linhas sem rótulo = Pandora). 20-30 linhas.\n"
             "Português do Brasil.\n\nRoteiro:")

        roteiro = _gemma(p, 800, temperature=0.8)
        contexto_acumulado += f"\nEpisódio {ep}: {roteiro[:200]}..."

        try:
            audio, _ = sintetizar_comedia(perfil, roteiro, ritmo=1.0, vol_sfx=0.6,
                                         vol_plateia=0.06, intensidade=1.0)
            resultado[f"ep_{ep:02d}"] = audio
        except Exception as e:
            print(f"Erro no episódio {ep}: {e}")

    descarregar_gemma()
    return resultado

def salvar(audio, nome="saida.wav"):
    d = os.path.join(PASTA, "saidas"); os.makedirs(d, exist_ok=True)
    p = os.path.join(d, nome); sf.write(p, audio, SR, subtype="PCM_16"); return p
