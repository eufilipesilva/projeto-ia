# -*- coding: utf-8 -*-
"""
Estúdio de Voz — FastAPI backend.
Roda: python app/estudio/estudio_web.py
Abre: http://127.0.0.1:5008
"""
import os, sys, io, re, uuid, json, threading, time, glob, shutil, tempfile, queue
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import soundfile as sf
from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

import motor_v2 as motor
import canto_musica
import canto_lote

PASTA      = os.path.dirname(os.path.abspath(__file__))
VOZES_DIR  = os.path.join(PASTA, "vozes")
STATIC_DIR = os.path.join(PASTA, "static")
TMP_DIR    = os.path.join(PASTA, "saidas", "tmp_web")
LOTE_DIR   = os.path.join(PASTA, "saidas", "canto_lote")  # resultados finais do modo lote
PERS_DIR   = os.path.join(PASTA, "personagens")           # fichas do Personagem Infinito
os.makedirs(TMP_DIR, exist_ok=True)
os.makedirs(LOTE_DIR, exist_ok=True)
os.makedirs(PERS_DIR, exist_ok=True)

app = FastAPI(title="Estúdio de Voz")

# ── Estado em memória ────────────────────────────────────────────────────────
_sessions: dict = {}   # session_id → perfil dict
_tasks:    dict = {}   # task_id → {status, progress, desc, audio_path, text, error}
_historicos: dict = {} # session_id → list de trocas do personagem

# ── Helpers ──────────────────────────────────────────────────────────────────

def _save_audio(audio: np.ndarray, sr: int) -> str:
    path = os.path.join(TMP_DIR, f"{uuid.uuid4().hex}.wav")
    sf.write(path, audio, sr)
    return path

def _perfil_de_voz(nome: str):
    """Constrói um perfil de clone a partir de um nome de voz salva em vozes/.
    Retorna None se o nome for vazio ou o arquivo não existir."""
    if not nome:
        return None
    cam = os.path.join(VOZES_DIR, nome)
    return motor.perfil_voz(cam) if os.path.exists(cam) else None

def _avaliar_meditacao(y: np.ndarray, sr: int, duracao_pedida_min: int) -> str:
    """Mede silêncio, pitch, monotonia, brilho e nível de uma meditação gerada
    e retorna um relatório de qualidade com notas e metas. Mono, antes do resample."""
    import librosa
    dur = len(y) / sr
    # Silêncio: tudo que não é fala detectada
    intervals = librosa.effects.split(y, top_db=35, frame_length=2048, hop_length=512)
    fala = sum((e - s) for s, e in intervals) / sr if len(intervals) else 0.0
    sil_pct = max(0.0, (1 - fala / dur) * 100) if dur > 0 else 0.0
    # Pitch só nas partes faladas
    voiced = np.concatenate([y[s:e] for s, e in intervals]) if len(intervals) else y
    if len(voiced) > sr * 0.5:
        f0 = librosa.yin(voiced, fmin=80, fmax=300, sr=sr)
        vv = f0[(f0 > 85) & (f0 < 280)]
    else:
        vv = np.array([])
    pitch_med = float(np.median(vv)) if len(vv) else 0.0
    pitch_cv = float(np.std(vv) / np.mean(vv) * 100) if len(vv) else 0.0
    centroid = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))
    rms = float(np.sqrt(np.mean(y ** 2)))

    def faixa(v, lo, hi, margem):
        if lo <= v <= hi:
            return 10.0
        d = (lo - v) if v < lo else (v - hi)
        return max(0.0, 10.0 - (d / margem) * 5.0)

    s_sil   = faixa(sil_pct, 60, 68, 8)
    s_pitch = faixa(pitch_med, 165, 190, 15) if pitch_med else 5.0
    alvo_dur = duracao_pedida_min * 60 * 0.7
    s_dur   = 10.0 if dur >= alvo_dur else max(3.0, 10 * dur / alvo_dur)
    s_cv    = 10.0 if pitch_cv < 25 else max(3.0, 10 - (pitch_cv - 25) / 3)
    s_clar  = faixa(centroid, 1000, 1800, 600)
    nota = (s_sil * 3 + s_pitch * 2 + s_dur * 2 + s_cv * 2 + s_clar * 1) / 10

    def mk(s):
        return "✓" if s >= 8 else ("⚠" if s >= 5 else "✗")

    return "\n".join([
        f"{mk(s_dur)} Duração: {dur/60:.1f} min",
        f"{mk(s_sil)} Silêncio: {sil_pct:.0f}% (meta 60-68%)",
        f"{mk(s_pitch)} Pitch: {pitch_med:.0f} Hz (alvo 165-190)",
        f"{mk(s_cv)} Monotonia (variação de pitch): {pitch_cv:.0f}% (alvo <25%)",
        f"{mk(s_clar)} Brilho/centroide: {centroid:.0f} Hz (alvo 1000-1800)",
        f"• Nível RMS: {rms:.3f}",
        f"NOTA ESTIMADA: {nota:.1f}/10",
    ])

def _parse_bool(val: str) -> bool:
    return str(val).lower() in ("1", "true", "yes")

def _audio_response(path: str):
    return FileResponse(path, media_type="audio/wav",
                        headers={"Cache-Control": "no-cache"})

def _prog_fn(task_id: str):
    def _p(f, desc=""):
        if task_id in _tasks:
            _tasks[task_id]["progress"] = round(float(f) * 100)
            _tasks[task_id]["desc"] = desc
    return _p

# ── Fila de inferência: UMA thread worker persistente ─────────────────────────
# O modelo (OmniVoice) é pesado e carregado via CUDA. Criar uma thread NOVA por
# tarefa (como antes) faz o contexto CUDA migrar de thread a cada geração, o que
# é instável no Windows/torch e pode causar segfault no carregamento do modelo —
# matando o servidor inteiro silenciosamente. Uma única thread persistente mantém
# o contexto CUDA estável pela vida toda do processo e serializa o uso da GPU
# (necessário numa GPU de 6GB de qualquer forma).
_task_queue: "queue.Queue" = queue.Queue()

def _executar_tarefa(task_id, fn, args):
    result = fn(*args, _prog_fn(task_id))
    # result de LOTE: {"batch": [{"nome":.., "saida":path|None, "ok":bool, "erro":..}, ...]}
    if isinstance(result, dict) and "batch" in result:
        _tasks[task_id]["batch"] = result["batch"]
        _tasks[task_id]["status"] = "done"
        _tasks[task_id]["progress"] = 100
        return
    # result pode ser (SR, array) ou ((SR, array), text)
    if isinstance(result, tuple) and len(result) == 2:
        first, second = result
        if isinstance(first, tuple):
            (sr, audio), _text = first, second
            _tasks[task_id]["audio_path"] = _save_audio(audio, sr)
            _tasks[task_id]["text"] = str(second)
        elif isinstance(first, int):
            sr, audio = first, second
            _tasks[task_id]["audio_path"] = _save_audio(audio, sr)
        else:
            _tasks[task_id]["text"] = str(result)
    else:
        _tasks[task_id]["text"] = str(result)
    _tasks[task_id]["status"] = "done"
    _tasks[task_id]["progress"] = 100

def _worker_loop():
    while True:
        task_id, fn, args = _task_queue.get()
        try:
            _executar_tarefa(task_id, fn, args)
        except Exception as e:
            _tasks[task_id]["status"] = "error"
            _tasks[task_id]["error"] = str(e)
        finally:
            _task_queue.task_done()

_worker_thread = threading.Thread(target=_worker_loop, daemon=True, name="model-worker")
_worker_thread.start()

# Higiene de tasks/disco: sem isso, _tasks cresce pra sempre e cada task deixa
# um wav órfão na tmp_web (_save_audio) — foi assim que a pasta chegou a 2 GB.
_MAX_TASKS_GUARDADAS = 30

def _podar_tasks():
    """Mantém só as últimas N tasks finalizadas; apaga do disco os áudios das
    descartadas. Dicts preservam ordem de inserção → as mais velhas saem antes."""
    if len(_tasks) <= _MAX_TASKS_GUARDADAS:
        return
    finalizadas = [k for k, t in _tasks.items() if t["status"] in ("done", "error")]
    excesso = len(_tasks) - _MAX_TASKS_GUARDADAS
    for k in finalizadas[:excesso]:
        t = _tasks.pop(k)
        try:
            if t.get("audio_path") and os.path.exists(t["audio_path"]):
                os.remove(t["audio_path"])
        except OSError:
            pass

def _varrer_tmp_antigos(horas=24):
    """Apaga da tmp_web arquivos/subpastas com mais de N horas (uploads e
    resultados de sessões passadas). Roda no startup; o critério de idade
    garante que nada em uso na sessão atual é tocado."""
    limite = time.time() - horas * 3600
    for f in glob.glob(os.path.join(TMP_DIR, "*")):
        try:
            if os.path.getmtime(f) < limite:
                shutil.rmtree(f, ignore_errors=True) if os.path.isdir(f) else os.remove(f)
        except OSError:
            pass

_varrer_tmp_antigos()

def _run_task(task_id: str, fn, *args):
    """Enfileira a tarefa para a thread worker única (contexto CUDA estável)."""
    _podar_tasks()
    _tasks[task_id] = {"status": "running", "progress": 0, "desc": "Na fila...",
                       "audio_path": None, "text": None, "error": None, "batch": None}
    _task_queue.put((task_id, fn, args))
    return task_id

def _new_task():
    tid = uuid.uuid4().hex
    return tid

async def _salvar_upload(up, suffix):
    """Salva um UploadFile num temporário do TMP_DIR e retorna o caminho, ou
    None se não veio arquivo. Centraliza o padrão que se repetia em 9 rotas."""
    if not (up and up.filename):
        return None
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=TMP_DIR)
    tmp.write(await up.read())
    tmp.close()
    return tmp.name

# ── Rotas utilitárias ─────────────────────────────────────────────────────────

@app.get("/api/status")
def status():
    import urllib.request, json as _json
    resultado = {"omnivoice": "ok" if motor._OMNI is not None else "não carregado", "gemma": "?"}
    try:
        req = urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3)
        resultado["gemma"] = "ollama ok"
    except Exception as e:
        resultado["gemma"] = f"ollama erro: {e}"
    return resultado

_vozes_cache: "list | None" = None
_vozes_cache_mtime: float = -1.0

@app.get("/api/vozes")
def listar_vozes():
    """Lista as vozes salvas. O cache invalida sozinho pelo mtime da pasta —
    salvar/apagar um wav em vozes/ atualiza a lista sem reiniciar o servidor."""
    global _vozes_cache, _vozes_cache_mtime
    try:
        mtime = os.path.getmtime(VOZES_DIR)
    except OSError:
        mtime = 0.0
    if _vozes_cache is None or mtime != _vozes_cache_mtime:
        fs = [f for f in glob.glob(os.path.join(VOZES_DIR, "*.wav"))
              if not os.path.basename(f).startswith("_")]
        _vozes_cache = sorted(os.path.basename(f) for f in fs)
        _vozes_cache_mtime = mtime
    return {"vozes": _vozes_cache}

@app.get("/api/vozes/preview/{nome}")
def preview_voz(nome: str):
    cam = os.path.join(VOZES_DIR, nome)
    if not os.path.exists(cam):
        raise HTTPException(404, "Voz não encontrada.")
    return _audio_response(cam)

@app.get("/api/task/{task_id}")
def task_status(task_id: str):
    if task_id not in _tasks:
        raise HTTPException(404, "Task não encontrada")
    t = _tasks[task_id]
    batch = t.get("batch")
    # Só expõe o essencial de cada faixa do lote (nome, se deu certo, erro),
    # com o índice pra o front buscar o áudio em /api/task/{id}/audio_lote/{i}.
    batch_pub = None
    if batch is not None:
        batch_pub = [{"indice": i, "nome": os.path.basename(b["musica"]),
                      "ok": b["ok"], "erro": b.get("erro")}
                     for i, b in enumerate(batch)]
    return {
        "status":    t["status"],
        "progress":  t["progress"],
        "desc":      t["desc"],
        "has_audio": t["audio_path"] is not None,
        "text":      t["text"],
        "error":     t["error"],
        "batch":     batch_pub,
    }

@app.get("/api/task/{task_id}/audio")
def task_audio(task_id: str):
    if task_id not in _tasks:
        raise HTTPException(404, "Task não encontrada")
    path = _tasks[task_id].get("audio_path")
    if not path or not os.path.exists(path):
        raise HTTPException(404, "Áudio ainda não disponível")
    return _audio_response(path)

@app.get("/api/task/{task_id}/audio_lote/{indice}")
def task_audio_lote(task_id: str, indice: int):
    """Serve o áudio da i-ésima faixa de uma tarefa de lote."""
    if task_id not in _tasks:
        raise HTTPException(404, "Task não encontrada")
    batch = _tasks[task_id].get("batch")
    if not batch or indice < 0 or indice >= len(batch):
        raise HTTPException(404, "Faixa não encontrada")
    path = batch[indice].get("saida")
    if not path or not os.path.exists(path):
        raise HTTPException(404, "Áudio desta faixa não disponível")
    return _audio_response(path)

# ── Clone de Voz ──────────────────────────────────────────────────────────────

@app.post("/api/voice/analyze")
async def analisar_voz(
    upload: UploadFile = File(None),
    escolhida: str = Form(""),
    ref_text: str = Form(""),
    corte_inicio: float = Form(0.0),
    corte_fim: float = Form(0.0),
):
    cam = await _salvar_upload(upload, ".wav")
    if not cam:
        if escolhida:
            cam = os.path.join(VOZES_DIR, escolhida)
        else:
            raise HTTPException(400, "Suba uma voz ou escolha uma da lista.")

    # Corte opcional do clipe (igual o trim do Gradio) — recorta antes de
    # construir o perfil, pra usar só o trecho selecionado no clone.
    if corte_fim > corte_inicio >= 0:
        try:
            y, sr = sf.read(cam)
        except Exception:
            # upload pode ser mp3/ogg com sufixo .wav — o librosa lê qualquer um
            import librosa as _lr
            y, sr = _lr.load(cam, sr=None, mono=True)
        ini = max(0, int(corte_inicio * sr))
        fim = min(len(y), int(corte_fim * sr)) if corte_fim > 0 else len(y)
        if fim > ini:
            cortado = tempfile.NamedTemporaryFile(delete=False, suffix=".wav", dir=TMP_DIR)
            sf.write(cortado.name, y[ini:fim], sr)
            cortado.close()
            cam = cortado.name

    try:
        perfil = motor.perfil_voz(cam, ref_text=ref_text or None)
    except Exception as e:
        raise HTTPException(500, str(e))
    sid = uuid.uuid4().hex
    _sessions[sid] = perfil
    fonte = f"_{perfil['ref_text'][:80]}_" if perfil["ref_text"] else "sem transcrição"
    return {"session_id": sid,
            "msg": f"✅ Voz pronta! ({perfil['dur']}s) — ritmo {perfil['base_speed']:.2f} — {fonte}"}

@app.post("/api/voice/clone")
async def gerar_clone(
    session_id: str = Form(...),
    texto: str = Form(...),
    idioma: str = Form("pt"),
    steps: int = Form(32),
    guidance: float = Form(3.0),
    velocidade: float = Form(1.0),
):
    perfil = _sessions.get(session_id)
    if not perfil:
        raise HTTPException(400, "Sessão inválida. Analise uma voz primeiro.")
    tid = _new_task()
    _run_task(tid, lambda *a: (motor.SR, motor.sintetizar_clone(
        perfil, texto, idioma, steps, guidance, velocidade, a[-1])))
    return {"task_id": tid}

# ── Cantar Música (Demucs + seed-vc) ─────────────────────────────────────────

async def _resolver_voz_ref(voz: str, voz_upload: "UploadFile | None",
                            corte_inicio: float = 0.0, corte_fim: float = 0.0):
    """Resolve a voz de referência da conversão: usa o TRECHO enviado por
    upload se veio um (o seed-vc é zero-shot, clona qualquer voz na hora),
    senão a voz salva escolhida. Se vier um corte (fim > início), recorta o
    upload pra usar só o trecho selecionado. Retorna (caminho, eh_temporario)
    — o chamador apaga o arquivo se for temporário, depois de usar."""
    if voz_upload is not None and voz_upload.filename:
        ext = os.path.splitext(voz_upload.filename)[1] or ".wav"
        caminho = await _salvar_upload(voz_upload, ext)
        if corte_fim and float(corte_fim) > float(corte_inicio):
            try:
                import librosa
                y, srr = librosa.load(caminho, sr=None, mono=True,
                                      offset=float(corte_inicio),
                                      duration=float(corte_fim) - float(corte_inicio))
                sf.write(caminho, y, srr)
            except Exception:
                pass  # se o corte falhar, usa o trecho inteiro
        return caminho, True
    if voz:
        p = os.path.join(VOZES_DIR, voz)
        if os.path.exists(p):
            return p, False
    raise HTTPException(400, "Escolha uma voz salva ou suba um trecho de voz de referência.")

@app.post("/api/sing")
async def gerar_canto(
    musica: UploadFile = File(...),
    voz: str = Form(""),
    voz_upload: UploadFile = File(None),
    corte_voz_inicio: float = Form(0.0),
    corte_voz_fim: float = Form(0.0),
    diffusion_steps: int = Form(50),
    vol_instrumental: float = Form(0.6),
    inference_cfg_rate: float = Form(0.7),
    auto_f0_adjust: str = Form("false"),
    ajuste_fino_pitch: int = Form(0),
):
    voz_path, voz_tmp = await _resolver_voz_ref(voz, voz_upload, corte_voz_inicio, corte_voz_fim)
    if not musica.filename:
        raise HTTPException(400, "Suba um arquivo de música.")

    mus_path = await _salvar_upload(musica, os.path.splitext(musica.filename)[1] or ".mp3")

    tid = _new_task()
    def _fn(progresso):
        try:
            sr, audio = canto_musica.gerar_canto(
                mus_path, voz_path, diffusion_steps, vol_instrumental,
                inference_cfg_rate, _parse_bool(auto_f0_adjust), "auto", ajuste_fino_pitch, progresso)
            return (sr, audio)
        finally:
            canto_musica._limpar(mus_path)          # upload da música (10-30 MB)
            if voz_tmp:
                canto_musica._limpar(voz_path)
    _run_task(tid, lambda *a: _fn(a[-1]))
    return {"task_id": tid}

@app.post("/api/sing_batch")
async def gerar_canto_lote(
    musicas: list[UploadFile] = File(...),
    voz: str = Form(""),
    voz_upload: UploadFile = File(None),
    corte_voz_inicio: float = Form(0.0),
    corte_voz_fim: float = Form(0.0),
    diffusion_steps: int = Form(50),
    vol_instrumental: float = Form(0.6),
    inference_cfg_rate: float = Form(0.7),
    auto_f0_adjust: str = Form("false"),
    ajuste_fino_pitch: int = Form(0),
):
    """Modo lote: várias músicas de uma vez. O seed-vc carrega os modelos uma
    única vez pro lote inteiro (economiza ~60s por música extra)."""
    voz_path, voz_tmp = await _resolver_voz_ref(voz, voz_upload, corte_voz_inicio, corte_voz_fim)
    if not musicas:
        raise HTTPException(400, "Suba pelo menos uma música.")

    # Cada música vai numa subpasta única do TMP_DIR preservando o NOME
    # ORIGINAL — o resultado final herda esse nome (limpo, sem uuid), e a
    # subpasta evita colisão se dois arquivos tiverem o mesmo nome.
    caminhos, subpastas = [], []
    for m in musicas:
        if not m.filename:
            continue
        sub = os.path.join(TMP_DIR, "lote_" + uuid.uuid4().hex[:8])
        os.makedirs(sub, exist_ok=True)
        destino = os.path.join(sub, os.path.basename(m.filename))
        with open(destino, "wb") as f:
            f.write(await m.read())
        caminhos.append(destino)
        subpastas.append(sub)

    if not caminhos:
        raise HTTPException(400, "Nenhum arquivo de música válido.")

    tid = _new_task()
    def _fn(progresso):
        try:
            resultados = canto_lote.gerar_canto_lote(
                caminhos, voz_path, LOTE_DIR, diffusion_steps, vol_instrumental,
                inference_cfg_rate, _parse_bool(auto_f0_adjust), "auto", ajuste_fino_pitch, progresso)
            return {"batch": resultados}
        finally:
            for sub in subpastas:
                shutil.rmtree(sub, ignore_errors=True)
            if voz_tmp:
                canto_musica._limpar(voz_path)
    _run_task(tid, lambda *a: _fn(a[-1]))
    return {"task_id": tid}

@app.post("/api/voice/design")
async def gerar_design(
    desc_voz: str = Form(...),
    texto: str = Form(...),
    idioma: str = Form("pt"),
    steps: int = Form(32),
    guidance: float = Form(3.0),
    velocidade: float = Form(1.0),
):
    tid = _new_task()
    def _fn(progresso):
        instruct, msg = motor.interpretar_descricao_voz(desc_voz, progresso)
        if not instruct:
            raise Exception(msg)
        audio = motor.sintetizar_design(instruct, texto, idioma, steps, guidance, velocidade, progresso)
        return (motor.SR, audio), msg
    _run_task(tid, lambda *a: _fn(a[-1]))
    return {"task_id": tid}

# ── Contador de Histórias ─────────────────────────────────────────────────────

@app.post("/api/story")
async def gerar_historia(
    session_id: str = Form(...),
    texto: str = Form(...),
    ritmo: float = Form(0.90),
    sussurro: str = Form("false"),
    fundo: UploadFile = File(None),
    vol_fundo: float = Form(0.03),
    cauda_fundo: float = Form(0.0),
    personagens_vozes: str = Form(""),   # JSON {"NomePersonagem": "Voz.wav", ...}
):
    perfil = _sessions.get(session_id)
    if not perfil:
        raise HTTPException(400, "Sessão inválida.")
    fundo_path = await _salvar_upload(fundo, ".wav")
    try:
        mapa_nomes = json.loads(personagens_vozes) if personagens_vozes.strip() else {}
    except Exception:
        mapa_nomes = {}
    tid = _new_task()
    def _fn(progresso):
        # resolve os perfis DENTRO da worker (perfil_voz pode transcrever = lento)
        vmap = {}
        for nome, voz in mapa_nomes.items():
            if str(nome).strip() and str(voz).strip():
                p = _perfil_de_voz(str(voz))
                if p:
                    vmap[str(nome).strip()] = p
        audio, roteiro = motor.sintetizar_historia(
            perfil, texto, ritmo, _parse_bool(sussurro), fundo_path, vol_fundo,
            cauda_fundo, progresso, vozes_map=vmap or None)
        tabela = "\n".join(f"**{q}** (*{e}*): {f}" for q, e, f in roteiro)
        return (motor.SR, audio), tabela
    _run_task(tid, lambda *a: _fn(a[-1]))
    return {"task_id": tid}

# ── Comédia ───────────────────────────────────────────────────────────────────

@app.post("/api/comedy")
async def gerar_comedia(
    session_id: str = Form(...),
    texto: str = Form(...),
    ritmo: float = Form(0.95),
    vol_sfx: float = Form(0.6),
    vol_plateia: float = Form(0.06),
    intensidade: float = Form(1.0),
    abertura: UploadFile = File(None),
    vol_abertura: float = Form(0.85),
):
    perfil = _sessions.get(session_id)
    if not perfil:
        raise HTTPException(400, "Sessão inválida.")
    ab_path = await _salvar_upload(abertura, ".wav")
    tid = _new_task()
    def _fn(progresso):
        audio, roteiro = motor.sintetizar_comedia(
            perfil, texto, ritmo, vol_sfx, vol_plateia, intensidade, ab_path, vol_abertura, progresso)
        tabela = "\n".join(
            f"**{q}** (*{e}*){(' 🔊 ' + s) if s and s != 'nenhum' else ''}: {f}"
            for q, e, f, s in roteiro)
        return (motor.SR, audio), tabela
    _run_task(tid, lambda *a: _fn(a[-1]))
    return {"task_id": tid}

@app.post("/api/comedy/random")
def roteiro_aleatorio():
    try:
        roteiro = motor.gerar_roteiro_comedia()
        return {"roteiro": roteiro}
    except Exception as e:
        raise HTTPException(500, str(e))

# ── Game Show Educativo ───────────────────────────────────────────────────────

# Game Show 2.0: passo 1 agora é TASK (retorna task_id) porque a leitura
# COMPLETA de um PDF grande é map-reduce na Gemma (minutos) — o front acompanha
# pelo progresso e pega o roteiro em `text` quando termina.
@app.post("/api/gameshow/pdf")
async def ler_pdf(
    pdf: UploadFile = File(...),
    faixa: str = Form("crianças de 7 a 10 anos"),
    n_perg: int = Form(5),
    nome1: str = Form("MAX"),
    nome2: str = Form("LILI"),
):
    pdf_path = await _salvar_upload(pdf, ".pdf")
    if not pdf_path:
        raise HTTPException(400, "Suba um arquivo PDF.")
    tid = _new_task()
    def _fn(progresso):
        try:
            progresso(0.02, "Extraindo o texto do PDF...")
            texto, n_pag = motor.ler_pdf_completo(pdf_path)
            if not texto.strip():
                raise RuntimeError("PDF sem texto (pode ser escaneado/imagem).")
            # material inteiro: destila em fatos se for maior que 1 bloco
            fatos = motor.destilar_conteudo(texto, progresso)
            roteiro = motor.gerar_gameshow_duelo(
                fatos, faixa.strip(), n_perg, nome1, nome2, progresso=progresso)
            if not roteiro.strip():
                raise RuntimeError("A Gemma não gerou o roteiro do duelo.")
            return f"[{n_pag} páginas lidas por inteiro]\n{roteiro}"
        finally:
            canto_musica._limpar(pdf_path)
    _run_task(tid, lambda *a: _fn(a[-1]))
    return {"task_id": tid}

@app.post("/api/gameshow")
async def gerar_gameshow(
    session_id: str = Form(...),
    texto: str = Form(...),
    ritmo: float = Form(0.95),
    vol_sfx: float = Form(0.6),
    vol_plateia: float = Form(0.06),
    intensidade: float = Form(1.0),
    abertura: UploadFile = File(None),
    vol_abertura: float = Form(0.85),
    nome1: str = Form(""),
    voz1: str = Form(""),
    nome2: str = Form(""),
    voz2: str = Form(""),
):
    """Sintetiza o duelo: Pandora (voz da sessão) apresenta; cada competidor
    fala com a voz SALVA escolhida (vozes_map). Sem voz escolhida, cai na
    PALETA (variações da voz base), como antes."""
    perfil = _sessions.get(session_id)
    if not perfil:
        raise HTTPException(400, "Sessão inválida.")
    ab_path = await _salvar_upload(abertura, ".wav")
    # remove o cabeçalho informativo do passo 1, se veio junto no textarea
    texto = re.sub(r"^\[\d+ páginas[^\]]*\]\n?", "", texto.strip())
    tid = _new_task()
    def _fn(progresso):
        vmap = {}
        for nome, voz in ((nome1, voz1), (nome2, voz2)):
            if nome.strip() and voz.strip():
                p = _perfil_de_voz(voz)
                if p:
                    vmap[nome.strip()] = p
        audio, roteiro = motor.sintetizar_comedia(
            perfil, texto, ritmo, vol_sfx, vol_plateia, intensidade,
            ab_path, vol_abertura, progresso, vozes_map=vmap or None)
        tabela = "\n".join(
            f"**{q}** (*{e}*){(' 🔊 ' + s) if s and s != 'nenhum' else ''}: {f}"
            for q, e, f, s in roteiro)
        return (motor.SR, audio), tabela
    _run_task(tid, lambda *a: _fn(a[-1]))
    return {"task_id": tid}

# ── Trailer ───────────────────────────────────────────────────────────────────

@app.post("/api/trailer")
async def gerar_trailer(
    genero: str = Form("Ficção Científica"),
    logline: str = Form(...),
    voz: str = Form(""),
    musica: UploadFile = File(None),
    vol_musica: float = Form(0.4),
):
    mus_path = await _salvar_upload(musica, ".wav")
    perfil = _perfil_de_voz(voz)
    tid = _new_task()
    def _fn(progresso):
        roteiro = motor.gerar_roteiro_trailer(genero, logline, progresso=progresso)
        if not roteiro.strip():
            raise Exception("Não foi possível gerar o roteiro.")
        if perfil:
            audio = motor.sintetizar_clone(perfil, roteiro, "pt", 32, 3.0, 1.0, progresso)
        else:
            audio = motor.sintetizar_design(
                "male, middle-aged, low pitch", roteiro, "pt", 32, 3.0, 1.0, progresso)
        if mus_path:
            fundo = motor._carregar_fundo(mus_path, vol_musica)
            if fundo is not None:
                audio = motor._misturar_fundo(audio, fundo, 2.0)
        return (motor.SR, audio), roteiro
    _run_task(tid, lambda *a: _fn(a[-1]))
    return {"task_id": tid}

# ── Meditação ─────────────────────────────────────────────────────────────────

@app.post("/api/meditation")
async def gerar_meditacao(
    session_id: str = Form(...),
    tema: str = Form("Floresta"),
    duracao: int = Form(10),
    vol_voz: float = Form(0.85),
    vel_voz: float = Form(0.62),
    voz: str = Form(""),
    asmr: str = Form("false"),
    asmr_idioma: str = Form("en"),
    fundo: UploadFile = File(None),
    vol_fundo: float = Form(0.08),
):
    asmr_on = _parse_bool(asmr)
    asmr_en = asmr_on and asmr_idioma.lower().startswith("en")
    # Voz do ASMR: EN → Nicole nativa (inglês); PT → mix3 (blend, pt). Senão galeria/sessão
    if asmr_on:
        perfil = _perfil_de_voz("_asmr_nicole_en.wav" if asmr_en else "_asmr_mix3_pt.wav")
    else:
        perfil = _perfil_de_voz(voz) or _sessions.get(session_id)
    if not perfil:
        raise HTTPException(400, "Analise uma voz ou escolha uma da galeria.")
    fundo_path = await _salvar_upload(fundo, ".wav")
    tid = _new_task()
    def _fn(progresso):
        idioma = "en" if asmr_en else "pt"
        script, _ = motor.gerar_meditacao(tema, duracao_min=duracao, intensidade_sussurro=0, idioma=idioma, progresso=progresso)
        if not script or not script.strip():
            raise RuntimeError("A Gemma não gerou o script de meditação. Verifique se o Ollama está rodando.")

        print(f"[meditação] Script bruto ({len(script)} chars):\n{script[:800]}\n---", flush=True)

        # Divide script em blocos de fala e suas pausas posteriores
        # Parser: divide por marcadores [pausa Xs]; cada linha de texto sem marcador vira uma frase
        tokens = re.split(r'(\[pausa \d+s\])', script)
        segmentos_fala = []
        segmentos_pausa = []
        texto_acumulado = ""
        pausa_acumulada = 0.0

        for tok in tokens:
            m_p = re.match(r'\[pausa (\d+)s\]', tok.strip())
            if m_p:
                pausa_acumulada = max(pausa_acumulada, float(m_p.group(1)))
            else:
                # Processa linha a linha para capturar pausas implícitas por linha vazia
                for linha in tok.splitlines():
                    linha = linha.strip()
                    if not linha:
                        if texto_acumulado:
                            pausa_acumulada = max(pausa_acumulada, 2.0)
                        continue
                    texto_acumulado = (texto_acumulado + " " + linha).strip()
                    if pausa_acumulada > 0:
                        segmentos_fala.append(texto_acumulado)
                        segmentos_pausa.append(pausa_acumulada)
                        texto_acumulado = ""
                        pausa_acumulada = 0.0

        if texto_acumulado.strip():
            segmentos_fala.append(texto_acumulado.strip())
            segmentos_pausa.append(0.0)

        # Fallback: se a Gemma ignorou os marcadores, divide por frases curtas
        if len(segmentos_fala) <= 2:
            print("[meditação] Poucos segmentos — ativando fallback por frases.", flush=True)
            frases_all = re.split(r'(?<=[.!?…])\s+', script.replace('\n', ' '))
            frases_all = [f.strip() for f in frases_all if len(f.strip()) > 8]
            segmentos_fala = []
            segmentos_pausa = []
            n = len(frases_all)
            for i, frase in enumerate(frases_all):
                segmentos_fala.append(frase)
                frac = i / max(n - 1, 1)
                if frac < 0.6:
                    pausa = 3.0 + frac / 0.6 * 5.0          # 3→8s
                else:
                    pausa = 8.0 - (frac - 0.6) / 0.4 * 4.0  # 8→4s
                segmentos_pausa.append(round(pausa, 1))

        if not segmentos_fala:
            raise RuntimeError("Script de meditação gerado sem segmentos válidos.")

        print(f"[meditação] {len(segmentos_fala)} segmentos para sintetizar.", flush=True)

        # Sintetiza todos com uma única carga do OmniVoice
        # guidance_scale 4.5 → síntese mais comprometida com o estilo = menos jitter
        progresso(0.5, f"Sintetizando {len(segmentos_fala)} segmentos...")
        # ASMR: sussurro nativo (EN=Nicole / PT=mix3); senão clone normal pt
        # num_step=64 → dicção mais fiel (menos palavras emboladas), como no Battle
        wavs = motor.sintetizar_clone_lote(
            perfil, segmentos_fala,
            language=("en" if asmr_en else ("pt" if asmr_on else None)),
            instruct=("whisper" if asmr_on else None),
            num_step=64, guidance_scale=4.5, speed_mult=float(vel_voz),
            progresso=progresso)

        # Monta voz: 4s de intro silencioso + segmentos + pausas
        SR = motor.SR
        import librosa as _lr
        from scipy.signal import butter as _butter, sosfilt as _sosfilt

        # Pré-computa filtros do EQ (evita recalcular butter() por segmento)
        _sos_eq_lp  = _butter(4, 5000,      btype='low',  fs=SR, output='sos')
        _sos_eq_low = _butter(2, [80, 300],  btype='band', fs=SR, output='sos')

        def _aquecer(y):
            """EQ de calor: passa-baixa 5kHz + realce de graves 80-300Hz."""
            y = _sosfilt(_sos_eq_lp, y)
            graves = _sosfilt(_sos_eq_low, y)
            return (y + 0.25 * graves).astype(np.float32)

        # Pré-processa cada segmento de fala (EQ + normalização + ganho orgânico)
        progresso(0.9, "Mixando voz...")
        segs_proc = []
        dur_fala_total = 0.0
        TARGET_SEG_RMS = 0.055  # nível uniforme antes do ganho orgânico (evita ±8dB entre frases)
        for idx, wav_seg in enumerate(wavs):
            if not asmr_on:
                wav_seg = _aquecer(wav_seg)
            wav_seg = motor._caimento_pandora(wav_seg, 180)
            seg_rms = motor._rms(wav_seg)
            if seg_rms > 1e-6:
                wav_seg = (wav_seg * (TARGET_SEG_RMS / seg_rms)).astype(np.float32)
            wav_seg = motor._fade_in_cos(wav_seg, 20)  # suaviza ataque abrupto
            ganho_organico = 0.92 + 0.08 * ((idx * 0.37) % 1.0)
            wav_seg = motor._brilho(wav_seg, 0.8) * float(vol_voz) * ganho_organico
            segs_proc.append(wav_seg)
            dur_fala_total += len(wav_seg) / SR

        # ── Alvo de silêncio adaptativo (relatório: meta 60-70% de silêncio) ──
        # Para 65% de silêncio: silêncio = fala * (0.65/0.35) ≈ fala * 1.857
        ALVO_SILENCIO = 0.65
        silencio_necessario = dur_fala_total * (ALVO_SILENCIO / (1 - ALVO_SILENCIO))
        silencio_entre_frases = sum(segmentos_pausa)

        # Fase PERMANÊNCIA: um único momento de silêncio antes do retorno.
        # Capado em 35s — um bloco grande (era 150s) deixava um "buraco" enorme no meio.
        # As pausas entre frases já distribuem o silêncio ao longo da meditação.
        permanencia = silencio_necessario - silencio_entre_frases
        permanencia = max(0.0, min(permanencia, 35.0))
        # Posição: antes das 3 últimas frases (fase de retorno)
        idx_permanencia = max(1, len(segs_proc) - 3)
        print(f"[meditação] fala={dur_fala_total:.0f}s pausas={silencio_entre_frases:.0f}s "
              f"permanência={permanencia:.0f}s → silêncio≈{100*(silencio_entre_frases+permanencia)/(dur_fala_total+silencio_entre_frases+permanencia):.0f}%",
              flush=True)

        partes_voz = [np.zeros(int(SR * 4), dtype=np.float32)]  # 4s de intro
        for idx, (wav_seg, pausa) in enumerate(zip(segs_proc, segmentos_pausa)):
            if idx == idx_permanencia:
                partes_voz.append(np.zeros(int(SR * permanencia), dtype=np.float32))
            partes_voz.append(wav_seg)
            if pausa > 0:
                partes_voz.append(np.zeros(int(SR * pausa), dtype=np.float32))

        voz = np.concatenate(partes_voz)
        voz = motor._eco(voz, delay_ms=50, decay=0.15)

        # Mistura com música de fundo com ducking (abaixa quando a voz fala)
        if fundo_path:
            fundo_wav = motor._carregar_fundo(fundo_path, vol_fundo)
            if fundo_wav is not None:
                n = len(voz)
                # Loop da música para cobrir todo o áudio + 3s de cauda
                bg = np.tile(fundo_wav, n // len(fundo_wav) + 2)[:n + int(SR * 3)].astype(np.float32)

                # Fade-in da música nos primeiros 3s
                fi = min(int(SR * 3), len(bg))
                bg[:fi] *= np.linspace(0, 1, fi)

                # Ducking: detecta onde a voz está ativa e abaixa a música
                frame = int(SR * 0.05)  # janelas de 50ms
                duck_ratio = 0.35       # música vai para 35% do volume quando a voz fala
                duck_attack  = int(SR * 0.15)
                duck_release = int(SR * 0.8)
                envelope = np.ones(len(bg), dtype=np.float32)
                # Vetoriza o RMS de todos os frames de uma vez (era loop Python ~12k iter)
                n_frames = len(voz) // frame
                if n_frames > 0:
                    chunks = voz[:n_frames * frame].reshape(n_frames, frame)
                    rms_frames = np.sqrt((chunks ** 2).mean(axis=1))
                    # Só itera sobre frames com voz ativa (~35% do total em meditação)
                    for i_f in np.where(rms_frames > 0.01)[0]:
                        i = int(i_f) * frame
                        start = max(0, i - duck_attack)
                        end   = min(len(bg), i + frame + duck_release)
                        ramp_down = min(duck_attack, i - start)
                        if ramp_down > 1:
                            envelope[start:start+ramp_down] = np.minimum(
                                envelope[start:start+ramp_down],
                                np.linspace(1, duck_ratio, ramp_down))
                        envelope[i:i+frame] = np.minimum(envelope[i:i+frame], duck_ratio)
                        ramp_up = end - (i + frame)
                        if ramp_up > 1:
                            envelope[i+frame:end] = np.minimum(
                                envelope[i+frame:end],
                                np.linspace(duck_ratio, 1, ramp_up))

                bg[:len(envelope)] *= envelope

                # Fade-out final da música nos últimos 4s
                fo = min(int(SR * 4), len(bg))
                bg[-fo:] *= np.linspace(1, 0, fo)

                # Trunca bg ao tamanho da voz + 3s cauda
                bg = bg[:len(voz) + int(SR * 3)]
                voz_ext = np.concatenate([voz, np.zeros(int(SR * 3), dtype=np.float32)])
                mix = voz_ext + bg[:len(voz_ext)]
                peak = np.max(np.abs(mix)) or 1.0
                voz = (mix / peak * 0.95).astype(np.float32)

        # Normaliza RMS para ~0.032 (nível da referência profissional)
        rms = np.sqrt(np.mean(voz**2))
        if rms > 1e-6:
            voz = (voz * (0.032 / rms)).clip(-1.0, 1.0).astype(np.float32)

        # Relatório de qualidade automático (medido no áudio final, antes do resample)
        progresso(0.95, "Avaliando qualidade...")
        try:
            relatorio = _avaliar_meditacao(voz, SR, int(duracao))
        except Exception as e:
            relatorio = f"(não foi possível avaliar: {e})"
        try:
            print(f"[meditação] Relatório de qualidade:\n{relatorio}", flush=True)
        except Exception:
            pass  # falha de encoding no console não deve perder o relatório

        # Export em 44.1 kHz pseudo-estéreo binaural (Haas 0.35ms + LP canal R)
        progresso(0.97, "Convertendo para 44.1 kHz estéreo binaural...")
        voz_44k = _lr.resample(voz, orig_sr=SR, target_sr=44100).astype(np.float32)
        voz_stereo = motor._binaural_widen(voz_44k, sr=44100)  # (T, 2) — L/R divergentes

        return (44100, voz_stereo), relatorio
    _run_task(tid, lambda *a: _fn(a[-1]))
    return {"task_id": tid}

# ── Rádio Pandora ─────────────────────────────────────────────────────────────

@app.post("/api/radio")
async def gerar_radio(
    session_id: str = Form(...),
    tema: str = Form(...),
    vinheta: UploadFile = File(None),
    vol_vinheta: float = Form(0.4),
):
    perfil = _sessions.get(session_id)
    if not perfil:
        raise HTTPException(400, "Sessão inválida.")
    vin_path = await _salvar_upload(vinheta, ".wav")
    tid = _new_task()
    def _fn(progresso):
        segs = motor.gerar_radio(tema, progresso)  # retorna dict {nome: texto}
        audios = []
        silencio = np.zeros(int(motor.SR * 1.5), dtype=np.float32)
        nomes = list(segs.keys())
        for i, (seg_nome, seg_texto) in enumerate(segs.items()):
            p = 0.5 + 0.45 * i / max(1, len(nomes))
            progresso(p, f"Sintetizando {seg_nome}...")
            # entrevista tem PANDORA:/CONVIDADO: — usa sintetizar_comedia
            if seg_nome == 'entrevista':
                wav, _ = motor.sintetizar_comedia(
                    perfil, seg_texto, 1.0, 0.3, 0.0, 0.5, None, 0.0, progresso)
            else:
                wav = motor.sintetizar_clone(perfil, seg_texto, "pt", 32, 3.0, 1.0, progresso)
            audios.append(wav)
            audios.append(silencio)
        audio = np.concatenate(audios)
        if vin_path:
            fundo_wav = motor._carregar_fundo(vin_path, vol_vinheta)
            if fundo_wav is not None:
                audio = motor._misturar_fundo(audio, fundo_wav, 2.0)
        return (motor.SR, audio), ""
    _run_task(tid, lambda *a: _fn(a[-1]))
    return {"task_id": tid}

# ── Batalha de Vozes ──────────────────────────────────────────────────────────

async def _ler_texto_upload(up):
    """Lê o conteúdo de um upload de dossiê (.txt direto, .pdf via motor._ler_pdf)."""
    if not (up and up.filename):
        return ""
    data = await up.read()
    if up.filename.lower().endswith(".pdf"):
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf", dir=TMP_DIR)
        tmp.write(data); tmp.close()
        try:
            return motor._ler_pdf(tmp.name)[0] or ""
        except Exception:
            return ""
        finally:
            try:
                os.remove(tmp.name)
            except OSError:
                pass
    for enc in ("utf-8", "latin-1"):
        try:
            return data.decode(enc)
        except Exception:
            continue
    return ""

@app.post("/api/battle")
async def gerar_batalha(
    nome1: str = Form(...),
    desc1: str = Form(...),
    nome2: str = Form(...),
    desc2: str = Form(...),
    tema: str = Form(...),
    modo: str = Form("sério"),
    voz1: str = Form(""),
    voz2: str = Form(""),
    dossie1: UploadFile = File(None),
    dossie2: UploadFile = File(None),
    n_turnos: int = Form(3),
):
    perfil1 = _perfil_de_voz(voz1)
    perfil2 = _perfil_de_voz(voz2)
    # Lê os dossiês (identidade de cada personagem) — se houver, vira debate por persona
    texto1 = await _ler_texto_upload(dossie1)
    texto2 = await _ler_texto_upload(dossie2)
    usar_persona = bool(texto1.strip() or texto2.strip())
    tid = _new_task()
    def _fn(progresso):
        if usar_persona:
            # Debate turno-a-turno: cada personagem é um agente com o seu dossiê
            roteiro = motor.gerar_batalha_persona(
                nome1, texto1, nome2, texto2, tema, modo, n_turnos, progresso)
        else:
            roteiro = motor.gerar_batalha(nome1, desc1, nome2, desc2, tema, modo, progresso)
        # Cada lado pode usar voz CLONADA (galeria) ou DESIGN (descrição).
        # Só interpreta a descrição (chamada ao Gemma, ~10-15s) pra quem NÃO
        # veio da galeria — com 2 vozes clonadas, pula as duas chamadas.
        progresso(0.55, "Fixando o timbre dos personagens...")
        if perfil1:
            p1 = perfil1
        else:
            instruct1, _ = motor.interpretar_descricao_voz(desc1 or "moderate pitch", progresso)
            p1 = motor.perfil_de_design(instruct1)
        if perfil2:
            p2 = perfil2
        else:
            instruct2, _ = motor.interpretar_descricao_voz(desc2 or "moderate pitch", progresso)
            p2 = motor.perfil_de_design(instruct2)

        progresso(0.6, "Sintetizando vozes do debate...")
        SRb = motor.SR

        def _fala(lado, texto):
            # Caimento natural estilo Pandora: gera mais devagar (vogal final longa)
            # + curva de decaimento da referência. num_step=64 → dicção mais fiel
            # (menos palavras emboladas; ~2x mais lento, ok p/ debate de poucas falas).
            perfil = p1 if lado == 1 else p2
            t = (texto or "").strip().strip('"“”').strip()
            return motor.sintetizar_clone_pandora(perfil, t, speed=0.80, num_step=64, progresso=progresso)

        def _preparar(w):
            # Volume parelho entre os atores + fade-in anti-clique
            w = np.asarray(w, dtype=np.float32)
            w = np.clip(w * (0.06 / motor._rms(w)), -0.99, 0.99)
            return motor._fade_in_cos(w, 20)

        # Monta roteiro com vozes distintas linha a linha.
        # Aceita "NOME:" (qualquer caixa) e SÓ sintetiza falas dos 2 personagens —
        # linhas que continuam a fala anterior são agregadas; cabeçalhos/cena são ignorados.
        segs = []
        quem_seg = []
        lado_atual = None
        buffer = []

        def _flush():
            if lado_atual and buffer:
                texto = " ".join(buffer).strip()
                if texto:
                    segs.append(_preparar(_fala(lado_atual, texto)))
                    quem_seg.append(lado_atual)

        for linha in roteiro.strip().split('\n'):
            linha = linha.strip()
            if not linha:
                continue
            m = re.match(r'^([^:]{1,40}):\s*(.+)', linha)
            falante = m.group(1).strip().upper() if m else None
            if falante == nome1.upper():
                _flush(); lado_atual, buffer = 1, [m.group(2).strip()]
            elif falante == nome2.upper():
                _flush(); lado_atual, buffer = 2, [m.group(2).strip()]
            elif lado_atual is not None and not m:
                buffer.append(linha)  # continuação da fala anterior (sem rótulo)
            # linhas com "OUTRO_NOME:" (cabeçalho/cena) são ignoradas
        _flush()
        if not segs:
            return (motor.SR, np.zeros(1, dtype=np.float32)), roteiro

        # Montagem: gaps entre falas (0.16s mesmo ator / 0.28s na troca)
        partes = []
        g_mesmo = np.zeros(int(SRb * 0.16), dtype=np.float32)
        g_troca = np.zeros(int(SRb * 0.28), dtype=np.float32)
        for i, w in enumerate(segs):
            if i > 0:
                partes.append(g_mesmo if quem_seg[i] == quem_seg[i-1] else g_troca)
            partes.append(w)
        voz = np.concatenate(partes)
        # Sem leito de room tone: o caimento natural (curva da Pandora) já faz cada
        # fala decair suave, então as pausas não soam mais como corte — e sem o
        # chiado de fundo que o leito contínuo causava.
        audio = (voz / (np.max(np.abs(voz)) or 1) * 0.95).astype(np.float32)
        return (motor.SR, audio), roteiro
    _run_task(tid, lambda *a: _fn(a[-1]))
    return {"task_id": tid}

# ── Personagem Infinito ───────────────────────────────────────────────────────

@app.post("/api/character/create")
async def criar_personagem(
    nome: str = Form(...),
    personalidade: str = Form(...),
    desc_voz: str = Form(...),
    quirks: str = Form(""),
    emocao_padrao: str = Form("neutra"),
):
    dados = {"nome": nome, "personalidade": personalidade,
             "desc_voz": desc_voz, "quirks": quirks, "emocao_padrao": emocao_padrao}
    path = os.path.join(PERS_DIR, f"{nome}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    return {"msg": f"✅ Personagem '{nome}' salvo!"}

@app.get("/api/character/list")
def listar_personagens():
    nomes = [os.path.splitext(f)[0] for f in os.listdir(PERS_DIR) if f.endswith(".json")]
    return {"personagens": sorted(nomes)}

@app.post("/api/character/chat")
async def conversar(
    session_id: str = Form(...),
    nome_personagem: str = Form(...),
    fala_usuario: str = Form(...),
):
    path = os.path.join(PERS_DIR, f"{nome_personagem}.json")
    if not os.path.exists(path):
        raise HTTPException(404, "Personagem não encontrado.")
    with open(path, encoding="utf-8") as f:
        pers = json.load(f)
    historico = _historicos.get(session_id, [])
    tid = _new_task()
    def _fn(progresso):
        resposta, _ = motor.responder_personagem(pers, historico, fala_usuario, progresso)
        historico.append({"usuario": fala_usuario, "personagem": resposta})
        if len(historico) > 10:
            historico.pop(0)
        _historicos[session_id] = historico
        instruct, _ = motor.interpretar_descricao_voz(pers.get("desc_voz", ""), progresso)
        audio = motor.sintetizar_design(
            instruct or "female, moderate pitch", resposta, "pt", 32, 3.0, 1.0, progresso)
        chat_txt = "\n\n".join(
            f"**Você:** {t['usuario']}\n**{nome_personagem}:** {t['personagem']}"
            for t in historico)
        return (motor.SR, audio), chat_txt
    _run_task(tid, lambda *a: _fn(a[-1]))
    return {"task_id": tid}

@app.post("/api/character/reset")
async def resetar_historico(session_id: str = Form(...)):
    _historicos.pop(session_id, None)
    return {"msg": "Histórico limpo."}

# ── Static files (sempre por último) ─────────────────────────────────────────

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

if __name__ == "__main__":
    import asyncio, logging

    # Silencia o erro cosmético do asyncio no Windows quando o browser fecha a conexão
    _original_call_exception_handler = asyncio.BaseEventLoop.call_exception_handler
    def _silent_exception_handler(self, context):
        exc = context.get("exception")
        if isinstance(exc, (ConnectionResetError, OSError)) and "call_connection_lost" in str(context.get("source_traceback", "") or ""):
            return
        msg = context.get("message", "")
        if "call_connection_lost" in msg or "_ProactorBasePipeTransport" in msg:
            return
        _original_call_exception_handler(self, context)
    asyncio.BaseEventLoop.call_exception_handler = _silent_exception_handler

    print("🎙️  Estúdio de Voz — http://127.0.0.1:5008")
    uvicorn.run(app, host="127.0.0.1", port=5008, log_level="warning")
