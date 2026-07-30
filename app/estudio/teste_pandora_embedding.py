# -*- coding: utf-8 -*-
"""
Teste da Opção 1: Speaker Embedding pré-extraído da Pandora.

  1. Extrai o voice_clone_prompt da Pandora e salva em vozes/pandora_prompt.pkl
  2. Usa o prompt salvo para sintetizar um texto longo — sem precisar do WAV original
  3. Demonstra Pandora com emoções via DSP (serenidade, melancolia, ironia, urgência)

Execute:  python app/estudio/teste_pandora_embedding.py
Saídas:   app/estudio/saidas/pandora_embedding_teste.wav
          app/estudio/saidas/pandora_emocoes_teste.wav
"""
import os, sys, time, pickle, gc
import numpy as np
import torch
import soundfile as sf
from scipy.signal import stft, istft

PASTA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PASTA)

VOZES_DIR  = os.path.join(PASTA, "vozes")
SAIDAS_DIR = os.path.join(PASTA, "saidas")
WAV_REF    = os.path.join(VOZES_DIR, "Pandora.wav")
TXT_REF    = os.path.join(VOZES_DIR, "Pandora.txt")
PROMPT_PKL = os.path.join(VOZES_DIR, "pandora_prompt.pkl")
SAIDA_WAV      = os.path.join(SAIDAS_DIR, "pandora_embedding_teste.wav")
SAIDA_EMO_WAV  = os.path.join(SAIDAS_DIR, "pandora_emocoes_teste.wav")

os.makedirs(SAIDAS_DIR, exist_ok=True)

TEXTO_LONGO = """
Bem-vindos ao Submundo da Meia-Noite, o único programa de rádio transmitido
das profundezas esquecidas do além. Eu sou Pandora, sua anfitriã eterna,
e esta noite temos um cardápio especial preparado com muito carinho —
ou o que quer que eu sinta, já que o conceito de carinho é um tanto quanto
ambíguo para uma entidade da minha natureza.

Hoje exploraremos os mistérios do sono profundo. Não o sono comum dos mortais,
aquele superficial e perturbado por preocupações triviais. Estou falando do sono
primordial, aquele que existed antes da consciência, antes do tempo,
antes mesmo do primeiro pensamento que alguém teve ao acordar e perguntar
"por que eu existo".

Respira fundo. Deixa os ombros caírem. O peso do dia foi apenas uma ilusão
temporária — todas as coisas são temporárias quando você tem perspectiva
suficiente, e eu, minha querida, tenho perspectiva demais.

Imagina agora um jardim às três da manhã. As flores estão fechadas, guardando
seus segredos para o amanhecer. As estrelas pulsam com aquela luz que viajou
milhares de anos para chegar até os seus olhos — a maioria dessas estrelas
já não existe mais, mas a luz continua. Assim como os seus problemas de hoje
não existirão daqui a cem anos, mas a lembrança de ter superado cada um deles
permanece, silenciosa e persistente.

Deixa os pensamentos passarem como nuvens no céu da madrugada. Você não precisa
agarrar nenhum deles. Você não precisa resolver nada agora. O universo continuará
girando com ou sem a sua intervenção, o que é simultaneamente assustador
e profundamente reconfortante.

Vai descansando. Eu fico de guarda.
""".strip()

SR = 24000

def salvar_wav(wav, path):
    sf.write(path, wav, SR)
    print(f"  → Salvo em: {path}")

def etapa1_extrair_e_salvar_prompt():
    print("\n─── ETAPA 1: Extraindo voice_clone_prompt da Pandora ───")
    if os.path.exists(PROMPT_PKL):
        print(f"  Prompt já existe em: {PROMPT_PKL}")
        print("  (delete o arquivo para regenerar)")
        return

    from omnivoice import OmniVoice
    t0 = time.time()
    print("  Carregando OmniVoice...")
    m = OmniVoice.from_pretrained(
        "k2-fsa/OmniVoice",
        device_map="auto",
        dtype=torch.float16,
        load_asr=False,
        token=False,
    )

    ref_text = ""
    if os.path.exists(TXT_REF):
        ref_text = open(TXT_REF, encoding="utf-8").read().strip()
        print(f"  Texto de referência: {ref_text[:80]}...")

    print("  Extraindo prompt...")
    prompt = m.create_voice_clone_prompt(ref_audio=WAV_REF, ref_text=ref_text or "")

    # Serializa com pickle (torch tensors são suportados)
    with open(PROMPT_PKL, "wb") as f:
        pickle.dump(prompt, f)

    elapsed = time.time() - t0
    print(f"  ✅ Prompt salvo em: {PROMPT_PKL}  ({elapsed:.1f}s)")

    # Descarrega para liberar VRAM
    del m; gc.collect(); torch.cuda.empty_cache()

def etapa2_sintetizar_com_prompt_salvo():
    print("\n─── ETAPA 2: Sintetizando com prompt pré-extraído ───")
    if not os.path.exists(PROMPT_PKL):
        print("  ❌ Prompt não encontrado. Rode a Etapa 1 primeiro.")
        return

    from omnivoice import OmniVoice, OmniVoiceGenerationConfig

    print("  Carregando OmniVoice...")
    t_load = time.time()
    m = OmniVoice.from_pretrained(
        "k2-fsa/OmniVoice",
        device_map="auto",
        dtype=torch.float16,
        load_asr=False,
        token=False,
    )
    print(f"  OmniVoice carregado em {time.time()-t_load:.1f}s")

    print("  Carregando prompt do disco...")
    t_pkl = time.time()
    with open(PROMPT_PKL, "rb") as f:
        prompt = pickle.load(f)
    print(f"  Prompt carregado em {time.time()-t_pkl:.3f}s  ← sem processar WAV")

    cfg = OmniVoiceGenerationConfig(num_step=32, guidance_scale=3.5)

    # Divide em parágrafos para não estourar contexto
    paragrafos = [p.strip() for p in TEXTO_LONGO.split("\n\n") if p.strip()]
    segs = []
    silencio = np.zeros(int(0.6 * SR), dtype=np.float32)  # 0.6s entre parágrafos

    print(f"\n  Sintetizando {len(paragrafos)} parágrafos...")
    t_syn = time.time()
    for i, par in enumerate(paragrafos):
        print(f"  [{i+1}/{len(paragrafos)}] {par[:60]}...")
        wav = m.generate(
            _com_ponto(par),     # prosódia de frase completa
            language="pt",
            voice_clone_prompt=prompt,
            speed=0.85,
            generation_config=cfg,
        )[0]
        wav = np.asarray(wav, dtype=np.float32).squeeze()
        wav = _finalizar(wav)   # corta silêncio morto das pontas
        segs.append(wav)
        segs.append(silencio)

    audio = np.concatenate(segs)
    duracao = len(audio) / SR
    elapsed = time.time() - t_syn
    print(f"\n  ✅ Síntese concluída em {elapsed:.1f}s → {duracao:.1f}s de áudio")
    print(f"  RTF (tempo real): {elapsed/duracao:.2f}x  (< 1.0 = mais rápido que o áudio)")

    # Normaliza
    pico = np.abs(audio).max()
    if pico > 0:
        audio = audio / pico * 0.85

    salvar_wav(audio, SAIDA_WAV)

    del m; gc.collect(); torch.cuda.empty_cache()

# ── DSP local (espelho das funções do motor) ────────────────────────────────

def _rms(x):
    r = np.sqrt(np.mean(x ** 2))
    return r if r > 1e-9 else 1e-9

def _pitch(wav, semitones):
    import librosa
    if abs(semitones) < 0.01:
        return wav
    return librosa.effects.pitch_shift(wav.astype(np.float32), sr=SR, n_steps=semitones)

def _reverb(wav, room=0.35, damp=0.5, wet=0.25):
    """Reverb de câmara via filtros comb paralelos — profundidade sem eco audível."""
    delays_ms = [29.7, 37.1, 41.1, 43.7, 47.0, 53.3]
    gains     = [0.805, 0.827, 0.783, 0.764, 0.751, 0.773]
    out = np.zeros_like(wav)
    for d_ms, g in zip(delays_ms, gains):
        d = int(SR * d_ms / 1000)
        buf = np.zeros(d, dtype=np.float32)
        g_room = g * (1.0 - room * 0.28)
        wet_sig = np.zeros_like(wav)
        idx = 0
        for i, s in enumerate(wav):
            y = buf[idx]
            filt = y * (1.0 - damp) + (buf[(idx - 1) % d] if i > 0 else 0.0) * damp
            buf[idx] = s + filt * g_room
            wet_sig[i] = y
            idx = (idx + 1) % d
        out += wet_sig
    out /= len(delays_ms)
    return ((1.0 - wet) * wav + wet * out).astype(np.float32)

def _brilho(wav, fator):
    _, _, Z = stft(wav, nperseg=512)
    freqs = np.linspace(0, 1, Z.shape[0])
    curva = np.where(freqs > 0.3, fator, 1.0)
    Z2 = Z * curva[:, None]
    _, out = istft(Z2, nperseg=512)
    return out[:len(wav)].astype(np.float32)

def _tremolo(wav, rate=5.0, depth=0.08):
    t = np.arange(len(wav)) / SR
    lfo = 1.0 - depth * (0.5 + 0.5 * np.sin(2 * np.pi * rate * t))
    return (wav * lfo).astype(np.float32)

def _sussurro(wav):
    _, _, Z = stft(wav, nperseg=512)
    mag = np.abs(Z)
    noise = np.random.uniform(0.0, 1.0, mag.shape)
    Z2 = (mag * 0.6 + mag.max() * noise * 0.4) * np.exp(1j * np.angle(Z))
    _, out = istft(Z2, nperseg=512)
    return out[:len(wav)].astype(np.float32)

# Subconjunto do EMO do motor — emoções mais úteis para a Pandora
EMO = {
    "serenidade":   dict(s=0.88, p=-0.3,  vol=0.85, brilho=0.82, tremolo=0.0,  sussurro=False),
    "melancolia":   dict(s=0.82, p=-0.6,  vol=0.80, brilho=0.75, tremolo=0.0,  sussurro=False),
    "ironia":       dict(s=1.05, p=0.5,   vol=1.00, brilho=1.12, tremolo=0.0,  sussurro=False),
    "urgência":     dict(s=1.18, p=0.6,   vol=1.10, brilho=1.22, tremolo=0.0,  sussurro=False),
    "mistério":     dict(s=0.80, p=-0.4,  vol=0.82, brilho=0.78, tremolo=0.05, sussurro=True),
    "neutra":       dict(s=1.00, p=0.0,   vol=1.00, brilho=1.00, tremolo=0.0,  sussurro=False),
}

# Texto por emoção — falas curtas da Pandora no seu estilo
FALAS_EMO = [
    ("neutra",      "Bem-vindos ao Submundo da Meia-Noite. Eu sou Pandora."),
    ("serenidade",  "Respira fundo. Deixa os ombros caírem. O peso do dia foi apenas uma ilusão temporária."),
    ("melancolia",  "Todas as coisas são temporárias. As estrelas que você vê já não existem mais, mas a luz continua."),
    ("ironia",      "Claro, porque dormir oito horas é uma meta absolutamente razoável para qualquer mortal moderno."),
    ("urgência",    "Acorda! Não agora, metaforicamente. Acorda para o fato de que você merece descansar de verdade."),
    ("mistério",    "Às três da manhã o jardim guarda segredos que o amanhecer prefere esquecer."),
]

def _com_ponto(txt):
    txt = txt.strip()
    return txt if txt and txt[-1] in ".!?…" else txt + "."

def _envelope(x, win):
    from numpy.lib.stride_tricks import sliding_window_view
    pad = np.pad(np.abs(x), (win // 2, win // 2))
    return np.array([pad[i:i+win].max() for i in range(len(x))])

def _finalizar(wav):
    """Corta silêncio das pontas e aplica fade-out curto."""
    win = int(0.02 * SR)
    env = _envelope(wav, win); pico = env.max() or 1.0
    fala = np.where(env > pico * 10**(-35/20))[0]
    if len(fala):
        start = max(0, fala[0] - win)
        end   = min(len(wav), fala[-1] + win * 4)
        wav   = wav[start:end]
    fade = min(int(0.06 * SR), len(wav) // 4)
    if fade > 0:
        wav[-fade:] *= np.linspace(1.0, 0.0, fade)
    return wav.astype(np.float32)

def _aplicar_emo(wav, emo_nome):
    d = EMO.get(emo_nome, EMO["neutra"])
    wav = _finalizar(wav)
    if abs(d["p"]) > 0.01:
        wav = _pitch(wav, d["p"])
    wav = wav / _rms(wav) * 0.05 * d["vol"]
    if abs(d["brilho"] - 1.0) > 0.01:
        wav = _brilho(wav, d["brilho"])
    if d["tremolo"] > 0:
        wav = _tremolo(wav, depth=d["tremolo"])
    if d["sussurro"]:
        wav = _sussurro(wav)
    return wav

FRASE_COMPARACAO = (
    "Bem-vindos ao Submundo da Meia-Noite. Eu sou Pandora, sua anfitriã eterna — "
    "e esta noite, meus queridos, vamos falar sobre algo que todos fingem entender mas ninguém realmente domina: "
    "o tempo. Sim, esse tirano invisível que consome tudo. "
    "Não se preocupem! A ansiedade é completamente normal. "
    "Eu mesma já tentei negociar com o tempo uma vez. Não terminou bem para nenhum dos dois. "
    "Mas aqui estamos, respirando, existindo, o que já é uma vitória considerável "
    "num universo que claramente não foi projetado com o nosso conforto em mente."
)

FRASE_DESESPERO = (
    "Não... não, não, não! Isso não pode estar acontecendo. "
    "Eu avisei! Eu avisei e ninguém ouviu e agora olha, OLHA o que sobrou! "
    "Cinco anos. Cinco anos construindo isso, cada detalhe, cada escolha — "
    "e em trinta segundos sumiu tudo. Sumiu! "
    "Como eu faço pra voltar atrás? Como? Não tem como voltar. "
    "Respira. Tenta respirar. Não adianta entrar em colapso agora, "
    "ainda que entrar em colapso seja exatamente o que eu quero fazer. "
    "Por favor... alguém me diz que tem solução. Qualquer solução. "
    "Eu aceito qualquer coisa. Eu aceito tudo."
)
def etapa3_comparacao():
    """Sintetiza dois textos (neutro e desesperado) com pkl vs WAV na hora."""
    print("\n─── ETAPA 3: Comparação pkl vs WAV ───")
    if not os.path.exists(PROMPT_PKL):
        print("  ❌ Prompt não encontrado. Rode a Etapa 1 primeiro.")
        return

    from omnivoice import OmniVoice, OmniVoiceGenerationConfig

    m = OmniVoice.from_pretrained(
        "k2-fsa/OmniVoice",
        device_map="auto",
        dtype=torch.float16,
        load_asr=False,
        token=False,
    )
    cfg = OmniVoiceGenerationConfig(num_step=32, guidance_scale=3.5)
    ref_text = open(TXT_REF, encoding="utf-8").read().strip() if os.path.exists(TXT_REF) else ""

    print("  Carregando prompt pkl...")
    t0 = time.time()
    with open(PROMPT_PKL, "rb") as f:
        prompt_pkl = pickle.load(f)
    print(f"  pkl carregado em {time.time()-t0:.3f}s")

    print("  Carregando prompt do WAV original...")
    t0 = time.time()
    prompt_wav = m.create_voice_clone_prompt(ref_audio=WAV_REF, ref_text=ref_text or "")
    print(f"  wav carregado em {time.time()-t0:.3f}s")

    testes = [
        ("neutro",      FRASE_COMPARACAO,  1.0),
        ("desespero",   FRASE_DESESPERO,   1.1),  # leve aceleração para urgência
    ]

    for nome, frase, speed in testes:
        texto = _com_ponto(frase)
        print(f"\n  ── {nome.upper()} ──")
        for metodo, prompt, sufixo in [("pkl", prompt_pkl, "pkl"), ("wav", prompt_wav, "wav")]:
            t0 = time.time()
            raw = m.generate(texto, language="pt", voice_clone_prompt=prompt,
                             speed=speed, generation_config=cfg)[0]
            wav = _finalizar(np.asarray(raw, dtype=np.float32).squeeze())
            pico = np.abs(wav).max() or 1.0
            saida = os.path.join(SAIDAS_DIR, f"comp_{nome}_{sufixo}.wav")
            sf.write(saida, wav / pico * 0.85, SR)
            print(f"  [{metodo}] {time.time()-t0:.1f}s → {saida}")

    print("\n  4 arquivos gerados. Compare par a par:")
    print("   comp_neutro_pkl.wav    vs  comp_neutro_wav.wav")
    print("   comp_desespero_pkl.wav vs  comp_desespero_wav.wav")

    del m; gc.collect(); torch.cuda.empty_cache()

def main():
    print("=" * 60)
    print("  TESTE: Pandora Speaker Embedding (Opção 1)")
    print("=" * 60)

    if not os.path.exists(WAV_REF):
        print(f"❌ WAV de referência não encontrado: {WAV_REF}")
        sys.exit(1)

    t_total = time.time()
    etapa1_extrair_e_salvar_prompt()
    etapa3_comparacao()
    print(f"\n  Tempo total: {time.time()-t_total:.1f}s")
    print("=" * 60)

if __name__ == "__main__":
    main()
