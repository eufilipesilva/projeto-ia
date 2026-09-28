"""Demo do Estúdio de Animação: St. Alex com parallax 2.5D, zoom, poeira dourada,
brilho na auréola e legenda karaokê. Roda no .venv_omni (torch + transformers já instalados).

    python demo_stalex.py
"""
import json, math, os, random, subprocess, sys
from pathlib import Path

os.environ.setdefault("HF_HOME", r"F:\Projeto IA\cache\huggingface")  # C: está sem espaço

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageFilter

AQUI = Path(__file__).parent
IMG = Path(r"C:\Users\Filipe Pereira\Downloads\saoalex.jpeg")
AUDIO = Path(r"C:\Users\Filipe Pereira\Downloads\oracao.wav")
SAIDA = AQUI / "01_stalex_animado.mp4"
W, H, FPS = 1080, 1920, 30
DEV = "cuda" if torch.cuda.is_available() else "cpu"

CORRECOES = {"Envi": "Envie"}  # erros do Whisper; "Dada Joe" e "-nos" tratados em carregar_palavras


def duracao_audio():
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(AUDIO)], capture_output=True, text=True)
    return float(out.stdout.strip())


# ---------- legenda karaokê ----------
def carregar_palavras():
    ws = json.load(open(AQUI / "palavras.json", encoding="utf-8"))
    res = []
    for w in ws:
        t = w["w"]
        if t.startswith("-") and res:          # "livrai -nos" -> "livrai-nos"
            res[-1]["w"] += t; res[-1]["t1"] = w["t1"]; continue
        if t == "Dada":
            t = "DataJud"
        elif t == "Joe,":
            res[-1]["w"] += ","; res[-1]["t1"] = w["t1"]; continue
        t = CORRECOES.get(t, t)
        res.append({"w": t, "t0": w["t0"], "t1": w["t1"]})
    return res


def linhas(ws, max_chars=24):
    grupos, atual = [], []
    for i, w in enumerate(ws):
        atual.append(w)
        txt = " ".join(x["w"] for x in atual)
        prox = ws[i + 1] if i + 1 < len(ws) else None
        pausa = prox and prox["t0"] - w["t1"] > 0.45
        if w["w"][-1] in ".,;!?" or pausa or len(txt) >= max_chars or prox is None:
            grupos.append(atual); atual = []
    return grupos


def ts(t):
    t = max(t, 0); h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def escrever_ass(ws, caminho):
    cab = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Vitral,Georgia,66,&H0045C8F0,&H00F4EEEA,&H00301418,&H96000000,-1,0,0,0,100,100,1,0,1,5,3,2,50,50,150,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    gs = linhas(ws)
    ev = []
    for k, g in enumerate(gs):
        ini = g[0]["t0"] - 0.12
        fim = g[-1]["t1"] + 0.35
        if k + 1 < len(gs):
            fim = min(fim, gs[k + 1][0]["t0"] - 0.14)
        partes = [f"{{\\k{round((g[0]['t0'] - ini) * 100)}}}"]
        for j, w in enumerate(g):
            dur = (g[j + 1]["t0"] if j + 1 < len(g) else w["t1"]) - w["t0"]
            partes.append(f"{{\\kf{max(1, round(dur * 100))}}}{w['w']} ")
        ev.append(f"Dialogue: 0,{ts(ini)},{ts(fim)},Vitral,,0,0,0,,{{\\fad(120,160)}}" + "".join(partes).rstrip())
    Path(caminho).write_text(cab + "\n".join(ev) + "\n", encoding="utf-8")
    return len(ev)


# ---------- imagem e profundidade ----------
def profundidade(img):
    from transformers import pipeline
    pipe = pipeline("depth-estimation", model="depth-anything/Depth-Anything-V2-Small-hf", device=0 if DEV == "cuda" else -1)
    d = pipe(img)["depth"].convert("L").resize(img.size, Image.BICUBIC)
    del pipe; torch.cuda.empty_cache()
    return d


def tensor(img):
    a = torch.from_numpy(np.asarray(img, dtype=np.float32) / 255.0)
    return a.permute(2, 0, 1).unsqueeze(0).to(DEV)


def grade(h, w):
    ys = torch.linspace(-1, 1, h, device=DEV); xs = torch.linspace(-1, 1, w, device=DEV)
    gy, gx = torch.meshgrid(ys, xs, indexing="ij")
    return torch.stack([gx, gy], -1).unsqueeze(0)


def main():
    dur = duracao_audio()
    n_frames = int(dur * FPS)
    ws = carregar_palavras()
    n_leg = escrever_ass(ws, AQUI / "legenda.ass")
    print(f"legenda: {n_leg} linhas · {len(ws)} palavras · {dur:.1f}s")

    src = Image.open(IMG).convert("RGB")
    fw = 980                                        # vitral menor: abre faixa para a legenda embaixo
    fh = round(src.height * fw / src.width)         # 1470
    fg_img = src.resize((fw, fh), Image.LANCZOS)
    x0, y0 = (W - fw) // 2, 110

    print("estimando profundidade (Depth Anything V2 Small)...")
    dep = profundidade(src)
    dep.save(AQUI / "01_mapa_profundidade.png")
    dep = dep.resize((fw, fh), Image.BICUBIC).filter(ImageFilter.GaussianBlur(5))

    bg = src.resize((round(src.width * H / src.height * 1.15), round(H * 1.15)), Image.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(38))
    bx, by = (bg.width - W) // 2, (bg.height - H) // 2
    bg = bg.crop((bx, by, bx + W, by + H))

    FG = tensor(fg_img)
    D = torch.from_numpy(np.asarray(dep, dtype=np.float32) / 255.0).to(DEV)
    D = (D - D.min()) / (D.max() - D.min() + 1e-6)
    BG = tensor(bg) * 0.72
    G_fg = grade(fh, fw)
    G_full = grade(H, W)

    # brilho da auréola (centro aproximado da cabeça do santo)
    hy, hx = y0 + fh * 0.165, x0 + fw * 0.5
    yy, xx = torch.meshgrid(torch.arange(H, device=DEV), torch.arange(W, device=DEV), indexing="ij")
    halo = torch.exp(-(((xx - hx) / 250) ** 2 + ((yy - hy) / 230) ** 2)).unsqueeze(0).unsqueeze(0)
    ouro = torch.tensor([1.0, 0.82, 0.45], device=DEV).view(1, 3, 1, 1)

    # poeira dourada
    random.seed(7)
    parts = [dict(x=random.uniform(0, W), y=random.uniform(0, H), vy=random.uniform(-38, -12),
                  fase=random.uniform(0, 6.28), fr=random.uniform(0.6, 1.8), r=random.choice([2, 2, 3, 3, 4, 6]))
             for _ in range(110)]
    sprites = {}
    for r in {p["r"] for p in parts}:
        k = r * 3
        a = torch.arange(-k, k + 1, device=DEV, dtype=torch.float32)
        sprites[r] = torch.exp(-(a.view(-1, 1) ** 2 + a.view(1, -1) ** 2) / (2 * (r * 0.8) ** 2))

    AMP = 16 / (fw / 2)   # 16 px de deslocamento máximo na frente
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-", "-i", str(AUDIO), "-vf", "ass=legenda.ass", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-t", f"{dur:.3f}",
           "-movflags", "+faststart", SAIDA.name]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE, cwd=AQUI)

    print(f"renderizando {n_frames} quadros em {DEV}...")
    with torch.no_grad():
        for f in range(n_frames):
            t = f / FPS
            # parallax: câmera flutuando devagar; o que está perto (D alto) se move mais
            dx = AMP * math.sin(2 * math.pi * t / 11.0)
            dy = AMP * 0.55 * math.sin(2 * math.pi * t / 15.0 + 0.8)
            g = G_fg.clone()
            g[..., 0] += dx * (D - 0.35)
            g[..., 1] += dy * (D - 0.35)
            fg = F.grid_sample(FG, g, mode="bilinear", padding_mode="border", align_corners=True)

            quadro = BG.clone()
            # fundo desfocado vai para o lado oposto, reforçando a profundidade
            quadro = torch.roll(quadro, shifts=(int(-dy * 180), int(-dx * 180)), dims=(2, 3))
            quadro[:, :, y0:y0 + fh, x0:x0 + fw] = fg

            # zoom lento da câmera (1.00 -> 1.07)
            z = 1.0 + 0.07 * (t / dur)
            quadro = F.grid_sample(quadro, G_full / z, mode="bilinear", align_corners=True)

            # auréola pulsando
            pulso = 0.10 + 0.07 * math.sin(2 * math.pi * t / 4.0)
            quadro = quadro + halo * ouro * pulso

            # poeira dourada subindo e cintilando
            for p in parts:
                y = (p["y"] + p["vy"] * t) % H
                x = (p["x"] + 14 * math.sin(p["fase"] + t * 0.7)) % W
                a = 0.25 + 0.55 * (0.5 + 0.5 * math.sin(p["fase"] + t * p["fr"] * 2.2))
                s = sprites[p["r"]]; k = s.shape[0] // 2
                xi, yi = int(x), int(y)
                x1, x2, y1, y2 = max(xi - k, 0), min(xi + k + 1, W), max(yi - k, 0), min(yi + k + 1, H)
                if x2 <= x1 or y2 <= y1:
                    continue
                sp = s[y1 - yi + k:y2 - yi + k, x1 - xi + k:x2 - xi + k]
                quadro[:, :, y1:y2, x1:x2] += sp * a * ouro[0]

            # fade de entrada e saída
            fade = min(1.0, t / 0.8, (dur - t) / 1.0)
            quadro = (quadro.clamp(0, 1) * max(fade, 0)) * 255
            ff.stdin.write(quadro[0].permute(1, 2, 0).to(torch.uint8).cpu().numpy().tobytes())
            if f % 150 == 0:
                print(f"  {f}/{n_frames}", flush=True)
    ff.stdin.close(); ff.wait()
    print("pronto:", SAIDA)


if __name__ == "__main__":
    main()
