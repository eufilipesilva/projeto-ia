# -*- coding: utf-8 -*-
"""Laboratório: voz "acompanhando" um instrumental.

Escopo assumido (ver conversa de 2026-07-01): o OmniVoice não é um modelo de
canto (SVS) — ele não aceita melodia (MIDI/pitch-curve) como entrada, só texto
+ instruct + duration/speed. Não existe "seguir a melodia nota a nota" sem
trocar de modelo (DiffSinger/VISinger2, que exigiriam treino/dataset próprio
em pt-BR — inviável no escopo atual).

O que este módulo faz de fato:
1. analisar_instrumental()   — detecta BPM e tonalidade (key) do instrumental.
2. gerar_voz_alinhada()      — gera a voz com OmniVoice pedindo uma duration=
   alvo (alinhamento de TIMING com a seção da música).
3. corrigir_pitch_escala()   — quantiza o pitch da voz gerada para a escala
   detectada, nota a nota por segmento (aproximação, não canto preciso).
4. compor_vocal_sobre_musica() — orquestra os 3 passos acima e mixa com o
   instrumental.

Usa OmniVoice via app/estudio/motor_v2.py (mesmo modelo/perfil de voz já
usado no Estúdio). Depende só do que já está no requirements.txt do estúdio
(librosa, soundfile, numpy) — nenhuma lib nova.
"""
import os, sys
import numpy as np
import soundfile as sf
import librosa

PASTA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(PASTA, "..", "estudio"))
import motor_v2 as mv  # carregar_omni, perfil_voz, _criar_prompt_voz, _cfg, SR

SR = mv.SR

# ── 1. Análise do instrumental ──────────────────────────────────────────────
_NOTAS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Perfis de Krumhansl-Schmuckler (correlação tom-a-tom) pra estimar a key.
_PERFIL_MAIOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_PERFIL_MENOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def analisar_instrumental(path):
    """Retorna {bpm, tonica, modo, duracao, sr} do instrumental em `path`."""
    y, sr = librosa.load(path, sr=SR, mono=True)
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    bpm = float(np.asarray(tempo).reshape(-1)[0])

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    perfil_musica = chroma.mean(axis=1)

    melhor_corr, tonica, modo = -1.0, "C", "maior"
    for i in range(12):
        maior = np.roll(_PERFIL_MAIOR, i)
        menor = np.roll(_PERFIL_MENOR, i)
        corr_maior = np.corrcoef(perfil_musica, maior)[0, 1]
        corr_menor = np.corrcoef(perfil_musica, menor)[0, 1]
        if corr_maior > melhor_corr:
            melhor_corr, tonica, modo = corr_maior, _NOTAS[i], "maior"
        if corr_menor > melhor_corr:
            melhor_corr, tonica, modo = corr_menor, _NOTAS[i], "menor"

    return {
        "bpm": round(bpm, 1),
        "tonica": tonica,
        "modo": modo,
        "duracao": round(len(y) / sr, 2),
        "sr": sr,
    }


def _escala_semitons(tonica, modo):
    """Graus (em semitons a partir de C) da escala maior ou menor natural."""
    passos = [0, 2, 4, 5, 7, 9, 11] if modo == "maior" else [0, 2, 3, 5, 7, 8, 10]
    raiz = _NOTAS.index(tonica)
    return sorted((raiz + p) % 12 for p in passos)


# ── 2. Geração com timing alinhado ──────────────────────────────────────────
def gerar_voz_alinhada(perfil, texto, duracao_alvo, num_step=32, guidance_scale=3.0,
                       progresso=lambda *a: None):
    """Gera a voz pedindo duration=duracao_alvo ao OmniVoice. Se o resultado
    ainda sair fora da duração (o modelo só aproxima), corrige com
    time-stretch fino (librosa) pra bater exatamente com o compasso alvo."""
    m = mv.carregar_omni()
    prompt = mv._criar_prompt_voz(m, perfil)
    cfg = mv._cfg(num_step, guidance_scale)
    progresso(0.1, "Gerando voz com duração alvo...")
    wav = m.generate(mv._com_ponto(texto), voice_clone_prompt=prompt,
                     generation_config=cfg, duration=float(duracao_alvo))[0]
    wav = np.asarray(wav, dtype=np.float32).squeeze()

    dur_real = len(wav) / SR
    if dur_real > 0 and abs(dur_real - duracao_alvo) > 0.05:
        progresso(0.6, "Ajustando timing (time-stretch)...")
        taxa = dur_real / duracao_alvo  # >1 = precisa acelerar
        wav = librosa.effects.time_stretch(wav, rate=taxa)
    return mv._saida(wav)


# ── 3. Correção de pitch pra escala detectada ───────────────────────────────
def _correcao_mais_proxima(midi_continuo, escala):
    """Distância assinada (em semitons, valor contínuo) até a nota da escala
    mais próxima — sem arredondar o pitch de entrada, pra não gerar saltos
    maiores que o necessário."""
    melhor = None
    for s in escala:
        for oitava in (-12, 0, 12):
            alvo = s + oitava
            d = alvo - midi_continuo
            if melhor is None or abs(d) < abs(melhor):
                melhor = d
    return melhor


def corrigir_pitch_escala(wav, tonica, modo, sr=SR, intensidade=0.35,
                          correcao_max=1.5, crossfade_ms=15):
    """Segmenta a voz por trecho de fala (via silêncio), detecta o pitch médio
    de cada trecho (librosa.pyin) e desloca de forma sutil em direção à nota
    da escala mais próxima. `intensidade` baixa (padrão 0.35) preserva a
    entonação natural da fala — corrigir 100% (tipo Auto-Tune duro) achata a
    prosódia e soa robótico, porque cada trecho vira um único pitch constante.
    `correcao_max` limita o desvio (evita saltos grandes por erro de detecção
    de pitch). `crossfade_ms` suaviza a transição no início/fim do trecho
    corrigido pra evitar cliques."""
    escala = set(_escala_semitons(tonica, modo))
    intervalos = librosa.effects.split(wav, top_db=30)
    if len(intervalos) == 0:
        return wav

    saida = wav.copy()
    cf = max(1, int(sr * crossfade_ms / 1000))
    for ini, fim in intervalos:
        seg = wav[ini:fim]
        if len(seg) < int(0.12 * sr):
            continue
        f0, voz_detectada, _ = librosa.pyin(
            seg, sr=sr, fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C6"))
        f0_validos = f0[voz_detectada] if voz_detectada is not None else f0[~np.isnan(f0)]
        f0_validos = f0_validos[~np.isnan(f0_validos)] if f0_validos is not None else np.array([])
        if len(f0_validos) == 0:
            continue

        midi_medio = float(librosa.hz_to_midi(np.median(f0_validos)))
        correcao = _correcao_mais_proxima(midi_medio, escala) * intensidade
        correcao = float(np.clip(correcao, -correcao_max, correcao_max))
        if abs(correcao) < 0.08:
            continue

        seg_corrigido = librosa.effects.pitch_shift(seg, sr=sr, n_steps=correcao)
        n = min(len(seg_corrigido), fim - ini)
        seg_corrigido = seg_corrigido[:n]

        # crossfade nas bordas com o áudio original, pra não haver clique
        janela = np.ones(n, dtype=np.float32)
        b = min(cf, n // 2)
        if b > 0:
            rampa = 0.5 * (1 - np.cos(np.linspace(0, np.pi, b)))
            janela[:b] = rampa
            janela[-b:] = rampa[::-1]
        original = wav[ini:ini + n]
        saida[ini:ini + n] = original * (1 - janela) + seg_corrigido * janela

    return saida


def _pitch_medio(seg, sr):
    """Mediana do pitch (em MIDI) de um trecho de áudio, ou None se não detectar voz."""
    f0, voz_detectada, _ = librosa.pyin(
        seg, sr=sr, fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C6"))
    validos = f0[voz_detectada] if voz_detectada is not None else f0[~np.isnan(f0)]
    validos = validos[~np.isnan(validos)] if validos is not None else np.array([])
    if len(validos) == 0:
        return None
    return float(librosa.hz_to_midi(np.median(validos)))


def seguir_melodia_real(wav_gerado, vocal_ref_path, sr=SR, inicio_seg=0.0, duracao_seg=None,
                        intensidade=0.5, correcao_max=4.0, crossfade_ms=15):
    """Em vez de quantizar pra uma escala genérica, usa a melodia REAL extraída
    do vocal isolado (ex: via Demucs) como alvo. Mapeia cada trecho de fala da
    voz gerada, proporcionalmente no tempo, pro trecho correspondente do vocal
    de referência, e corrige o pitch médio na direção do pitch real cantado
    ali — não pra nota de escala mais próxima. `intensidade` baixa preserva a
    entonação natural (ver corrigir_pitch_escala para o porquê)."""
    y_ref, _ = librosa.load(vocal_ref_path, sr=sr, mono=True,
                            offset=inicio_seg, duration=duracao_seg)
    if len(y_ref) < int(0.2 * sr):
        return wav_gerado

    intervalos = librosa.effects.split(wav_gerado, top_db=30)
    if len(intervalos) == 0:
        return wav_gerado

    dur_gerado = len(wav_gerado) / sr
    dur_ref = len(y_ref) / sr
    saida = wav_gerado.copy()
    cf = max(1, int(sr * crossfade_ms / 1000))

    for ini, fim in intervalos:
        seg = wav_gerado[ini:fim]
        if len(seg) < int(0.12 * sr):
            continue

        t_ini = (ini / sr) / dur_gerado * dur_ref
        t_fim = (fim / sr) / dur_gerado * dur_ref
        ref_seg = y_ref[int(t_ini * sr):int(t_fim * sr)]
        if len(ref_seg) < int(0.1 * sr):
            continue

        midi_alvo = _pitch_medio(ref_seg, sr)
        midi_atual = _pitch_medio(seg, sr)
        if midi_alvo is None or midi_atual is None:
            continue

        correcao = (midi_alvo - midi_atual) * intensidade
        correcao = float(np.clip(correcao, -correcao_max, correcao_max))
        if abs(correcao) < 0.08:
            continue

        seg_corrigido = librosa.effects.pitch_shift(seg, sr=sr, n_steps=correcao)
        n = min(len(seg_corrigido), fim - ini)
        seg_corrigido = seg_corrigido[:n]

        janela = np.ones(n, dtype=np.float32)
        b = min(cf, n // 2)
        if b > 0:
            rampa = 0.5 * (1 - np.cos(np.linspace(0, np.pi, b)))
            janela[:b] = rampa
            janela[-b:] = rampa[::-1]
        original = wav_gerado[ini:ini + n]
        saida[ini:ini + n] = original * (1 - janela) + seg_corrigido * janela

    return saida


# ── 4. Orquestração + mix ───────────────────────────────────────────────────
def mixar_com_instrumental(voz, instrumental_path, inicio_seg=0.0, vol_voz=1.0,
                           vol_instrumental=0.6, sr=SR):
    fundo, _ = librosa.load(instrumental_path, sr=sr, mono=True)
    offset = int(inicio_seg * sr)
    fim = offset + len(voz)
    if fim > len(fundo):
        fundo = np.pad(fundo, (0, fim - len(fundo)))

    mix = fundo.copy() * vol_instrumental
    mix[offset:fim] += voz * vol_voz
    pico = np.max(np.abs(mix)) or 1.0
    return (mix / pico * 0.95).astype(np.float32)


def compor_vocal_sobre_musica(perfil, texto, instrumental_path, inicio_seg, duracao_alvo,
                              saida_path, intensidade_correcao=1.0, vol_instrumental=0.6,
                              progresso=lambda *a: None):
    """Pipeline completo: analisa a música, gera a voz com timing encaixado no
    trecho [inicio_seg, inicio_seg+duracao_alvo], corrige o pitch pra escala
    detectada e mixa. Salva o resultado em `saida_path`. Retorna a análise do
    instrumental (bpm/key) pra você conferir o que foi detectado."""
    progresso(0.05, "Analisando instrumental...")
    analise = analisar_instrumental(instrumental_path)

    voz = gerar_voz_alinhada(perfil, texto, duracao_alvo, progresso=progresso)

    progresso(0.7, "Corrigindo pitch para a escala detectada...")
    voz = corrigir_pitch_escala(voz, analise["tonica"], analise["modo"],
                                intensidade=intensidade_correcao)

    progresso(0.85, "Mixando com o instrumental...")
    mix = mixar_com_instrumental(voz, instrumental_path, inicio_seg=inicio_seg,
                                 vol_instrumental=vol_instrumental)

    sf.write(saida_path, mix, SR)
    progresso(1.0, "Concluído.")
    return analise


if __name__ == "__main__":
    # Teste rápido de linha de comando:
    #   python canto_lab.py instrumental.wav ref_voz.wav "letra da música" inicio_seg duracao_seg saida.wav
    if len(sys.argv) < 7:
        print("Uso: python canto_lab.py <instrumental.wav> <ref_voz.wav> <texto> "
              "<inicio_seg> <duracao_seg> <saida.wav>")
        sys.exit(1)
    instrumental, ref_voz, texto, inicio, duracao, saida = sys.argv[1:7]
    perfil = mv.perfil_voz(ref_voz)
    analise = compor_vocal_sobre_musica(
        perfil, texto, instrumental, float(inicio), float(duracao), saida,
        progresso=lambda p, msg: print(f"[{p*100:5.1f}%] {msg}"))
    print("Instrumental detectado:", analise)
