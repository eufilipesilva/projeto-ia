"""Demo v2 — St. Alex "vivo": luz que reage à voz, raios, reflexo no vitral, brilhos,
respiração, zoom nas palavras fortes, legenda que salta e explosão de luz no Amém.

    python demo_stalex_v2.py
"""
import math, random, re, subprocess
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
import torch.nn.functional as F
from PIL import Image, ImageFilter

from demo_stalex import (AQUI, AUDIO, DEV, FPS, H, IMG, W, carregar_palavras, duracao_audio,
                         grade, linhas, tensor, ts)

SAIDA = AQUI / "02_stalex_vivo.mp4"
FORTES = {"impossíveis", "proteja", "instabilidade", "luz", "brilhantes", "malware", "datajud", "três", "amém"}


def limpa(w):
    return re.sub(r"[^\wÀ-ú]", "", w).lower()


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
            txt = w["w"]
            if limpa(txt) in FORTES:   # palavra forte em ouro mais quente e maior
                txt = f"{{\\fscx112\\fscy112\\1c&H2FA8F5&}}{txt}{{\\fscx100\\fscy100\\1c&H45C8F0&}}"
            partes.append(f"{{\\kf{max(1, round(dur * 100))}}}{txt} ")
        pop = "{\\fad(90,160)\\fscx78\\fscy78\\t(0,170,\\fscx104\\fscy104)\\t(170,260,\\fscx100\\fscy100)}"
        ev.append(f"Dialogue: 0,{ts(ini)},{ts(fim)},Vitral,,0,0,0,,{pop}" + "".join(partes).rstrip())
    Path(caminho).write_text(cab + "\n".join(ev) + "\n", encoding="utf-8")


def envelope_voz(n_frames):
    a, sr = sf.read(str(AUDIO), dtype="float32")
    if a.ndim > 1:
        a = a.mean(1)
    hop = sr / FPS
    rms = np.array([np.sqrt(np.mean(a[int(i * hop):int((i + 1) * hop)] ** 2) + 1e-9) for i in range(n_frames)])
    rms = rms / np.percentile(rms, 95)
    sm = np.zeros_like(rms)            # ataque rápido, soltura lenta
    for i, v in enumerate(rms):
        prev = sm[i - 1] if i else 0
        sm[i] = prev + (v - prev) * (0.55 if v > prev else 0.08)
    return np.clip(sm, 0, 1.2)


def main():
    dur = duracao_audio()
    n = int(dur * FPS)
    ws = carregar_palavras()
    escrever_ass(ws, AQUI / "legenda_v2.ass")
    env = envelope_voz(n)
    batidas = [w["t0"] for w in ws if limpa(w["w"]) in FORTES]
    t_amem = next((w["t0"] for w in reversed(ws) if limpa(w["w"]) == "amém"), dur - 1.5)

    src = Image.open(IMG).convert("RGB")
    fw = 980; fh = round(src.height * fw / src.width); x0, y0 = (W - fw) // 2, 110
    fg_img = src.resize((fw, fh), Image.LANCZOS)
    dep = Image.open(AQUI / "01_mapa_profundidade.png").convert("L").resize((fw, fh), Image.BICUBIC).filter(ImageFilter.GaussianBlur(5))

    bg = src.resize((round(src.width * H / src.height * 1.2), round(H * 1.2)), Image.LANCZOS).filter(ImageFilter.GaussianBlur(38))
    bx, by = (bg.width - W) // 2, (bg.height - H) // 2
    bg = bg.crop((bx, by, bx + W, by + H))

    FG = tensor(fg_img)
    D = torch.from_numpy(np.asarray(dep, dtype=np.float32) / 255.0).to(DEV)
    D = (D - D.min()) / (D.max() - D.min() + 1e-6)
    BG = tensor(bg) * 0.68
    G_fg, G_full = grade(fh, fw), grade(H, W)
    ouro = torch.tensor([1.0, 0.82, 0.45], device=DEV).view(1, 3, 1, 1)
    quente = torch.tensor([1.0, 0.93, 0.78], device=DEV).view(1, 3, 1, 1)

    # máscaras no espaço do vitral
    fundo = (1 - D).clamp(0, 1) ** 1.5                     # vidro de trás
    yy, xx = torch.meshgrid(torch.arange(fh, device=DEV, dtype=torch.float32),
                            torch.arange(fw, device=DEV, dtype=torch.float32), indexing="ij")
    hx, hy = fw * 0.5, fh * 0.165                            # centro da auréola
    ang = torch.atan2(yy - hy, xx - hx)
    raio = torch.sqrt((xx - hx) ** 2 + (yy - hy) ** 2)
    halo = torch.exp(-((raio / 230) ** 2))
    queda_raios = torch.exp(-raio / 520)

    # candidatos a brilho: pixels dourados e claros do vitral
    arr = np.asarray(fg_img, dtype=np.float32) / 255
    ys, xs = np.where((arr.mean(2) > 0.78) & (arr[..., 0] > arr[..., 2] + 0.25))
    random.seed(3)
    idx = random.sample(range(len(ys)), min(70, len(ys)))
    brilhos = [dict(x=int(xs[i]), y=int(ys[i]), t=random.uniform(0, dur), p=random.uniform(2.5, 5.5)) for i in idx]
    k = 22
    a = torch.arange(-k, k + 1, device=DEV, dtype=torch.float32)
    X, Y = a.view(1, -1), a.view(-1, 1)
    estrela = (torch.exp(-(X ** 2) / 2.5 - (Y ** 2) / 90) + torch.exp(-(Y ** 2) / 2.5 - (X ** 2) / 90)
               + 1.4 * torch.exp(-(X ** 2 + Y ** 2) / 10)).clamp(0, 1.6)

    # poeira + explosão final
    random.seed(7)
    poeira = [dict(x=random.uniform(0, W), y=random.uniform(0, H), vy=random.uniform(-45, -14), f=random.uniform(0, 6.28),
                   fr=random.uniform(0.6, 1.8), r=random.choice([2, 2, 3, 3, 4, 6])) for _ in range(130)]
    cx, cy = x0 + hx, y0 + hy
    explosao = []
    for _ in range(170):
        th = random.uniform(0, 6.283); v = random.uniform(180, 720)
        explosao.append(dict(vx=v * math.cos(th), vy=v * math.sin(th) - 60, r=random.choice([2, 3, 3, 4, 6]), f=random.uniform(0, 6.28)))
    sprites = {}
    for r in (2, 3, 4, 6):
        kk = r * 3; b = torch.arange(-kk, kk + 1, device=DEV, dtype=torch.float32)
        sprites[r] = torch.exp(-(b.view(-1, 1) ** 2 + b.view(1, -1) ** 2) / (2 * (r * 0.8) ** 2))

    def carimbo(img, s, x, y, forca, cor):
        kk = s.shape[0] // 2; xi, yi = int(x), int(y)
        x1, x2, y1, y2 = max(xi - kk, 0), min(xi + kk + 1, img.shape[3]), max(yi - kk, 0), min(yi + kk + 1, img.shape[2])
        if x2 > x1 and y2 > y1:
            img[:, :, y1:y2, x1:x2] += s[y1 - yi + kk:y2 - yi + kk, x1 - xi + kk:x2 - xi + kk] * forca * cor[0]

    AMP = 26 / (fw / 2)
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-", "-i", str(AUDIO), "-vf", "ass=legenda_v2.ass", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-t", f"{dur:.3f}",
           "-movflags", "+faststart", SAIDA.name]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE, cwd=AQUI)
    print(f"renderizando {n} quadros em {DEV}...")

    with torch.no_grad():
        for f in range(n):
            t = f / FPS
            e = float(env[f])

            # câmera na mão: soma de ondas lentas
            dx = AMP * (0.75 * math.sin(2 * math.pi * t / 9.0) + 0.25 * math.sin(2 * math.pi * t / 3.7 + 1.3))
            dy = AMP * (0.45 * math.sin(2 * math.pi * t / 13.0 + 0.8) + 0.15 * math.sin(2 * math.pi * t / 4.3))
            resp = 0.007 * math.sin(2 * math.pi * t / 4.6)          # respiração
            g = G_fg.clone()
            g[..., 0] += dx * (D - 0.35)
            g[..., 1] += dy * (D - 0.35) + resp * D * (g[..., 1] + 0.2)
            fg = F.grid_sample(FG, g, mode="bilinear", padding_mode="border", align_corners=True)

            # raios girando atrás do santo, mais fortes quando ele fala
            raios = (0.5 + 0.5 * torch.cos(14 * ang + t * 0.35)) ** 6 * queda_raios * fundo
            fg = fg + raios * ouro * (0.10 + 0.22 * e)
            # reflexo de sol atravessando o vidro a cada 9 s
            pos = ((t % 9.0) / 9.0) * (fw + fh * 0.6 + 700) - 350
            faixa = torch.exp(-(((xx + yy * 0.6) - pos) / 110) ** 2)
            fg = fg + faixa * fundo * quente * 0.20
            # auréola acompanha a voz
            fg = fg + halo * ouro * (0.06 + 0.26 * e)
            # brilhos de estrela nos dourados
            for b in brilhos:
                fase = ((t - b["t"]) % b["p"]) / 0.7
                if 0 <= fase < 1:
                    carimbo(fg, estrela, b["x"], b["y"], math.sin(math.pi * fase) * 0.9, quente)

            quadro = torch.roll(BG, shifts=(int(-dy * 260), int(-dx * 260)), dims=(2, 3)).clone()
            quadro[:, :, y0:y0 + fh, x0:x0 + fw] = fg

            # zoom: lento + batidas nas palavras fortes
            z = 1.0 + 0.06 * (t / dur)
            for tb in batidas:
                if 0 <= t - tb < 0.9:
                    u = (t - tb) / 0.9
                    z += 0.03 * math.sin(math.pi * min(u * 3, 1) / 2) * (1 - u) ** 2
            quadro = F.grid_sample(quadro, G_full / z, mode="bilinear", align_corners=True)

            for p in poeira:
                y = (p["y"] + p["vy"] * t) % H
                x = (p["x"] + 16 * math.sin(p["f"] + t * 0.7)) % W
                forca = (0.25 + 0.55 * (0.5 + 0.5 * math.sin(p["f"] + t * p["fr"] * 2.2))) * (0.8 + 0.5 * e)
                carimbo(quadro, sprites[p["r"]], x, y, forca, ouro)

            # Amém: clarão e explosão de luz saindo da auréola
            dt = t - t_amem
            if dt >= 0:
                quadro = quadro + ouro * 0.45 * math.exp(-dt * 3.2)
                for p in explosao:
                    x = cx + p["vx"] * dt; y = cy + p["vy"] * dt + 90 * dt * dt
                    carimbo(quadro, sprites[p["r"]], x, y, max(0.0, 1 - dt / 2.6) * (0.7 + 0.3 * math.sin(p["f"] + dt * 9)), ouro)

            fade = min(1.0, t / 0.8, (dur - t) / 1.0)
            quadro = quadro.clamp(0, 1) * max(fade, 0) * 255
            ff.stdin.write(quadro[0].permute(1, 2, 0).to(torch.uint8).cpu().numpy().tobytes())
            if f % 150 == 0:
                print(f"  {f}/{n}", flush=True)
    ff.stdin.close(); ff.wait()
    print("pronto:", SAIDA)


if __name__ == "__main__":
    main()
