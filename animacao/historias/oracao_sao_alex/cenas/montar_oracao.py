"""Monta o vídeo da oração: 7 cenas no ritmo do áudio, parallax suave pela profundidade,
zoom lento, transição suave, boca falando (visemas contínuos, ferramentas\visemas) nas cenas de rosto e legenda karaokê.
Estilo contido da v1 do St. Alex. Roda no .venv_omni.

    python montar_oracao.py
"""
import math, os, subprocess, sys
from pathlib import Path

os.environ.setdefault("HF_HOME", r"F:\Projeto IA\cache\huggingface")

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageFilter

AQUI = Path(__file__).parent
sys.path.insert(0, str(AQUI.parent / "exemplos"))
from demo_stalex import carregar_palavras, linhas, ts   # correções da transcrição e quebra de linhas

AUDIO = Path(r"C:\Users\Filipe Pereira\Downloads\oracao.wav")
SAIDA = AQUI.parent / "exemplos" / "03_oracao_cenas.mp4"
W, H, FPS = 1920, 1080, 30
XF = 0.5                       # duração da transição entre cenas (s)
DEV = "cuda" if torch.cuda.is_available() else "cpu"

# (imagem, início, fim) em segundos — cortes alinhados aos trechos da oração
CENAS = [
    ("o01_invocacao", 0.0, 3.6),
    ("o02_quinze_dias", 3.6, 11.2),
    ("o03_instabilidade", 11.2, 17.8),
    ("o04_luz", 17.8, 28.4),
    ("o05_malware", 28.4, 34.6),
    ("o06_tres_vezes", 34.6, 41.3),
    ("o07_amem", 41.3, None),
]


def duracao():
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(AUDIO)],
                       capture_output=True, text=True)
    return float(r.stdout.strip())


def escrever_ass(ws, caminho):
    cab = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Oracao,Georgia,58,&H0045C8F0,&H00F4EEEA,&H00301418,&H96000000,-1,0,0,0,100,100,1,0,1,4,2,2,80,80,64,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    gs = linhas(ws, max_chars=40)
    ev = []
    for k, g in enumerate(gs):
        ini = g[0]["t0"] - 0.12
        fim = g[-1]["t1"] + 0.35
        if k + 1 < len(gs):
            fim = min(fim, gs[k + 1][0]["t0"] - 0.14)
        partes = [f"{{\\k{round((g[0]['t0'] - ini) * 100)}}}"]
        for j, w in enumerate(g):
            d = (g[j + 1]["t0"] if j + 1 < len(g) else w["t1"]) - w["t0"]
            partes.append(f"{{\\kf{max(1, round(d * 100))}}}{w['w']} ")
        ev.append(f"Dialogue: 0,{ts(ini)},{ts(fim)},Oracao,,0,0,0,,{{\\fad(120,160)}}" + "".join(partes).rstrip())
    Path(caminho).write_text(cab + "\n".join(ev) + "\n", encoding="utf-8")


def ler_video(caminho, w, h):
    """Decodifica o vídeo da cena falando para quadros RGB a 30 fps, no tamanho da imagem da cena."""
    cmd = ["ffmpeg", "-v", "error", "-i", str(caminho), "-vf", f"fps={FPS},scale={w}:{h}:flags=lanczos",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3)


def main():
    dur = duracao()
    n = int(dur * FPS)
    escrever_ass(carregar_palavras(), AQUI / "legenda_oracao.ass")

    from transformers import pipeline
    prof = pipeline("depth-estimation", model="depth-anything/Depth-Anything-V2-Small-hf", device=0 if DEV == "cuda" else -1)

    ys = torch.linspace(-1, 1, H, device=DEV); xs = torch.linspace(-1, 1, W, device=DEV)
    gy, gx = torch.meshgrid(ys, xs, indexing="ij")
    cenas = []
    for i, (nome, t0, t1) in enumerate(CENAS):
        img = Image.open(AQUI / f"{nome}.png").convert("RGB")
        w0, h0 = img.size
        # "cover": recorta o excesso para caber em 16:9 sem faixas
        a_src, a_out = w0 / h0, W / H
        sx, sy = (a_out / a_src, 1.0) if a_src > a_out else (1.0, a_src / a_out)
        base = torch.stack([gx * sx, gy * sy], -1).unsqueeze(0)
        d = prof(img)["depth"].convert("L").resize((w0, h0), Image.BICUBIC).filter(ImageFilter.GaussianBlur(4))
        D = torch.from_numpy(np.asarray(d, np.float32) / 255).to(DEV)[None, None]
        D = (D - D.min()) / (D.max() - D.min() + 1e-6)
        D_out = F.grid_sample(D, base, mode="bilinear", align_corners=True)[0, 0]
        vid = AQUI / "falando" / f"{nome}_{nome}.mp4"
        quadros = ler_video(vid, w0, h0) if vid.exists() else None
        cenas.append(dict(nome=nome, t0=t0, t1=t1 if t1 is not None else dur, base=base, D=D_out,
                          img=torch.from_numpy(np.asarray(img, np.float32) / 255).permute(2, 0, 1)[None].to(DEV),
                          quadros=quadros, fase=i * 1.7))
        print(f"{nome}: {'fala' if quadros is not None else 'imagem'}  {t0:.1f}s")
    del prof; torch.cuda.empty_cache()

    AMP = 14 / (W / 2)
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-", "-i", str(AUDIO), "-vf", "ass=legenda_oracao.ass", "-c:v", "libx264", "-preset", "medium",
           "-crf", "19", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
           "-t", f"{dur:.3f}", "-movflags", "+faststart", str(SAIDA)]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE, cwd=AQUI)

    def render(c, t):
        rel = t - c["t0"]
        src = c["img"]
        if c["quadros"] is not None:
            k = min(max(int(rel * FPS), 0), len(c["quadros"]) - 1)
            src = torch.from_numpy(c["quadros"][k].astype(np.float32) / 255).permute(2, 0, 1)[None].to(DEV)
        span = c["t1"] - c["t0"] + XF
        z = 1.0 + 0.05 * min(max((rel + XF / 2) / span, 0), 1)      # zoom lento dentro da cena
        dx = AMP * math.sin(2 * math.pi * t / 11.0 + c["fase"])
        dy = AMP * 0.55 * math.sin(2 * math.pi * t / 15.0 + c["fase"] + 0.8)
        g = c["base"] / z
        g = g + torch.stack([dx * (c["D"] - 0.35), dy * (c["D"] - 0.35)], -1)[None]
        return F.grid_sample(src, g, mode="bicubic", padding_mode="border", align_corners=True)

    print(f"renderizando {n} quadros...")
    with torch.no_grad():
        for f in range(n):
            t = f / FPS
            ativos = [(c, 1.0) for c in cenas if c["t0"] - XF / 2 <= t < c["t1"] + XF / 2]
            if len(ativos) == 2:                 # transição: a nova cena aparece por cima
                a = (t - (ativos[1][0]["t0"] - XF / 2)) / XF
                q = render(ativos[0][0], t) * (1 - a) + render(ativos[1][0], t) * a
            else:
                q = render(ativos[0][0], t)
            fade = min(1.0, t / 0.6, (dur - t) / 1.0)
            q = q.clamp(0, 1) * max(fade, 0) * 255
            ff.stdin.write(q[0].permute(1, 2, 0).to(torch.uint8).cpu().numpy().tobytes())
            if f % 300 == 0:
                print(f"  {f}/{n}", flush=True)
    ff.stdin.close(); ff.wait()
    print("pronto:", SAIDA)


if __name__ == "__main__":
    main()
