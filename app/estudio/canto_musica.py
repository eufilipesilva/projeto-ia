# -*- coding: utf-8 -*-
"""Pipeline "Cantar Música": separa o vocal do instrumental (Demucs) e converte
o timbre do vocal isolado pra uma voz clonada (seed-vc), preservando a melodia/
ritmo/pitch reais de quem cantou. Ver memória do projeto "canto-lab-voz-musica"
pro histórico completo — essa é a solução validada; TTS + pitch-shift foi
tentado antes e soava robótico (formantes distorcidos por phase-vocoder).

O seed-vc roda num venv/Python separado (.venv_seedvc, Python 3.11) porque suas
dependências não instalam no Python 3.14 usado pelo resto do projeto. Por isso
a conversão de voz é feita via subprocess, não import direto.

Notas de eficiência (reescrita jun/2026):
- O vocal separado é reaproveitado EM MEMÓRIA pra estimar o pitch — não é relido
  do disco.
- A estimativa de pitch (pyin, caro) roda só sobre um trecho REALMENTE cantado
  (~25s de maior energia), não sobre a música inteira: antes o pyin varria 3-4
  min de áudio 2x, dominando o tempo de CPU do pipeline.
- O Demucs é carregado e movido pra GPU uma única vez (cache de processo).
- Os wavs temporários são apagados ao fim de cada geração.
"""
import os, subprocess, uuid
import numpy as np
import soundfile as sf
import librosa
import torch

PASTA         = os.path.dirname(os.path.abspath(__file__))
LAB_DIR       = os.path.abspath(os.path.join(PASTA, "..", "laboratorios"))
SEEDVC_DIR    = os.path.join(LAB_DIR, "seed-vc")
SEEDVC_PYTHON = os.path.join(LAB_DIR, ".venv_seedvc", "Scripts", "python.exe")
FFMPEG_DIR    = r"C:\Users\Filipe Pereira\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.2-full_build\bin"
TMP_DIR       = os.path.join(PASTA, "saidas", "tmp_web")
os.makedirs(TMP_DIR, exist_ok=True)

# Taxa usada só na análise de pitch (pyin não ganha nada com 44.1k e fica bem
# mais lento; 16k basta pra estimar a fundamental de uma voz).
_SR_ANALISE   = 16000
# Resolução reduzida do pyin (frame/hop maiores): varre a música inteira ~3x
# mais rápido que o padrão e, por cobrir tudo, dá a MESMA mediana de pitch
# arredondada (erro < 0,7 semitom) — sem o viés de pegar só o refrão, que é
# mais agudo. Medido em Roberto Carlos/Frank Sinatra (jun/2026).
_PYIN_FRAME   = 2048
_PYIN_HOP     = 1024

# Tratamento automático de "belting"/picos agudos (ver memória canto-lab):
# o TETO de pitch = registro que a voz-alvo sustenta, estimado como a mediana
# da voz de REFERÊNCIA + 1 oitava. Ele só age quando o cantor ULTRAPASSA esse
# limite (ex: Shania beltando); pra músicas em registro normal (Paula, Ismael)
# fica inócuo. A suavização LEVE do F0 tira o pior do caos dos picos sem
# achatar a música. Validado como a receita simples que venceu (jul/2026).
_TETO_OFFSET_SEMITONS = 12
_SUAVIZAR_JANELA      = 9

# Limite do deslocamento de pitch AUTOMÁTICO. Abaixar a música (shift negativo)
# engrossa/descaracteriza a voz e mata a energia (ex: Shania cantando 1 oitava
# acima da Pandora dava -12) — e é REDUNDANTE com o teto, que já doma os agudos
# SEM derrubar a música. Decisão do Filipe: shift 0 é o ideal → NUNCA abaixar
# (piso 0); só subir vozes graves pro registro da voz-alvo (até +8). Ver
# memória canto-lab.
_SHIFT_MIN_AUTO = 0
_SHIFT_MAX_AUTO = 8


def _limitar_shift(shift):
    """Prende o deslocamento automático em [0, +8]: nunca abaixa (o teto cuida
    dos agudos, e abaixar engrossaria a voz), só sobe vozes graves."""
    return max(_SHIFT_MIN_AUTO, min(_SHIFT_MAX_AUTO, int(shift)))

_DEMUCS_MODEL = None
_DEMUCS_DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def _limpar(*paths):
    """Remove arquivos temporários, ignorando os que já não existem."""
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.remove(p)
        except OSError:
            pass


def _pitch_mediano_midi(y, sr):
    """Mediana do pitch (em MIDI) de um sinal de voz já em memória, via
    librosa.pyin com resolução reduzida (frame/hop maiores) — cobre o sinal
    inteiro rápido, sem viés de seção. Retorna None se não detectar voz."""
    f0, vozeado, _ = librosa.pyin(
        y, sr=sr, fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C6"),
        frame_length=_PYIN_FRAME, hop_length=_PYIN_HOP)
    validos = f0[vozeado]
    validos = validos[~np.isnan(validos)]
    if len(validos) == 0:
        return None
    return float(np.median(librosa.hz_to_midi(validos)))


def calcular_semi_tone_shift(vocal_y, sr_vocal, voz_referencia_path):
    """Deslocamento de pitch (em semitons) entre o cantor original e a voz de
    referência, comparando a mediana de pitch dos dois — em vez de adivinhar
    (ex: sempre ±12, que só acerta quando as vozes já estão ~1 oitava
    distantes). Retorna 0 se não detectar pitch em algum dos dois.

    `vocal_y`/`sr_vocal`: sinal do vocal isolado JÁ em memória (reaproveitado
    da separação, sem reler disco). A referência é curta e é lida direto."""
    if sr_vocal != _SR_ANALISE:
        vocal_y = librosa.resample(vocal_y, orig_sr=sr_vocal, target_sr=_SR_ANALISE)
    m_original = _pitch_mediano_midi(vocal_y, _SR_ANALISE)

    y_ref, _ = librosa.load(voz_referencia_path, sr=_SR_ANALISE, mono=True)
    m_referencia = _pitch_mediano_midi(y_ref, _SR_ANALISE)

    if m_original is None or m_referencia is None:
        return 0
    return int(round(m_referencia - m_original))


def calcular_teto_pitch(voz_referencia_path):
    """Teto de pitch automático pro tratamento de belting: a nota máxima que a
    voz de referência sustenta bem, estimada como a mediana dela + 1 oitava.
    Acima disso, os picos agudos do cantor são comprimidos (senão a voz clonada
    quebra). Só age quando o cantor ultrapassa; inócuo no registro normal.
    Retorna None se não detectar pitch na referência (aí não aplica teto)."""
    y_ref, _ = librosa.load(voz_referencia_path, sr=_SR_ANALISE, mono=True)
    m_ref = _pitch_mediano_midi(y_ref, _SR_ANALISE)
    if m_ref is None:
        return None
    return int(round(m_ref + _TETO_OFFSET_SEMITONS))


def _carregar_demucs():
    """Carrega o htdemucs uma vez por processo e já o deixa na GPU/CPU final,
    pra não repetir a transferência de pesos a cada música."""
    global _DEMUCS_MODEL
    if _DEMUCS_MODEL is None:
        from demucs.pretrained import get_model
        modelo = get_model("htdemucs")
        modelo.eval()
        modelo.to(_DEMUCS_DEVICE)
        _DEMUCS_MODEL = modelo
    return _DEMUCS_MODEL


def separar_vocal_instrumental(caminho_musica, progresso=lambda *a: None):
    """Separa a música em vocal isolado + instrumental (drums+bass+other).
    Retorna (vocal_path, instrumental_path, vocal_y, sr): os dois caminhos wav
    temporários mais o vocal já em memória (pra estimar pitch sem reler disco)."""
    from demucs.apply import apply_model
    progresso(0.10, "Separando vocal do instrumental (Demucs)...")
    model = _carregar_demucs()
    sr = model.samplerate
    y, _ = librosa.load(caminho_musica, sr=sr, mono=False)
    if y.ndim == 1:
        y = np.stack([y, y])
    wav = torch.tensor(y, dtype=torch.float32).unsqueeze(0)
    with torch.no_grad():
        out = apply_model(model, wav, device=_DEMUCS_DEVICE, progress=False)[0]
    out = out.cpu()
    idx = {nome: i for i, nome in enumerate(model.sources)}

    def _mono(stem):
        a = out[idx[stem]].numpy()          # (canais, amostras)
        return a.mean(axis=0) if a.ndim > 1 else a

    vocal = _mono("vocals")
    instrumental = _mono("drums") + _mono("bass") + _mono("other")

    tid = uuid.uuid4().hex
    vocal_path = os.path.join(TMP_DIR, f"{tid}_vocal.wav")
    inst_path = os.path.join(TMP_DIR, f"{tid}_instrumental.wav")
    sf.write(vocal_path, vocal, sr)
    sf.write(inst_path, instrumental, sr)
    return vocal_path, inst_path, vocal, sr


def converter_voz(vocal_path, voz_referencia_path, diffusion_steps=30,
                  inference_cfg_rate=0.7, auto_f0_adjust=False, semi_tone_shift=0,
                  teto_midi=0, suavizar_janela=_SUAVIZAR_JANELA,
                  progresso=lambda *a: None):
    """Roda o seed-vc (subprocess, venv isolado) pra converter o timbre do
    vocal isolado pra voz de referência, preservando a melodia real cantada.

    `inference_cfg_rate` (0-1): quanto mais alto, mais fielmente segue o
    conteúdo/timbre da referência — valores mais baixos (ex: 0.3-0.5) tendem
    a soar menos "puxado"/rouco quando a referência é uma voz muito
    característica (ex: clipes emocionais como "desespero").
    `auto_f0_adjust`: desloca o pitch médio do vocal original pro nível médio
    da voz de referência antes de converter — ajuda quando a voz escolhida
    tem uma faixa de pitch bem diferente da do cantor original (sintoma:
    saída "desafinada").
    `semi_tone_shift`: ajuste manual de pitch em semitons, além do acima.
    `teto_midi`/`suavizar_janela`: tratamento automático de belting (ver
    calcular_teto_pitch); 0 desliga o teto."""
    progresso(0.35, "Convertendo para a voz escolhida (pode levar alguns minutos)...")
    env = os.environ.copy()
    env["PATH"] = FFMPEG_DIR + os.pathsep + env.get("PATH", "")
    cmd = [
        SEEDVC_PYTHON, os.path.join(SEEDVC_DIR, "inference.py"),
        "--source", vocal_path,
        "--target", voz_referencia_path,
        "--output", TMP_DIR,
        "--diffusion-steps", str(diffusion_steps),
        "--inference-cfg-rate", str(inference_cfg_rate),
        "--f0-condition", "True",
        "--auto-f0-adjust", "True" if auto_f0_adjust else "False",
        "--semi-tone-shift", str(int(semi_tone_shift)),
        "--teto-midi", str(float(teto_midi or 0)),
        "--suavizar-janela", str(int(suavizar_janela)),
        "--fp16", "True",
    ]
    resultado = subprocess.run(cmd, cwd=SEEDVC_DIR, env=env, capture_output=True, text=True)
    if resultado.returncode != 0:
        raise RuntimeError(f"seed-vc falhou: {resultado.stderr[-2000:]}")

    base_vocal = os.path.splitext(os.path.basename(vocal_path))[0]
    base_voz = os.path.splitext(os.path.basename(voz_referencia_path))[0]
    convertido = os.path.join(
        TMP_DIR, f"vc_{base_vocal}_{base_voz}_1.0_{diffusion_steps}_{inference_cfg_rate}.wav")
    if not os.path.exists(convertido):
        raise RuntimeError("seed-vc não gerou o arquivo esperado.")
    return convertido


def mixar(voz_convertida_path, instrumental_path, vol_instrumental=0.6, progresso=lambda *a: None):
    """Mixa a voz convertida (que manda na taxa de amostragem) com o
    instrumental, casando a taxa via `librosa.load(sr=...)` pra não haver
    troca de velocidade/pitch por descasamento de sample rate."""
    progresso(0.90, "Mixando com o instrumental...")
    voz, sr = sf.read(voz_convertida_path)
    if voz.ndim > 1:
        voz = voz.mean(axis=1)
    inst, _ = librosa.load(instrumental_path, sr=sr, mono=True)
    n = min(len(voz), len(inst))
    mix = inst[:n] * vol_instrumental + voz[:n] * 1.0
    pico = np.max(np.abs(mix)) or 1.0
    mix = (mix / pico * 0.95).astype(np.float32)
    return mix, sr


def gerar_canto(caminho_musica, voz_referencia_path, diffusion_steps=30,
               vol_instrumental=0.6, inference_cfg_rate=0.7, auto_f0_adjust=False,
               semi_tone_shift="auto", ajuste_fino=0, progresso=lambda *a: None):
    """Pipeline completo: libera VRAM do OmniVoice, separa vocal/instrumental,
    calcula o deslocamento de pitch automaticamente, converte a voz e mixa.
    Retorna (sr, audio) — mesmo formato usado pelas outras rotas do estúdio.
    Limpa os wavs temporários ao final, mesmo se der erro.

    `semi_tone_shift="auto"` (padrão) calcula o deslocamento comparando a
    mediana de pitch do cantor original com a da voz de referência — não
    força oitava inteira (±12), que só funciona quando as vozes calham de
    estar exatamente 1 oitava distantes. `ajuste_fino` soma semitons extras
    por cima do valor calculado, pra correção manual fina se precisar."""
    progresso(0.02, "Liberando VRAM (descarregando OmniVoice)...")
    import motor_v2 as motor
    motor.descarregar_omni()

    vocal_path = inst_path = convertido = None
    try:
        vocal_path, inst_path, vocal_y, sr_vocal = separar_vocal_instrumental(
            caminho_musica, progresso)

        if semi_tone_shift == "auto":
            progresso(0.30, "Calculando deslocamento de pitch (comparando registros)...")
            shift = _limitar_shift(calcular_semi_tone_shift(vocal_y, sr_vocal, voz_referencia_path))
        else:
            shift = int(semi_tone_shift)
        shift += int(ajuste_fino)

        # tratamento automático de belting: teto = registro sustentável da voz-alvo
        teto = calcular_teto_pitch(voz_referencia_path) or 0

        convertido = converter_voz(vocal_path, voz_referencia_path, diffusion_steps,
                                   inference_cfg_rate, auto_f0_adjust, shift,
                                   teto, _SUAVIZAR_JANELA, progresso)
        mix, sr = mixar(convertido, inst_path, vol_instrumental, progresso)
        progresso(1.0, "Concluído!")
        return sr, mix
    finally:
        _limpar(vocal_path, inst_path, convertido)
