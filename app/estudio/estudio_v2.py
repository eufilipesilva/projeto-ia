# -*- coding: utf-8 -*-
"""Estúdio de Voz v2 — Interface Modernizada com Novas Abas
Roda: python app/estudio/estudio_v2.py
Abre: http://127.0.0.1:5007 (porta diferente para não colidir com v1)
"""
import os, sys, glob, json, re
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if sys.platform == "win32":
    import asyncio.proactor_events as _pe
    _orig_ccl = _pe._ProactorBasePipeTransport._call_connection_lost
    def _safe_ccl(self, exc):
        try: _orig_ccl(self, exc)
        except ConnectionResetError: pass
    _pe._ProactorBasePipeTransport._call_connection_lost = _safe_ccl

import gradio as gr
import motor_v2 as motor

PASTA = os.path.dirname(os.path.abspath(__file__))
VOZES = os.path.join(PASTA, "vozes")

IDIOMAS = ["pt", "en", "zh", "ja", "ko", "fr", "de", "es", "ru", "ar", "hi", "it", "nl", "tr", "pl"]

_VOZ_GENERO = {"feminino": "female", "masculino": "male"}
_VOZ_IDADE  = {"criança": "child", "jovem": "young adult", "adulto": "middle-aged", "idoso": "elderly"}
_VOZ_TOM    = {"grave": "low pitch", "moderado": "moderate pitch", "agudo": "high pitch"}
_VOZ_ESTILO = {"normal": "", "sussurro": "whisper", "expressivo": "expressive"}

GENEROS_TRAILER = ["Terror", "Ficção Científica", "Romance", "Ação", "Comédia"]
TEMAS_MEDITACAO = ["Floresta", "Oceano", "Cosmos", "Sono Profundo", "Foco"]
DURACAO_MEDITACAO = [5, 10, 20]
MODOS_BATALHA = ["sério", "caos"]

def listar_vozes():
    fs = [f for f in glob.glob(os.path.join(VOZES, "*.wav"))
          if not os.path.basename(f).startswith("_")]
    return sorted(os.path.basename(f) for f in fs)

def _prog(progress):
    return lambda f, d="": progress(min(max(f, 0), 1), desc=d)

# ── Contador de Histórias ──────────────────────────────────────────────────
EXEMPLO_HIST = (
    "Era uma vez uma menininha que adorava brincar no jardim.\n"
    "– Mamãe, posso ir ver a vovó? – perguntou ela, animada.\n"
    "– Pode sim, mas tome cuidado no caminho – respondeu a mãe.\n"
    "No bosque, um lobo apareceu e rosnou:\n"
    "– Aonde vais, menininha?\n"
    "A menina correu, com muito medo, até a casa da vovó."
)

def gerar_historia(perfil, texto, ritmo, sussurro, fundo, vol_fundo, cauda_fundo,
                   progress=gr.Progress()):
    if not perfil:
        raise gr.Error("Analise uma voz primeiro (aba Clone).")
    if not (texto or "").strip():
        raise gr.Error("Escreva a história.")
    audio, roteiro = motor.sintetizar_historia(
        perfil, texto, float(ritmo), bool(sussurro),
        fundo or None, float(vol_fundo), float(cauda_fundo), _prog(progress))
    tabela = "\n".join(f"- **{q}** (*{e}*): {f}" for q, e, f in roteiro)
    return (motor.SR, audio), "### Roteiro\n" + tabela

# ── Comédia e Game Show ────────────────────────────────────────────────────
EXEMPLO_COMEDIA = (
    "Boa noite, almas penadas e criaturas deste auditório dos condenados!\n"
    "Eu sou a Pandora, secretária oficial do senhor Hades, e hoje eu vim alegrar a sua eternidade de sofrimento!\n"
    "Façam barulho, suas almas, porque quem ficar calado vai direto pra fila do caldeirão!\n"
    "Isso, assim que eu gosto! Sintam esse calorzinho do inferno, não é uma delícia?\n"
    "E para começar a nossa noite de tormentos, recebam o nosso primeiro condenado!\n"
    "Ele já foi o terror das noites de lua cheia, mas hoje vive no seguro-desemprego. O RUFUS!\n"
    "RUFUS: Boa noite... eu era o lobisomem mais temido da floresta, mas ninguém tem medo de mim.\n"
    "Ai, que coisa mais triste, Rufus! Um lobisomem aposentado por falta de assombração!\n"
    "RUFUS: Eu uivo a noite inteira e só consigo uma reclamação dos vizinhos.\n"
    "Talvez seja porque você uiva igual a um chihuahua resfriado, meu querido.\n"
    "RUFUS: Isso foi maldade, Pandora!\n"
    "Eu sei, e eu adorei cada segundo! Bem-vindo ao meu mundo, Rufus!\n"
    "Uma salva de palmas para o nosso lobisomem fracassado, antes que ele comece a chorar!\n"
    "E agora a nossa próxima alma em pena. Essa daqui assombra... ou pelo menos tenta.\n"
    "Direto do além, a fantasma mais atrapalhada do submundo, a GISELE!\n"
    "GISELE: Buuu! Eu vim assombrar todos vocês nesta noite sombria!\n"
    "Gisele, querida, a luz está acesa e você está tremendo de medo.\n"
    "GISELE: É que... eu tenho um pavor terrível do escuro, sabe?\n"
    "Uma fantasma com medo do escuro! O senhor Hades vai rir disso por mil anos!\n"
    "GISELE: Você não precisava contar isso pra todo mundo!\n"
    "Ah, mas eu precisava sim, é o melhor momento do meu dia!\n"
    "E agora está na hora do nosso quadro preferido: a Roleta do Hades!\n"
    "As regras são simples, Gisele: responda a minha pergunta, ou caia no caldeirão de lava!\n"
    "GISELE: Espera, isso não é nada justo!\n"
    "Justo? Querida, isto aqui é o inferno, ninguém nunca prometeu justiça!\n"
    "Primeira e única pergunta: quanto é dois mais dois?\n"
    "GISELE: É... é cinco?\n"
    "Resposta errada! Diga um oizinho para a lava, Gisele!\n"
    "Não se preocupem, ela já estava morta mesmo, no máximo vai ficar tostadinha!\n"
    "Bom, minhas criaturas, a nossa noite chega ao fim, infelizmente para vocês.\n"
    "Antes de ir, o meu recado: comportem-se na sua eternidade, porque eu estou sempre de olho.\n"
    "E lembrem-se: aqui no submundo, a saída é sempre só de entrada!\n"
    "Foi a Pandora, a anfitriã favorita do inferno. Durmam com um olho aberto. Boa noite!"
)

def gerar_comedia(perfil, texto, ritmo, vol_sfx, vol_plateia, intensidade,
                  abertura, vol_abertura, progress=gr.Progress()):
    if not perfil:
        raise gr.Error("Analise uma voz primeiro (aba Clone).")
    if not (texto or "").strip():
        raise gr.Error("Escreva o quadro/história.")
    audio, roteiro = motor.sintetizar_comedia(
        perfil, texto, float(ritmo), float(vol_sfx), float(vol_plateia),
        float(intensidade), abertura or None, float(vol_abertura), _prog(progress))
    tabela = "\n".join(
        f"- **{q}** (*{e}*){(' 🔊 `' + s + '`') if s and s != 'nenhum' else ''}: {f}"
        for q, e, f, s in roteiro)
    return (motor.SR, audio), "### Roteiro\n" + tabela

def hora_da_loucura(progress=gr.Progress()):
    progress(0.2, desc="A IA está inventando o programa...")
    return motor.gerar_roteiro_comedia()

def roteiro_do_pdf(pdf, faixa, n_perg, progress=gr.Progress()):
    if not pdf:
        raise gr.Error("Suba um arquivo PDF primeiro.")
    progress(0.1, desc="Lendo o PDF...")
    texto, n_pag, trunc = motor._ler_pdf(pdf)
    if not texto.strip():
        raise gr.Error("Não encontrei texto neste PDF (pode ser escaneado/imagem).")
    progress(0.4, desc="A Pandora está montando o game show...")
    roteiro = motor.gerar_gameshow_educativo(texto, (faixa or "crianças").strip(), int(n_perg))
    aviso = (f"✅ Roteiro criado do PDF ({n_pag} páginas)."
             + (" PDF longo — usei o começo do material." if trunc else "")
             + " Revise/edite abaixo e clique em Gerar o game show.")
    return roteiro, aviso

# ── Melhoria 1.1: Design de Voz com linguagem natural ─────────────────────
def gerar_design_livre(desc_voz, texto, idioma, steps, guidance, velocidade, progress=gr.Progress()):
    if not (desc_voz or "").strip():
        raise gr.Error("Descreva a voz que deseja criar.")
    if not (texto or "").strip():
        raise gr.Error("Escreva um texto.")
    progresso = _prog(progress)
    instruct, msg = motor.interpretar_descricao_voz(desc_voz, progresso)
    if not instruct:
        raise gr.Error(msg)
    progresso(0.4, "Gerando áudio...")
    audio = motor.sintetizar_design(
        instruct, texto, idioma, int(steps), float(guidance), float(velocidade), progresso)
    return (motor.SR, audio), msg

# ── Trailer ────────────────────────────────────────────────────────────────
def gerar_trailer(genero, logline, musica, vol_musica, progress=gr.Progress()):
    if not (logline or "").strip():
        raise gr.Error("Escreva uma logline para o trailer.")
    progresso = _prog(progress)
    progresso(0.1, "Gerando roteiro...")
    roteiro = motor.gerar_roteiro_trailer(genero, logline, progresso=progresso)
    if not roteiro.strip():
        raise gr.Error("Não consegui gerar o roteiro. Tente novamente.")
    progresso(0.4, "Sintetizando voz épica...")
    audio = motor.sintetizar_design(
        "male, middle-aged, low pitch, expressive",
        roteiro, "pt", 32, 3.0, 1.0, progresso)
    if musica:
        progresso(0.9, "Misturando com música...")
        fundo = motor._carregar_fundo(musica, float(vol_musica))
        if fundo is not None:
            audio = motor._misturar_fundo(audio, fundo, 2.0)
    return (motor.SR, audio), roteiro

# ── Meditação ──────────────────────────────────────────────────────────────
def gerar_meditacao(tema, duracao, intensidade_sussurro, fundo, vol_fundo, perfil, progress=gr.Progress()):
    if not perfil:
        raise gr.Error("Analise uma voz primeiro (aba Clone).")
    if not (tema or "").strip():
        raise gr.Error("Escolha um tema de meditação.")
    progresso = _prog(progress)
    progresso(0.1, "Gerando script...")
    script, pausas = motor.gerar_meditacao(tema, duracao, intensidade_sussurro, progresso)
    if not script:
        raise gr.Error("Erro ao gerar a meditação.")
    progresso(0.5, "Sintetizando meditação...")
    partes_texto = re.split(r'\[pausa \d+s\]|\[respire\]', script)
    partes_texto = [s.strip() for s in partes_texto if s.strip()]

    # une todos os segmentos de texto em um único texto para síntese contínua
    # inserindo pausas via silêncio depois da síntese
    audio_segs = []
    texto_completo = " ".join(partes_texto)
    try:
        progresso(0.6, "Gerando voz da meditação...")
        # velocidade 0.65 → fala mais lenta, contemplativa
        wav = motor.sintetizar_clone(perfil, texto_completo, "pt", 32, 3.5, 0.65, progresso)
        # eco suave (55 ms, decay 0.18) cria profundidade onírica
        wav = motor._eco(wav, delay_ms=55, decay=0.18)
        # sussurro proporcional à intensidade
        if float(intensidade_sussurro) > 0:
            wav = motor._sussurro(wav)
        # espectro mais escuro/sedativo
        wav = motor._brilho(wav, 0.72)
        audio_segs.append(wav)
    except Exception as e:
        raise gr.Error(f"Erro na síntese: {e}")

    # adiciona silêncio de cauda (simula duração total desejada)
    cauda_seg = max(0, int(duracao) * 60 - len(audio_segs[0]) // motor.SR) if audio_segs else 0
    audio = audio_segs[0] if audio_segs else np.zeros(1, dtype=np.float32)

    if fundo:
        progresso(0.95, "Adicionando ambiente...")
        fundo_wav = motor._carregar_fundo(fundo, float(vol_fundo))
        if fundo_wav is not None:
            audio = motor._misturar_fundo(audio, fundo_wav, float(cauda_seg))

    return (motor.SR, audio)

# ── Rádio Pandora ──────────────────────────────────────────────────────────
def gerar_radio(tema, vinheta, vol_vinheta, perfil, progress=gr.Progress()):
    if not perfil:
        raise gr.Error("Analise a voz da Pandora na aba Clone primeiro.")
    if not (tema or "").strip():
        raise gr.Error("Escolha um tema para o episódio de rádio.")
    progresso = _prog(progress)
    progresso(0.05, "Gerando segmentos...")
    segmentos = motor.gerar_radio(tema, progresso)
    progresso(0.95, "Sintetizando e montando...")

    # Segmentos de monólogo (abertura, noticias, quadro, encerramento) → sintetizar_clone
    # Segmento de entrevista tem formato PANDORA:/CONVIDADO: → sintetizar_comedia
    audios_seg = {}
    nomes_comedia = {"entrevista"}
    for i, (seg_nome, roteiro_seg) in enumerate(segmentos.items()):
        progresso(0.95 * (i + 1) / len(segmentos), f"Sintetizando {seg_nome}...")
        if not (roteiro_seg or "").strip():
            continue
        try:
            if seg_nome in nomes_comedia:
                wav, _ = motor.sintetizar_comedia(perfil, roteiro_seg, 1.0, 0.6, 0.06, 1.0)
            else:
                wav = motor.sintetizar_clone(perfil, roteiro_seg, "pt", 32, 3.0, 1.0)
            audios_seg[seg_nome] = wav
        except Exception as e:
            print(f"Erro em {seg_nome}: {e}")

    if vinheta:
        vinheta_wav = motor._carregar_fundo(vinheta, float(vol_vinheta))
    else:
        vinheta_wav = None

    tudo = []
    if vinheta_wav is not None:
        tudo.append(vinheta_wav)
        tudo.append(np.zeros(int(0.3 * motor.SR)))

    for seg_nome in ['abertura', 'noticias', 'entrevista', 'quadro', 'encerramento']:
        if seg_nome in audios_seg:
            tudo.append(audios_seg[seg_nome])
            tudo.append(np.zeros(int(2 * motor.SR)))

    if vinheta_wav is not None:
        tudo.append(vinheta_wav)

    audio_final = np.concatenate(tudo) if tudo else np.zeros(1, dtype=np.float32)

    return (motor.SR, audio_final)

# ── Batalha de Vozes ───────────────────────────────────────────────────────
def gerar_batalha(nome1, desc1, nome2, desc2, tema, modo, progress=gr.Progress()):
    if not (nome1 or "").strip() or not (nome2 or "").strip():
        raise gr.Error("Dê nomes aos dois debatedores.")
    if not (tema or "").strip():
        raise gr.Error("Digite o tema do debate.")
    progresso = _prog(progress)
    progresso(0.1, "Gerando diálogo...")
    roteiro = motor.gerar_batalha(nome1, desc1, nome2, desc2, tema, modo, progresso)
    if not roteiro:
        raise gr.Error("Erro ao gerar o debate.")

    progresso(0.5, "Sintetizando debate...")
    # Sintetiza cada fala alternando entre duas instruções de voz
    beats, falantes = motor._beats_comedia(roteiro)
    instruct1, _ = motor.interpretar_descricao_voz(desc1, progresso) if (desc1 or "").strip() else (None, "")
    instruct2, _ = motor.interpretar_descricao_voz(desc2, progresso) if (desc2 or "").strip() else (None, "")
    instruct1 = instruct1 or "male, middle-aged, low pitch"
    instruct2 = instruct2 or "female, young adult, high pitch, expressive"

    # monta texto único por voz para sintetizar em dois passes
    linhas_v1 = [txt for (_, txt), fal in zip(beats, falantes) if fal == motor._norm_nome(nome1)]
    linhas_v2 = [txt for (_, txt), fal in zip(beats, falantes) if fal == motor._norm_nome(nome2)]
    linhas_narr = [txt for (_, txt), fal in zip(beats, falantes) if fal == "narrador"]

    segs_audio = []
    quem_lista = []
    try:
        m_omni = motor.carregar_omni()
        cfg = motor._cfg()
        for (_, txt), fal in zip(beats, falantes):
            inst = instruct1 if fal == motor._norm_nome(nome1) else instruct2
            kw = dict(language="pt", generation_config=cfg, instruct=inst)
            raw = m_omni.generate(motor._com_ponto(txt), **kw)[0]
            wav = np.asarray(raw, dtype=np.float32).squeeze()
            wav = motor.finalizar(wav)
            segs_audio.append(wav)
            quem_lista.append(fal)
        motor.descarregar_omni()
        audio = motor._montar(segs_audio, quem_lista)
    except Exception as e:
        motor.descarregar_omni()
        raise gr.Error(f"Erro na síntese da batalha: {e}")

    return (motor.SR, audio), roteiro

# ── Personagem Infinito (interativo) ───────────────────────────────────────
personagens_salvos = {}

def carregar_personagens():
    pasta_pers = os.path.join(PASTA, "personagens")
    os.makedirs(pasta_pers, exist_ok=True)
    global personagens_salvos
    personagens_salvos = {}
    for f in glob.glob(os.path.join(pasta_pers, "*.json")):
        try:
            with open(f, encoding="utf-8") as fp:
                personagens_salvos[os.path.basename(f)[:-5]] = json.load(fp)
        except:
            pass
    return list(personagens_salvos.keys())

def salvar_personagem(nome, personalidade, vozes_desc, quirks, tom_emocional):
    if not (nome or "").strip():
        raise gr.Error("Dê um nome ao personagem.")
    pasta_pers = os.path.join(PASTA, "personagens")
    os.makedirs(pasta_pers, exist_ok=True)
    pers_json = {
        "nome": nome,
        "personalidade": personalidade,
        "vozes_desc": vozes_desc,
        "quirks": quirks,
        "tom_emocional": tom_emocional,
    }
    with open(os.path.join(pasta_pers, f"{nome}.json"), "w", encoding="utf-8") as f:
        json.dump(pers_json, f, ensure_ascii=False, indent=2)
    global personagens_salvos
    personagens_salvos[nome] = pers_json
    return f"✅ Personagem '{nome}' salvo!", list(personagens_salvos.keys())

def conversar_com_personagem(nome_pers, fala_usuario, historico_json, progress=gr.Progress()):
    if not (nome_pers or "").strip():
        raise gr.Error("Selecione um personagem.")
    if not (fala_usuario or "").strip():
        raise gr.Error("Escreva algo para dizer.")

    if nome_pers not in personagens_salvos:
        raise gr.Error(f"Personagem '{nome_pers}' não encontrado.")

    progresso = _prog(progress)
    progresso(0.2, "Pensando...")

    historico = json.loads(historico_json) if historico_json else []
    resposta, emoção = motor.responder_personagem(
        personagens_salvos[nome_pers], historico, fala_usuario, progresso)

    historico.append((fala_usuario, resposta))
    historico = historico[-10:]
    historico_novo = json.dumps(historico, ensure_ascii=False)

    try:
        progresso(0.7, "Sintetizando voz...")
        desc_voz = personagens_salvos[nome_pers].get("vozes_desc", "")
        instruct, _ = motor.interpretar_descricao_voz(desc_voz, progresso) if desc_voz else (None, "")
        if instruct:
            audio = motor.sintetizar_design(instruct, resposta, "pt", 32, 3.0, 1.0, progresso)
        else:
            audio = np.zeros(1, dtype=np.float32)
    except:
        audio = np.zeros(1, dtype=np.float32)

    texto_chat = "\n".join([f"👤 Você: {u}\n🎭 {nome_pers}: {r}" for u, r in historico])

    return (motor.SR, audio), historico_novo, texto_chat

# ── Funções originais ──────────────────────────────────────────────────────
def analisar(upload, escolhida, ref_text):
    cam = upload or (os.path.join(VOZES, escolhida) if escolhida else None)
    if not cam:
        return None, "⚠️ Suba uma voz ou escolha uma da lista."
    try:
        p = motor.perfil_voz(cam, ref_text=ref_text or None)
    except Exception as e:
        return None, f"❌ {e}"
    fonte = f"_{p['ref_text'][:80]}_" if p["ref_text"] else "sem transcrição"
    return p, (f"✅ Voz pronta! ({p['dur']}s) — ritmo base {p['base_speed']:.2f} — ref: {fonte}")

def gerar_clone(perfil, texto, idioma, steps, guidance, velocidade, progress=gr.Progress()):
    if not perfil:
        raise gr.Error("Analise uma voz primeiro.")
    if not (texto or "").strip():
        raise gr.Error("Escreva um texto.")
    audio = motor.sintetizar_clone(
        perfil, texto, idioma, int(steps), float(guidance), float(velocidade), _prog(progress))
    return (motor.SR, audio)

# ── CSS Moderno ────────────────────────────────────────────────────────────
css_moderno = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');

:root {
    --primary-color: #8b5cf6;
    --primary-dark: #7c3aed;
    --accent: #ec4899;
    --bg-dark: #0f172a;
    --bg-mid: #1e293b;
    --bg-light: #334155;
    --text-main: #f1f5f9;
    --text-dim: #cbd5e1;
}

* {
    font-family: 'Inter', sans-serif !important;
}

body, #root {
    background: linear-gradient(135deg, var(--bg-dark) 0%, #1a1f3a 100%) !important;
    color: var(--text-main) !important;
}

.gradio-container {
    background: transparent !important;
    max-width: 1400px !important;
}

.tab-nav button {
    font-weight: 600 !important;
    border-radius: 12px !important;
    margin: 0 4px !important;
    transition: all 0.3s !important;
    background: var(--bg-mid) !important;
    color: var(--text-dim) !important;
    border: 2px solid transparent !important;
}

.tab-nav button:hover {
    background: var(--bg-light) !important;
    border-color: var(--primary-color) !important;
}

.tab-nav button.selected {
    background: linear-gradient(135deg, var(--primary-color) 0%, var(--accent) 100%) !important;
    color: white !important;
    box-shadow: 0 8px 24px rgba(139, 92, 246, 0.3) !important;
}

.textbox-label, .slider-label, .dropdown-label, .checkbox-label {
    color: var(--text-main) !important;
    font-weight: 500 !important;
}

textarea, input[type="text"], select {
    background: var(--bg-mid) !important;
    color: var(--text-main) !important;
    border: 2px solid var(--bg-light) !important;
    border-radius: 8px !important;
    padding: 10px !important;
    font-family: 'Inter', sans-serif !important;
}

textarea:focus, input[type="text"]:focus, select:focus {
    border-color: var(--primary-color) !important;
    box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.1) !important;
}

.gr-button {
    background: linear-gradient(135deg, var(--primary-color) 0%, var(--primary-dark) 100%) !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    padding: 12px 24px !important;
    transition: all 0.3s !important;
    cursor: pointer !important;
}

.gr-button:hover {
    box-shadow: 0 8px 24px rgba(139, 92, 246, 0.4) !important;
    transform: translateY(-2px) !important;
}

.gr-button.secondary {
    background: var(--bg-light) !important;
    border: 2px solid var(--primary-color) !important;
    color: var(--primary-color) !important;
}

.gr-button.secondary:hover {
    background: var(--primary-color) !important;
    color: white !important;
}

h1, h2, h3 {
    color: var(--text-main) !important;
    font-weight: 700 !important;
    letter-spacing: -0.5px !important;
}

.gr-markdown {
    color: var(--text-dim) !important;
}

.gr-audio {
    border-radius: 12px !important;
    background: var(--bg-mid) !important;
    border: 2px solid var(--bg-light) !important;
}

.gr-box {
    border-radius: 12px !important;
    background: rgba(51, 65, 85, 0.3) !important;
    border: 1px solid var(--bg-light) !important;
    backdrop-filter: blur(10px) !important;
    padding: 16px !important;
}
"""

# ── Interface Principal ────────────────────────────────────────────────────
def criar_interface():
    with gr.Blocks(title="Estúdio de Voz v2", theme=gr.themes.Soft(primary_hue="purple"), css=css_moderno) as demo:
        gr.Markdown("# 🎙️ Estúdio de Voz v2\n✨ **OmniVoice + Gemma** — 100% Local com Novas Abas Ousadas")

        estado = gr.State(None)
        personagens_lista = carregar_personagens()

        # ── TAB 1: CLONE ORIGINAL ──
        with gr.Tab("🎤 Clone de Voz"):
            gr.Markdown("**Passo 1** — escolha ou suba uma voz. **Passo 2** — gere áudio.")
            with gr.Row():
                up = gr.Audio(label="Subir voz (≥ 3s)", type="filepath", sources=["upload", "microphone"])
                with gr.Column():
                    dd = gr.Dropdown(listar_vozes(), label="ou escolher voz salva",
                                   value=("Pandora.wav" if "Pandora.wav" in listar_vozes() else None))
                    rt = gr.Textbox(label="Transcrição (recomendado)", lines=2)
                    b_an = gr.Button("🔎 Analisar voz", variant="primary")
            status_c = gr.Markdown()
            b_an.click(analisar, [up, dd, rt], [estado, status_c])

            txt_c = gr.Textbox(label="Texto", lines=8, placeholder="Cole aqui o texto...")
            with gr.Row():
                lang_c = gr.Dropdown(IDIOMAS, label="Idioma", value="pt")
                step_c = gr.Slider(8, 64, value=32, step=1, label="Inference steps")
                gs_c = gr.Slider(0.0, 10.0, value=3.0, step=0.1, label="Guidance scale")
                vel_c = gr.Slider(0.5, 2.0, value=1.0, step=0.05, label="Velocidade")
            b_c = gr.Button("🎧 Gerar áudio", variant="primary")
            out_c = gr.Audio(label="Resultado", type="numpy", autoplay=True)
            b_c.click(gerar_clone, [estado, txt_c, lang_c, step_c, gs_c, vel_c], out_c)

        # ── TAB 2: DESIGN LIVRE (MELHORIA 1.1) ──
        with gr.Tab("🎨 Design de Voz Livre"):
            gr.Markdown("Descreva a voz em português natural. A IA traduz para o modelo.")
            desc_voz = gr.Textbox(label="Descreva a voz", lines=4,
                                placeholder="Ex: professora de 55 anos, cansada, com sotaque do interior")
            txt_d = gr.Textbox(label="Texto", lines=8, placeholder="Escreva o texto...")
            with gr.Row():
                lang_d = gr.Dropdown(IDIOMAS, label="Idioma", value="pt")
                step_d = gr.Slider(8, 64, value=32, step=1, label="Steps")
                gs_d = gr.Slider(0.0, 10.0, value=3.0, step=0.1, label="Guidance")
                vel_d = gr.Slider(0.5, 2.0, value=1.0, step=0.05, label="Velocidade")
            b_d = gr.Button("🎤 Gerar com descrição", variant="primary")
            out_d = gr.Audio(label="Resultado", type="numpy", autoplay=True)
            msg_d = gr.Markdown()
            b_d.click(gerar_design_livre, [desc_voz, txt_d, lang_d, step_d, gs_d, vel_d], [out_d, msg_d])

        # ── TAB 3: TRAILER ──
        with gr.Tab("🎬 Gerador de Trailer"):
            gr.Markdown("Crie trailers épicos de cinema em 30-90 segundos.")
            with gr.Row():
                gen_tr = gr.Dropdown(GENEROS_TRAILER, label="Gênero", value="Ficção Científica")
                logline_tr = gr.Textbox(label="Logline", placeholder="um detetive cego descobre que é o assassino que procura")
            musica_tr = gr.Audio(label="🎵 Música épica (opcional)", type="filepath", sources=["upload"])
            vol_musica_tr = gr.Slider(0.0, 1.0, value=0.3, step=0.05, label="Volume da música")
            b_tr = gr.Button("🎬 Gerar Trailer", variant="primary")
            out_tr = gr.Audio(label="Resultado", type="numpy", autoplay=True)
            roteiro_tr = gr.Textbox(label="Roteiro gerado", lines=8, interactive=False)
            b_tr.click(gerar_trailer, [gen_tr, logline_tr, musica_tr, vol_musica_tr], [out_tr, roteiro_tr])

        # ── TAB 4: MEDITAÇÃO ──
        with gr.Tab("🧘 Meditação Guiada"):
            gr.Markdown("Meditações relaxantes com pausas e ambiente sonoro.")
            with gr.Row():
                tema_med = gr.Dropdown(TEMAS_MEDITACAO, label="Tema", value="Floresta")
                duracao_med = gr.Dropdown(DURACAO_MEDITACAO, label="Duração (min)", value=10)
                suss_med = gr.Slider(0.0, 1.0, value=0.3, step=0.1, label="Intensidade do sussurro")

            fundo_med = gr.Audio(label="🎵 Ambiente de fundo", type="filepath", sources=["upload"])
            vol_fundo_med = gr.Slider(0.0, 0.3, value=0.05, step=0.01, label="Volume do ambiente")

            gr.Markdown("**Analise uma voz na aba Clone primeiro.**")
            b_med = gr.Button("🧘 Gerar Meditação", variant="primary")
            out_med = gr.Audio(label="Resultado", type="numpy", autoplay=True)
            b_med.click(gerar_meditacao, [tema_med, duracao_med, suss_med, fundo_med, vol_fundo_med, estado], out_med)

        # ── TAB 5: RÁDIO PANDORA ──
        with gr.Tab("📻 Rádio Pandora"):
            gr.Markdown("Episódio de rádio completo com 5 segmentos gerados:")
            gr.Markdown("1. Abertura • 2. Notícias • 3. Entrevista • 4. Quadro Fixo • 5. Encerramento")

            tema_radio = gr.Textbox(label="Tema do episódio", placeholder="ex: reality shows de culinária")
            vinheta_radio = gr.Audio(label="🎵 Vinheta musical (opcional)", type="filepath", sources=["upload"])
            vol_vinheta = gr.Slider(0.0, 1.0, value=0.85, step=0.05, label="Volume da vinheta")

            gr.Markdown("**Analise a voz da Pandora na aba Clone primeiro.**")
            b_radio = gr.Button("📻 Gerar Episódio de Rádio", variant="primary")
            out_radio = gr.Audio(label="Episódio Completo", type="numpy", autoplay=True)
            b_radio.click(gerar_radio, [tema_radio, vinheta_radio, vol_vinheta, estado], out_radio)

        # ── TAB 6: BATALHA DE VOZES ──
        with gr.Tab("⚔️ Batalha de Vozes"):
            gr.Markdown("Dois personagens com vozes distintas debatem sobre um tema.")

            with gr.Row():
                nome1_bat = gr.Textbox(label="Nome do personagem 1", placeholder="Doutor")
                desc1_bat = gr.Textbox(label="Descrição da voz 1", placeholder="homem sério, profundo")

            with gr.Row():
                nome2_bat = gr.Textbox(label="Nome do personagem 2", placeholder="Bufão")
                desc2_bat = gr.Textbox(label="Descrição da voz 2", placeholder="homem engraçado, agudo")

            tema_bat = gr.Textbox(label="Tema do debate", placeholder="filosofia do absurdo")
            modo_bat = gr.Radio(MODOS_BATALHA, label="Modo", value="sério")

            b_bat = gr.Button("⚔️ Gerar Batalha", variant="primary")
            out_bat = gr.Audio(label="Áudio", type="numpy", autoplay=True)
            roteiro_bat = gr.Textbox(label="Roteiro", lines=10, interactive=False)
            b_bat.click(gerar_batalha, [nome1_bat, desc1_bat, nome2_bat, desc2_bat, tema_bat, modo_bat],
                       [out_bat, roteiro_bat])

        # ── TAB 7: PERSONAGEM INFINITO ──
        with gr.Tab("🎭 Personagem Infinito"):
            gr.Markdown("Crie e converse com personagens salvos com voz e personalidade próprias.")

            with gr.Tabs():
                # Sub-aba: Criar Personagem
                with gr.TabItem("Criar"):
                    nome_pers_novo = gr.Textbox(label="Nome do personagem")
                    pers_novo = gr.Textbox(label="Personalidade (descrição)", lines=4)
                    voz_desc_novo = gr.Textbox(label="Descrição da voz", placeholder="ex: mulher jovem, alegre")
                    quirks_novo = gr.Textbox(label="Maneirismos/Quirks", lines=2, placeholder="ex: sempre ri de próprias piadas")
                    tom_novo = gr.Dropdown(motor.EMO_LISTA, label="Tom emocional padrão", value="neutra")

                    b_salvar_pers = gr.Button("💾 Salvar Personagem", variant="primary")
                    msg_pers = gr.Markdown()
                    pers_list = gr.Dropdown(personagens_lista, label="Personagens salvos", interactive=False)

                    b_salvar_pers.click(salvar_personagem,
                                       [nome_pers_novo, pers_novo, voz_desc_novo, quirks_novo, tom_novo],
                                       [msg_pers, pers_list])

                # Sub-aba: Conversar
                with gr.TabItem("Conversar"):
                    pers_selecionado = gr.Dropdown(personagens_lista, label="Selecione personagem")
                    historico_estado = gr.State(json.dumps([]))

                    fala_usuario = gr.Textbox(label="Você diz:", placeholder="Olá, como você está?")
                    b_conversar = gr.Button("💬 Enviar", variant="primary")

                    out_conversar = gr.Audio(label="Resposta (áudio)", type="numpy", autoplay=True)
                    chat_display = gr.Textbox(label="Histórico da conversa", lines=12, interactive=False)

                    b_conversar.click(conversar_com_personagem,
                                     [pers_selecionado, fala_usuario, historico_estado],
                                     [out_conversar, historico_estado, chat_display])

        # ── Contador de Histórias ─────────────────────────────────────────
        with gr.Tab("📖 Contador de Histórias"):
            gr.Markdown(
                "Cole uma história com diálogos. A IA (Gemma) descobre **quem fala** e a "
                "**emoção** de cada frase, e dá uma voz distinta a cada personagem.\n"
                "O narrador usa a voz da aba Clone — analise uma voz antes de gerar."
            )
            txt_h = gr.Textbox(label="História", lines=12, value=EXEMPLO_HIST)
            with gr.Row():
                ritmo_h    = gr.Slider(0.70, 1.10, value=0.90, step=0.02,
                                       label="Ritmo da narração (← mais devagar · mais rápido →)")
                sussurro_h = gr.Checkbox(value=False, label="🤫 Modo sussurro (ASMR)")
            fundo_h = gr.Audio(label="🎵 Áudio de fundo (opcional — música/ambiente)",
                               type="filepath", sources=["upload"])
            with gr.Row():
                vol_fundo_h = gr.Slider(0.0, 0.40, value=0.03, step=0.01,
                                        label="Volume do fundo (0 = sem fundo)")
                cauda_h     = gr.Slider(0.0, 20.0, value=0.0, step=0.5,
                                        label="Cauda do fundo (segundos após a voz acabar)")
            b_h   = gr.Button("📖 Gerar história", variant="primary")
            out_h = gr.Audio(label="Resultado", type="numpy", autoplay=True)
            det_h = gr.Markdown()
            b_h.click(gerar_historia,
                      [estado, txt_h, ritmo_h, sussurro_h, fundo_h, vol_fundo_h, cauda_h],
                      [out_h, det_h])

        # ── Comédia (auditório / Ratinho) ─────────────────────────────────
        with gr.Tab("🎪 Comédia (auditório)"):
            gr.Markdown(
                "Programa de **auditório** (estilo Ratinho) com **sonoplastia**. A Gemma analisa o "
                "contexto e coloca efeitos nos momentos certos (rufar antes da revelação, "
                "risada/aplauso depois da piada...) + plateia de fundo.\n"
                "**Formato do roteiro:** linhas normais = o **apresentador** (usa a voz da aba "
                "Clone — analise antes). Para um **convidado**, comece a linha com o nome dele "
                "em maiúsculas e dois-pontos — ex.: `BIRUTA: Boa noite!` — que ele ganha uma voz "
                "própria e consistente. Use nomes de uma palavra.\n"
                "**Efeitos:** coloque os seus em `app/estudio/sonoplastia/` — nomes-chave: "
                "`aplauso`, `risada`, `rufar`, `buzina`, `trombone`, `apito`, `vinheta`, `grilo`, "
                "`plateia` (fundo). Usa só o que existir."
            )
            with gr.Row():
                txt_co    = gr.Textbox(label="Quadro / história", lines=12,
                                       value=EXEMPLO_COMEDIA, scale=4)
                with gr.Column(scale=1, min_width=160):
                    b_loucura = gr.Button("🤪 Hora da loucura!", variant="secondary", size="lg")
                    gr.Markdown("*A IA inventa um programa novo, do zero. Clique de novo para outro!*")
            b_loucura.click(hora_da_loucura, None, txt_co)
            with gr.Row():
                ritmo_co  = gr.Slider(0.70, 1.10, value=0.95, step=0.02, label="Ritmo")
                intens_co = gr.Slider(0.0, 2.0, value=1.0, step=0.1,
                                      label="Intensidade da sonoplastia (← menos · mais →)")
            with gr.Row():
                vol_sfx_co  = gr.Slider(0.0, 1.0, value=0.6, step=0.05, label="Volume dos efeitos")
                vol_plat_co = gr.Slider(0.0, 0.30, value=0.06, step=0.01,
                                        label="Volume da plateia (fundo · 0 = sem plateia)")
            with gr.Row():
                abertura_co     = gr.Audio(label="🎵 Música de abertura (opcional)",
                                           type="filepath", sources=["upload"])
                vol_abertura_co = gr.Slider(0.0, 1.0, value=0.85, step=0.05,
                                            label="Volume da abertura")
            b_co   = gr.Button("🎪 Gerar comédia", variant="primary")
            out_co = gr.Audio(label="Resultado", type="numpy", autoplay=True)
            det_co = gr.Markdown()
            b_co.click(gerar_comedia,
                       [estado, txt_co, ritmo_co, vol_sfx_co, vol_plat_co, intens_co,
                        abertura_co, vol_abertura_co],
                       [out_co, det_co])

        # ── Game Show Educativo (PDF) ──────────────────────────────────────
        with gr.Tab("🎓 Game Show Educativo (PDF)"):
            gr.Markdown(
                "Suba um **PDF** (material de estudo) e a **Pandora** cria um game show de **quiz "
                "educativo** sobre o assunto — ela ensina e faz perguntas, com convidados, plateia e "
                "sonoplastia. Feito para **aprendizado de crianças**.\n"
                "**Passo 1:** suba o PDF, ajuste a faixa etária e o nº de perguntas, e clique em "
                "*Ler PDF e criar roteiro*. **Passo 2:** revise/edite o roteiro e clique em *Gerar o "
                "game show*. (Analise a voz da Pandora na aba Clone antes.)"
            )
            with gr.Row():
                pdf_ed   = gr.File(label="📄 Material em PDF", file_types=[".pdf"], type="filepath")
                with gr.Column():
                    faixa_ed = gr.Textbox(label="Faixa etária / público",
                                          value="crianças de 7 a 10 anos")
                    nperg_ed = gr.Slider(3, 12, value=5, step=1, label="Nº de perguntas do quiz")
                    b_pdf    = gr.Button("📄 Ler PDF e criar roteiro", variant="secondary")
            status_ed = gr.Markdown()
            txt_ed = gr.Textbox(label="Roteiro do game show (gerado do PDF — pode editar)", lines=14)
            b_pdf.click(roteiro_do_pdf, [pdf_ed, faixa_ed, nperg_ed], [txt_ed, status_ed])
            with gr.Row():
                ritmo_ed  = gr.Slider(0.70, 1.10, value=0.95, step=0.02, label="Ritmo")
                intens_ed = gr.Slider(0.0, 2.0, value=1.0, step=0.1,
                                      label="Intensidade da sonoplastia")
            with gr.Row():
                vol_sfx_ed  = gr.Slider(0.0, 1.0, value=0.6, step=0.05, label="Volume dos efeitos")
                vol_plat_ed = gr.Slider(0.0, 0.30, value=0.06, step=0.01,
                                        label="Volume da plateia (fundo)")
            with gr.Row():
                abertura_ed     = gr.Audio(label="🎵 Música de abertura (opcional)",
                                           type="filepath", sources=["upload"])
                vol_abertura_ed = gr.Slider(0.0, 1.0, value=0.85, step=0.05,
                                            label="Volume da abertura")
            b_ed   = gr.Button("🎓 Gerar o game show", variant="primary")
            out_ed = gr.Audio(label="Resultado", type="numpy", autoplay=True)
            det_ed = gr.Markdown()
            b_ed.click(gerar_comedia,
                       [estado, txt_ed, ritmo_ed, vol_sfx_ed, vol_plat_ed, intens_ed,
                        abertura_ed, vol_abertura_ed],
                       [out_ed, det_ed])

    return demo

if __name__ == "__main__":
    demo = criar_interface()
    demo.launch(server_name="127.0.0.1", server_port=5007, inbrowser=True, show_error=True)
