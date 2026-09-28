"""Revisor técnico de animação falante: mede rosto, movimento da boca e sincronia boca↔áudio.

Roda no venv do JoyVASA (usa o detector de rosto e os 203 pontos faciais do LivePortrait,
que funcionam em rosto desenhado).

    F:\\Projeto IA\\ferramentas\\JoyVASA\\.venv\\Scripts\\python.exe analisar_animacao.py VIDEO.mp4
        [--audio AUDIO.wav] [--ref IMAGEM_ORIGINAL.png] [--saida PASTA]

Gera na pasta de saída:
  relatorio.json      métricas + veredito por critério
  rostos.png          recortes ampliados do rosto ao longo do vídeo (qualidade do desenho)
  bocas.png           recortes da boca do mais fechado ao mais aberto (qualidade do movimento)
  sincronia.png       curva de abertura da boca x volume da voz (sincronização)
"""
import argparse, json, os, subprocess, sys
from pathlib import Path

JOY = Path(r"F:\Projeto IA\ferramentas\JoyVASA")
sys.path.insert(0, str(JOY))
os.chdir(JOY)  # os caminhos dos pesos no config são relativos ao repositório

import numpy as np
import cv2
from PIL import Image, ImageDraw
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from skimage.metrics import structural_similarity as ssim

from src.config.crop_config import CropConfig
from src.utils.cropper import Cropper

# índices dos 203 pontos do LivePortrait
LAB_SUP, LAB_INF, CANTO_E, CANTO_D = 90, 102, 48, 66   # centro dos lábios e cantos da boca
OLHO_E = (0, 12, 6, 18)                                   # cantos e pálpebras do olho esquerdo
OLHO_D = (24, 36, 30, 42)


# ---------------------------------------------------------------- entrada
def sondar(video):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,r_frame_rate:format=duration", "-of", "json", str(video)],
                       capture_output=True, text=True)
    j = json.loads(r.stdout)
    s = j["streams"][0]
    n, d = s["r_frame_rate"].split("/")
    return int(s["width"]), int(s["height"]), float(n) / float(d), float(j["format"]["duration"])


def ler_quadros(video, w, h):
    cmd = ["ffmpeg", "-v", "error", "-i", str(video), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3)


def ler_audio(fonte, sr=16000):
    cmd = ["ffmpeg", "-v", "error", "-i", str(fonte), "-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    return np.frombuffer(raw, np.float32), sr


def envelope(audio, sr, fps, n):
    hop = sr / fps
    falta = int(np.ceil(n * hop)) - len(audio)
    if falta > 0:                                      # vídeo um pouco mais longo que o áudio
        audio = np.concatenate([audio, np.zeros(falta, np.float32)])
    rms = np.array([np.sqrt(np.mean(audio[int(i * hop):int((i + 1) * hop)] ** 2) + 1e-10) for i in range(n)])
    db = 20 * np.log10(rms + 1e-10)
    fala = db > (np.percentile(db, 95) - 25)          # voz ativa: até 25 dB abaixo dos picos
    return rms, fala


# ---------------------------------------------------------------- rosto
def pontos_por_quadro(cropper, quadros):
    """Detecta o rosto no 1º quadro e segue os 203 pontos quadro a quadro."""
    face = cropper.face_analysis_wrapper.get(np.ascontiguousarray(quadros[0][..., ::-1]),
                                             flag_do_landmark_2d_106=True, direction="large-small")
    if not face:
        raise SystemExit("Nenhum rosto detectado no primeiro quadro.")
    lmk = face[0].landmark_2d_106
    todos = []
    for q in quadros:
        lmk = cropper.human_landmark_runner.run(q, lmk)
        todos.append(lmk.copy())
    return np.stack(todos)                               # (N, 203, 2)


def d(l, a, b):
    return np.linalg.norm(l[:, a] - l[:, b], axis=1)


def caixa(pts, margem, w, h):
    x0, y0 = pts.min(0); x1, y1 = pts.max(0)
    mx, my = (x1 - x0) * margem, (y1 - y0) * margem
    return (int(max(x0 - mx, 0)), int(max(y0 - my, 0)), int(min(x1 + mx, w)), int(min(y1 + my, h)))


def quadrado(pts, fator, w, h):
    """Recorte quadrado centrado nos pontos (lado = fator × maior dimensão) — sem distorcer ao redimensionar."""
    x0, y0 = pts.min(0); x1, y1 = pts.max(0)
    cx, cy, lado = (x0 + x1) / 2, (y0 + y1) / 2, max(x1 - x0, y1 - y0) * fator
    return (int(max(cx - lado / 2, 0)), int(max(cy - lado / 2, 0)), int(min(cx + lado / 2, w)), int(min(cy + lado / 2, h)))


def nitidez(img):
    g = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    return float(cv2.Laplacian(g, cv2.CV_64F).var())


def rosto_ref(cropper, ref_path):
    img = np.asarray(Image.open(ref_path).convert("RGB"))
    face = cropper.face_analysis_wrapper.get(np.ascontiguousarray(img[..., ::-1]), flag_do_landmark_2d_106=True,
                                             direction="large-small")
    if not face:
        return None, None
    lmk = cropper.human_landmark_runner.run(img, face[0].landmark_2d_106)
    return img, lmk


def recorte_alinhado(img, lmk, tam=160):
    """Rosto recortado pela caixa dos pontos, redimensionado — para comparar identidade."""
    h, w = img.shape[:2]
    x0, y0, x1, y1 = quadrado(lmk, 1.1, w, h)
    return cv2.resize(img[y0:y1, x0:x1], (tam, tam), interpolation=cv2.INTER_AREA)


# ---------------------------------------------------------------- análise
def correlacao_com_atraso(boca, voz, fps, max_ms=400):
    """Atraso (ms) que maximiza a correlação entre abertura da boca e volume. >0 = boca atrasada."""
    a = (boca - boca.mean()) / (boca.std() + 1e-9)
    b = (voz - voz.mean()) / (voz.std() + 1e-9)
    max_k = int(max_ms / 1000 * fps)
    res = []
    for k in range(-max_k, max_k + 1):
        if k >= 0:
            x, y = a[k:], b[:len(b) - k]
        else:
            x, y = a[:k], b[-k:]
        if len(x) > 10:
            res.append((k, float(np.corrcoef(x, y)[0, 1])))
    k, r = max(res, key=lambda t: t[1])
    r0 = dict(res).get(0, float("nan"))
    return k / fps * 1000, r, r0, res


def suavizar(x, n=3):
    k = np.ones(n) / n
    return np.convolve(np.pad(x, (n // 2, n // 2), mode="edge"), k, mode="valid")


def veredito(valor, bom, aceitavel, maior_melhor=True):
    if maior_melhor:
        return "bom" if valor >= bom else "aceitável" if valor >= aceitavel else "ruim"
    return "bom" if valor <= bom else "aceitável" if valor <= aceitavel else "ruim"


# ---------------------------------------------------------------- imagens do relatório
def folha(imgs, legendas, colunas, tam, caminho, titulo):
    linhas_n = (len(imgs) + colunas - 1) // colunas
    W, Hc = colunas * tam, linhas_n * (tam + 22) + 30
    fol = Image.new("RGB", (W, Hc), (24, 22, 34))
    dr = ImageDraw.Draw(fol)
    dr.text((8, 8), titulo, fill=(240, 220, 150))
    for i, (im, leg) in enumerate(zip(imgs, legendas)):
        x, y = (i % colunas) * tam, 30 + (i // colunas) * (tam + 22)
        fol.paste(Image.fromarray(im).resize((tam, tam), Image.LANCZOS), (x, y))
        dr.text((x + 6, y + tam + 4), leg, fill=(220, 220, 230))
    fol.save(caminho)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video"); ap.add_argument("--audio"); ap.add_argument("--ref"); ap.add_argument("--saida")
    ap.add_argument("--deslocar-audio", type=float, default=0.0,
                    help="controle negativo: desloca o áudio N segundos só para o SyncNet (a nota deve cair)")
    a = ap.parse_args()
    video = Path(a.video).resolve()
    saida = Path(a.saida).resolve() if a.saida else video.parent / f"revisao_{video.stem}"
    saida.mkdir(parents=True, exist_ok=True)

    w, h, fps, dur = sondar(video)
    quadros = ler_quadros(video, w, h)
    n = len(quadros)
    audio, sr = ler_audio(a.audio or video)
    rms, fala = envelope(audio, sr, fps, n)

    cropper = Cropper(crop_cfg=CropConfig(), image_type="human_face", flag_force_cpu=False)
    L = pontos_por_quadro(cropper, quadros)

    # ---- sincronia pelo SyncNet (métrica padrão da literatura)
    sys.path.insert(0, str(Path(__file__).parent))
    from syncnet_lse import medir as medir_syncnet
    sn, faces_sn = medir_syncnet(quadros, L, fps, audio, deslocar_s=a.deslocar_audio)
    Image.fromarray(np.concatenate([f[..., ::-1] for f in faces_sn[::max(len(faces_sn) // 6, 1)][:6]], 1)).save(
        saida / "syncnet_recortes.png")

    # ---- boca
    largura = d(L, CANTO_E, CANTO_D)
    abertura = d(L, LAB_SUP, LAB_INF) / (largura + 1e-6)
    ab_s = suavizar(abertura)
    amp = float(np.percentile(ab_s, 95) - np.percentile(ab_s, 5))
    jitter = float(np.mean(np.abs(np.diff(abertura, 2)))) / (amp + 1e-9)       # tremedeira relativa
    ab_fala = float(ab_s[fala].mean()) if fala.any() else float("nan")
    ab_sil = float(ab_s[~fala].mean()) if (~fala).any() else float("nan")
    fecha_silencio = (ab_fala - ab_sil) / (amp + 1e-9) if (~fala).sum() > fps * 0.3 else None
    # atividade: aberturas da boca por segundo x sílabas por segundo na voz
    from scipy.signal import find_peaks
    pb, _ = find_peaks(ab_s, prominence=max(amp * 0.25, 0.01), distance=max(int(fps * 0.1), 1))
    env_voz = suavizar(20 * np.log10(rms + 1e-10), 3)
    pv, _ = find_peaks(env_voz, prominence=3.0, distance=max(int(fps * 0.1), 1))
    seg_fala = max(fala.sum() / fps, 1e-6)
    aberturas_s = float(len(pb) / seg_fala)
    silabas_s = float(len(pv) / seg_fala)
    cobertura = aberturas_s / (silabas_s + 1e-9)
    atraso_ms, r_max, r0, curva = correlacao_com_atraso(ab_s, suavizar(np.log(rms + 1e-6), 5), fps)
    # movimento geral da cabeça (desvio do centro do rosto em % da largura do rosto)
    centro = L.mean(1)
    larg_rosto = np.ptp(L[:, :, 0], axis=1).mean()
    mov_cabeca = float(np.percentile(np.linalg.norm(centro - centro[0], axis=1), 95) / larg_rosto * 100)

    # ---- rosto: nitidez da boca vs. olhos, estabilidade e identidade
    amostras = np.linspace(0, n - 1, min(12, n)).astype(int)
    nit_boca, nit_olhos, rostos, legs = [], [], [], []
    for i in amostras:
        q, l = quadros[i], L[i]
        bx = caixa(l[[CANTO_E, CANTO_D, LAB_SUP, LAB_INF]], 0.35, w, h)
        ox = caixa(l[list(OLHO_E + OLHO_D)], 0.25, w, h)
        nit_boca.append(nitidez(q[bx[1]:bx[3], bx[0]:bx[2]]))
        nit_olhos.append(nitidez(q[ox[1]:ox[3], ox[0]:ox[2]]))
        fx = quadrado(l, 1.15, w, h)
        rostos.append(q[fx[1]:fx[3], fx[0]:fx[2]])
        legs.append(f"{i / fps:5.2f}s  abertura {abertura[i]:.2f}")
    razao_nitidez = float(np.median(np.array(nit_boca) / (np.array(nit_olhos) + 1e-6)))

    ident = None
    if a.ref:
        ref_img, ref_l = rosto_ref(cropper, a.ref)
        if ref_img is not None:
            rr = cv2.cvtColor(recorte_alinhado(ref_img, ref_l), cv2.COLOR_RGB2GRAY)
            vals = [ssim(rr, cv2.cvtColor(recorte_alinhado(quadros[i], L[i]), cv2.COLOR_RGB2GRAY), data_range=255)
                    for i in amostras]
            ident = {"ssim_medio": float(np.mean(vals)), "ssim_minimo": float(np.min(vals)),
                     "no_tempo_s": float(amostras[int(np.argmin(vals))] / fps)}

    # ---- imagens
    folha(rostos, legs, 4, 256, saida / "rostos.png", f"Rostos ao longo do vídeo — {video.name}")
    ordem = np.argsort(abertura)
    esc = ordem[np.linspace(0, n - 1, 12).astype(int)]
    bocas, legb = [], []
    for i in esc:
        bx = quadrado(L[i][[CANTO_E, CANTO_D, LAB_SUP, LAB_INF]], 1.5, w, h)
        bocas.append(quadros[i][bx[1]:bx[3], bx[0]:bx[2]])
        legb.append(f"{i / fps:5.2f}s  ab {abertura[i]:.2f} {'fala' if fala[i] else 'silêncio'}")
    folha(bocas, legb, 6, 200, saida / "bocas.png", "Boca: do mais fechado ao mais aberto")

    t = np.arange(n) / fps
    fig, ax = plt.subplots(2, 1, figsize=(12, 6), sharex=True)
    ax[0].plot(t, ab_s, color="#5B3F8F", lw=1.4, label="abertura da boca")
    ax[0].fill_between(t, ab_s.min(), ab_s.max(), where=fala, color="#F1D38B", alpha=.35, label="voz ativa")
    ax[0].legend(loc="upper right"); ax[0].set_ylabel("abertura")
    ax[0].set_title(f"Sincronia: atraso {atraso_ms:+.0f} ms (boca {'atrasada' if atraso_ms > 0 else 'adiantada'}), "
                    f"correlação {r_max:.2f}")
    ax[0].plot(t[pb], ab_s[pb], "o", color="#5B3F8F", ms=5)
    ax[1].plot(t, env_voz, color="#9A6E1C", lw=1)
    ax[1].plot(t[pv], env_voz[pv], "o", color="#9A6E1C", ms=4)
    ax[1].set_ylim(max(env_voz.min(), np.percentile(env_voz, 2) - 6), env_voz.max() + 3)
    ax[1].set_ylabel("volume (dB)"); ax[1].set_xlabel("tempo (s)")
    fig.tight_layout(); fig.savefig(saida / "sincronia.png", dpi=90); plt.close(fig)

    # ---- relatório
    rel = {
        "video": str(video), "duracao_s": round(dur, 2), "fps": round(fps, 2), "quadros": n, "resolucao": f"{w}x{h}",
        "boca": {
            "amplitude_abertura": round(amp, 3),
            "tremedeira_relativa": round(jitter, 3),
            "abertura_media_fala": round(ab_fala, 3), "abertura_media_silencio": round(ab_sil, 3),
            "fecha_nos_silencios": None if fecha_silencio is None else round(float(fecha_silencio), 2),
            "aberturas_por_segundo": round(aberturas_s, 2),
            "silabas_por_segundo_na_voz": round(silabas_s, 2),
            "cobertura_silabas": round(cobertura, 2),
            "veredito_cobertura": veredito(cobertura, 0.6, 0.35),
            "veredito_amplitude": veredito(amp, 0.20, 0.10),
            "veredito_tremedeira": veredito(jitter, 0.08, 0.15, maior_melhor=False),
        },
        "sincronia": {
            "syncnet": {
                "lse_c": sn["lse_c"], "lse_d": sn["lse_d"], "offset_ms": sn["offset_ms"],
                "audio_deslocado_s": a.deslocar_audio,
                "veredito_lse_c": veredito(sn["lse_c"], 5.0, 3.0),
                "veredito_offset": veredito(abs(sn["offset_ms"]), 40, 120, maior_melhor=False),
            },
            "atraso_ms": round(atraso_ms), "correlacao_no_melhor_atraso": round(r_max, 3),
            "correlacao_sem_atraso": round(r0, 3),
            "veredito_atraso": veredito(abs(atraso_ms), 45, 100, maior_melhor=False),
            "veredito_correlacao": veredito(r_max, 0.5, 0.3),
        },
        "rosto": {
            "nitidez_boca_sobre_olhos": round(razao_nitidez, 3),
            "veredito_nitidez_boca": veredito(razao_nitidez, 0.6, 0.35),
            "movimento_cabeca_pct_largura": round(mov_cabeca, 2),
            "identidade_vs_referencia": ident,
        },
        "arquivos": ["rostos.png", "bocas.png", "sincronia.png", "syncnet_recortes.png"],
    }
    (saida / "relatorio.json").write_text(json.dumps(rel, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(rel, ensure_ascii=False, indent=2))
    print("\nimagens em:", saida)


if __name__ == "__main__":
    main()
