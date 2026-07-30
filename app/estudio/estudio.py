# -*- coding: utf-8 -*-
"""Estúdio de Voz — OmniVoice local.
Roda:  .venv_omni/Scripts/python.exe app/estudio/estudio.py
Abre:  http://127.0.0.1:5006
"""
import os, sys, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Suprime WinError 10054 (browser fecha aba → asyncio lança ConnectionResetError cosmético)
if sys.platform == "win32":
    import asyncio.proactor_events as _pe
    _orig_ccl = _pe._ProactorBasePipeTransport._call_connection_lost
    def _safe_ccl(self, exc):
        try: _orig_ccl(self, exc)
        except ConnectionResetError: pass
    _pe._ProactorBasePipeTransport._call_connection_lost = _safe_ccl

import gradio as gr
import motor

PASTA = os.path.dirname(os.path.abspath(__file__))
VOZES = os.path.join(PASTA, "vozes")

IDIOMAS = ["pt", "en", "zh", "ja", "ko", "fr", "de", "es",
           "ru", "ar", "hi", "it", "nl", "tr", "pl"]

_VOZ_GENERO = {"feminino": "female",    "masculino": "male"}
_VOZ_IDADE  = {"criança": "child",      "jovem": "young adult",
               "adulto": "middle-aged", "idoso": "elderly"}
_VOZ_TOM    = {"grave": "low pitch",    "moderado": "moderate pitch", "agudo": "high pitch"}
_VOZ_ESTILO = {"normal": "",            "sussurro": "whisper",        "expressivo": "expressive"}

def listar_vozes():
    fs = [f for f in glob.glob(os.path.join(VOZES, "*.wav"))
          if not os.path.basename(f).startswith("_")]
    return sorted(os.path.basename(f) for f in fs)

def _prog(progress):
    return lambda f, d="": progress(min(max(f, 0), 1), desc=d)

# ── Tab Clone ─────────────────────────────────────────────────────────────────
def analisar(upload, escolhida, ref_text):
    cam = upload or (os.path.join(VOZES, escolhida) if escolhida else None)
    if not cam:
        return None, "⚠️ Suba uma voz ou escolha uma da lista."
    try:
        p = motor.perfil_voz(cam, ref_text=ref_text or None)
    except Exception as e:
        return None, f"❌ {e}"
    fonte = f"_{p['ref_text'][:80]}_" if p["ref_text"] else "sem transcrição"
    return p, (f"✅ Voz pronta! ({p['dur']}s) — "
               f"ritmo base {p['base_speed']:.2f} — referência: {fonte}")

def gerar_clone(perfil, texto, idioma, steps, guidance, velocidade, progress=gr.Progress()):
    if not perfil:
        raise gr.Error("Analise uma voz primeiro.")
    if not (texto or "").strip():
        raise gr.Error("Escreva um texto.")
    audio = motor.sintetizar_clone(
        perfil, texto, idioma,
        int(steps), float(guidance), float(velocidade),
        _prog(progress),
    )
    return (motor.SR, audio)

# ── Tab Design ────────────────────────────────────────────────────────────────
def gerar_design(genero, idade, tom, estilo, texto, idioma,
                 steps, guidance, velocidade, progress=gr.Progress()):
    if not (texto or "").strip():
        raise gr.Error("Escreva um texto.")
    partes = [_VOZ_GENERO.get(genero, ""), _VOZ_IDADE.get(idade, ""),
              _VOZ_TOM.get(tom, ""),        _VOZ_ESTILO.get(estilo, "")]
    instruct = ", ".join(p for p in partes if p)
    audio = motor.sintetizar_design(
        instruct or None, texto, idioma,
        int(steps), float(guidance), float(velocidade),
        _prog(progress),
    )
    return (motor.SR, audio)

# ── Tab Contador de Histórias ─────────────────────────────────────────────────
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

# ── Tab  ───────────────────────────────────
# Roteiro de programa: linhas SEM rótulo = a apresentadora PANDORA (voz da aba Clone);
# "NOME: fala" = convidado (voz própria e consistente). Nomes de uma palavra.
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

# ── Tab Game Show Educativo (PDF) ──────────────────────────────────────────────
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

# ── Interface ─────────────────────────────────────────────────────────────────
with gr.Blocks(title="Estúdio de Voz", theme=gr.themes.Soft(primary_hue="violet")) as demo:
    gr.Markdown("# 🎙️ Estúdio de Voz\n100% local · OmniVoice + Gemma")
    estado = gr.State(None)

    # ── 1. Clone de Voz ──────────────────────────────────────────────────────
    with gr.Tab("🎤 Clone de Voz"):
        gr.Markdown("**Passo 1** — escolha ou suba uma voz e clique *Analisar*.\n"
                    "**Passo 2** — escreva o texto e gere.")

        with gr.Row():
            up = gr.Audio(label="Subir voz de referência (≥ 3s)",
                          type="filepath", sources=["upload", "microphone"])
            with gr.Column():
                dd = gr.Dropdown(
                    listar_vozes(), label="...ou escolher voz salva",
                    value=("Pandora.wav" if "Pandora.wav" in listar_vozes() else None),
                )
                rt = gr.Textbox(
                    label="O que a pessoa diz no clipe (recomendado)",
                    info="Preencher melhora muito o clone. Vazio = usa só o áudio.",
                    lines=2,
                )
                b_an = gr.Button("🔎 Analisar voz", variant="primary")
        status_c = gr.Markdown()
        b_an.click(analisar, [up, dd, rt], [estado, status_c])

        txt_c = gr.Textbox(label="Texto", lines=8,
                           placeholder="Cole aqui o texto que a voz vai falar...")
        with gr.Row():
            lang_c  = gr.Dropdown(IDIOMAS, label="Idioma", value="pt")
            step_c  = gr.Slider(8, 64,  value=32,  step=1,    label="Inference steps")
            gs_c    = gr.Slider(0.0, 10.0, value=3.0, step=0.1, label="Guidance scale")
            vel_c   = gr.Slider(0.5, 2.0, value=1.0, step=0.05, label="Velocidade")
        b_c   = gr.Button("🎧 Gerar áudio", variant="primary")
        out_c = gr.Audio(label="Resultado", type="numpy", autoplay=True)
        b_c.click(gerar_clone, [estado, txt_c, lang_c, step_c, gs_c, vel_c], out_c)

    # ── 2. Design de Voz ─────────────────────────────────────────────────────
    with gr.Tab("🎨 Design de Voz"):
        gr.Markdown("Crie uma voz por características — **sem áudio de referência**.")
        with gr.Row():
            dv_gen = gr.Dropdown(list(_VOZ_GENERO), label="Gênero",  value="feminino")
            dv_id  = gr.Dropdown(list(_VOZ_IDADE),  label="Idade",   value="adulto")
            dv_tom = gr.Dropdown(list(_VOZ_TOM),    label="Tom",     value="moderado")
            dv_est = gr.Dropdown(list(_VOZ_ESTILO), label="Estilo",  value="normal")
        txt_d = gr.Textbox(label="Texto", lines=8,
                           placeholder="Escreva aqui o texto...")
        with gr.Row():
            lang_d = gr.Dropdown(IDIOMAS, label="Idioma", value="pt")
            step_d = gr.Slider(8, 64,  value=32,  step=1,    label="Inference steps")
            gs_d   = gr.Slider(0.0, 10.0, value=3.0, step=0.1, label="Guidance scale")
            vel_d  = gr.Slider(0.5, 2.0, value=1.0, step=0.05, label="Velocidade")
        b_d   = gr.Button("🎤 Gerar com voz projetada", variant="primary")
        out_d = gr.Audio(label="Resultado", type="numpy", autoplay=True)
        b_d.click(gerar_design,
                  [dv_gen, dv_id, dv_tom, dv_est, txt_d, lang_d, step_d, gs_d, vel_d],
                  out_d)

    # ── 3. Contador de Histórias ──────────────────────────────────────────────
    with gr.Tab("📖 Contador de Histórias"):
        gr.Markdown(
            "Cole uma história com diálogos. A IA (Gemma) descobre **quem fala** e a "
            "**emoção** de cada frase, e dá uma voz distinta a cada personagem.\n"
            "O narrador usa a voz da aba Clone — analise uma voz antes de gerar."
        )
        txt_h = gr.Textbox(label="História", lines=12, value=EXEMPLO_HIST)
        with gr.Row():
            ritmo_h = gr.Slider(0.70, 1.10, value=0.90, step=0.02,
                                label="Ritmo da narração (← mais devagar · mais rápido →)")
            sussurro_h = gr.Checkbox(value=False, label="🤫 Modo sussurro (ASMR)")
        fundo_h = gr.Audio(label="🎵 Áudio de fundo (opcional — música/ambiente)",
                           type="filepath", sources=["upload"])
        with gr.Row():
            vol_fundo_h = gr.Slider(0.0, 0.40, value=0.03, step=0.01,
                                    label="Volume do fundo (0 = sem fundo)")
            cauda_h = gr.Slider(0.0, 20.0, value=0.0, step=0.5,
                                label="Cauda do fundo (segundos após a voz acabar)")
        b_h   = gr.Button("📖 Gerar história", variant="primary")
        out_h = gr.Audio(label="Resultado", type="numpy", autoplay=True)
        det_h = gr.Markdown()
        b_h.click(gerar_historia,
                  [estado, txt_h, ritmo_h, sussurro_h, fundo_h, vol_fundo_h, cauda_h],
                  [out_h, det_h])

    # ── 4. Comédia (auditório / Ratinho) ──────────────────────────────────────
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
            txt_co = gr.Textbox(label="Quadro / história", lines=12,
                                value=EXEMPLO_COMEDIA, scale=4)
            with gr.Column(scale=1, min_width=160):
                b_loucura = gr.Button("🤪 Hora da loucura!", variant="secondary", size="lg")
                gr.Markdown("*A IA inventa um programa novo, do zero. Clique de novo "
                            "para outro!*")
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
            abertura_co = gr.Audio(label="🎵 Música de abertura (opcional)",
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

    # ── 5. Game Show Educativo (PDF) ──────────────────────────────────────────
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
            abertura_ed = gr.Audio(label="🎵 Música de abertura (opcional)",
                                   type="filepath", sources=["upload"])
            vol_abertura_ed = gr.Slider(0.0, 1.0, value=0.85, step=0.05, label="Volume da abertura")
        b_ed   = gr.Button("🎓 Gerar o game show", variant="primary")
        out_ed = gr.Audio(label="Resultado", type="numpy", autoplay=True)
        det_ed = gr.Markdown()
        b_ed.click(gerar_comedia,
                   [estado, txt_ed, ritmo_ed, vol_sfx_ed, vol_plat_ed, intens_ed,
                    abertura_ed, vol_abertura_ed],
                   [out_ed, det_ed])

if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=5006, inbrowser=True, show_error=True,share=True)
