"""Monta o vídeo de uma história a partir do projeto.json: planos no ritmo do áudio, parallax suave pela
profundidade, zoom lento, transição suave, trechos com boca falando, legenda karaokê com cor por
personagem, título, trilha e efeitos. Estilo contido (o aprovado na oração a São Alex). Roda no .venv_omni.

    F:\\Projeto IA\\.venv_omni\\Scripts\\python.exe montar.py PASTA_DO_PROJETO [--rascunho]

projeto.json (caminhos relativos à pasta do projeto):
{
  "titulo": "Chapeuzinho Vermelho",
  "formato": [1080, 1920], "fps": 30,                      # 9:16 = TikTok/Shorts; [1920, 1080] = horizontal
  "audio": "audio.wav", "linha_do_tempo": "linha_do_tempo.json",   # saída do alinhar.py
  "legenda": {"cores": {"narra": "FFFFFF", "lobo": "7FB2FF"}, "fonte": "Fredoka Legenda", "tamanho": 74},
  "planos": [
    {"id": "p01", "inicio": 0.0, "imagem": "planos/p01.png",
     "falas": [{"video": "falando/p09_lobo1.mp4", "inicio": 47.82}]}   # opcional: trechos com boca falando
  ],                                                        # cada plano vai até o início do seguinte
  "musica": {"arquivo": "trilha.mp3", "volume_db": -26},    # opcional
  "efeitos": [{"arquivo": "porta.wav", "t": 77.4, "volume_db": -10}],   # opcional
  "saida": "video.mp4"
}
--rascunho: 540 px de largura e sem parallax (rápido, para conferir cortes e legendas).
"""
import argparse, json, math, os, subprocess, sys
from pathlib import Path

os.environ.setdefault("HF_HOME", r"F:\Projeto IA\cache\huggingface")

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageFilter

XF = 0.45                       # duração da transição entre planos (s)
DEV = "cuda" if torch.cuda.is_available() else "cpu"


def ts(t):
    t = max(t, 0)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def cor_ass(hexrgb):
    r, g, b = hexrgb[0:2], hexrgb[2:4], hexrgb[4:6]
    return f"&H00{b}{g}{r}".upper()


def linhas_legenda(palavras, max_chars):
    """Quebra as palavras de uma fala em linhas curtas (legenda de celular)."""
    grupos, atual = [], []
    for w in palavras:
        if atual and len(" ".join(x["w"] for x in atual + [w])) > max_chars:
            grupos.append(atual); atual = []
        atual.append(w)
        if w["w"][-1:] in ".!?" and len(" ".join(x["w"] for x in atual)) > max_chars * 0.5:
            grupos.append(atual); atual = []
    if atual:
        grupos.append(atual)
    return grupos


def escrever_ass(proj, linha, W, H, caminho):
    leg = proj.get("legenda", {})
    esc = min(W, H) / 1080                                   # tamanhos pensados para 1080 px; o rascunho escala
    fonte, tam = leg.get("fonte", "Fredoka Legenda"), int(leg.get("tamanho", 74 if H > W else 58) * esc)
    cores = leg.get("cores", {})
    vertical = H > W
    # celular: a legenda fica acima da faixa de baixo (descrição/botões ocupam ~25%) e longe dos botões da direita
    margem_v = int(leg.get("margem_inferior", 0.30 * H if vertical else 64))
    margem_l, margem_r = (int(70 * esc), int(150 * esc)) if vertical else (int(80 * esc), int(80 * esc))
    max_chars = int(leg.get("max_caracteres", 22 if vertical else 40))
    quem_todos = sorted({f["quem"] for f in linha["falas"]})
    magico = leg.get("tema") == "magico"
    ouro, roxo = cor_ass(leg.get("cor_brilho", "FFD95A")), cor_ass(leg.get("cor_contorno", "3B1A5E"))
    estilos = []
    for q in quem_todos:
        c = cor_ass(cores.get(q, "FFE27A"))
        if magico:
            # tema mágico/lúdico: letra branca que "acende" em dourado ao ser dita, contorno roxo, e atrás um
            # halo desfocado na cor do personagem (a cor continua dizendo quem fala)
            estilos.append(f"Style: {q},{fonte},{tam},{ouro},&H00FFFFFF,{roxo},&H783B1A5E,-1,0,0,0,100,100,1,0,1,"
                           f"{6 * esc:.1f},{3.5 * esc:.1f},2,{margem_l},{margem_r},{margem_v},1")
            estilos.append(f"Style: {q}_halo,{fonte},{tam},{c},{c},{c},&H00000000,-1,0,0,0,100,100,1,0,1,"
                           f"{16 * esc:.1f},0,2,{margem_l},{margem_r},{margem_v},1")
        else:
            estilos.append(f"Style: {q},{fonte},{tam},{c},&H00FFFFFF,&H00201010,&H96000000,-1,0,0,0,100,100,1,0,1,{6 * esc:.1f},{3 * esc:.1f},2,"
                           f"{margem_l},{margem_r},{margem_v},1")
    if magico:
        estilos.append(f"Style: Titulo,{fonte},{int(tam * 1.4)},{ouro},{ouro},{roxo},&H783B1A5E,-1,0,0,0,"
                       f"100,100,2,0,1,{7 * esc:.1f},{4 * esc:.1f},8,60,60,{int(0.12 * H)},1")
        estilos.append(f"Style: Titulo_halo,{fonte},{int(tam * 1.4)},&H00FFB3E6,&H00FFB3E6,&H00FFB3E6,&H00000000,"
                       f"-1,0,0,0,100,100,2,0,1,{18 * esc:.1f},0,8,60,60,{int(0.12 * H)},1")
    else:
        estilos.append(f"Style: Titulo,{fonte},{int(tam * 1.35)},&H00FFFFFF,&H00FFFFFF,&H00201010,&H96000000,-1,0,0,0,"
                       f"100,100,2,0,1,{8 * esc:.1f},{4 * esc:.1f},8,60,60,{int(0.12 * H)},1")
    cab = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{chr(10).join(estilos)}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    # entrada com "pulinho" contido: cresce de 88% até 104% e assenta em 100% (sem pulsar depois)
    pulo = "\\fscx88\\fscy88\\t(0,200,\\fscx104\\fscy104)\\t(200,340,\\fscx100\\fscy100)"
    estrela = "{\\c" + ouro + "\\3c" + roxo + "}✦{\\r}"
    if proj.get("titulo"):
        t0, t1 = ts(0.2), ts(float(proj.get("titulo_duracao", 3.2)))
        if magico:
            ev.append(f"Dialogue: 0,{t0},{t1},Titulo_halo,,0,0,0,,{{\\fad(400,500)\\blur{12 * esc:.0f}\\alpha&H80&{pulo}}}"
                      f"✦ {proj['titulo']} ✦")
            ev.append(f"Dialogue: 1,{t0},{t1},Titulo,,0,0,0,,{{\\fad(400,500){pulo}}}{estrela} {proj['titulo']} {estrela}")
        else:
            ev.append(f"Dialogue: 1,{t0},{t1},Titulo,,0,0,0,,{{\\fad(300,400)}}{proj['titulo']}")
    grupos = [(f["quem"], g) for f in linha["falas"] for g in linhas_legenda(f["palavras"], max_chars)]
    for k, (quem, g) in enumerate(grupos):
        ini, fim = g[0]["t0"] - 0.10, g[-1]["t1"] + 0.30
        if k + 1 < len(grupos):
            fim = min(fim, grupos[k + 1][1][0]["t0"] - 0.12)
        partes = [f"{{\\k{round((g[0]['t0'] - ini) * 100)}}}"]
        for j, w in enumerate(g):
            d = (g[j + 1]["t0"] if j + 1 < len(g) else w["t1"]) - w["t0"]
            partes.append(f"{{\\kf{max(1, round(d * 100))}}}{w['w']} ")
        if magico:
            texto = " ".join(w["w"] for w in g)
            ev.append(f"Dialogue: 0,{ts(ini)},{ts(fim)},{quem}_halo,,0,0,0,,"
                      f"{{\\fad(150,150)\\blur{10 * esc:.0f}\\alpha&H58&{pulo}}}✦ {texto} ✦")
            ev.append(f"Dialogue: 1,{ts(ini)},{ts(fim)},{quem},,0,0,0,,{{\\fad(150,150){pulo}}}{estrela} "
                      + "".join(partes).rstrip() + f" {estrela}")
        else:
            ev.append(f"Dialogue: 0,{ts(ini)},{ts(fim)},{quem},,0,0,0,,{{\\fad(90,120)}}" + "".join(partes).rstrip())
    Path(caminho).write_text(cab + "\n".join(ev) + "\n", encoding="utf-8")


def ler_video(caminho, w, h, fps):
    cmd = ["ffmpeg", "-v", "error", "-i", str(caminho), "-vf", f"fps={fps},scale={w}:{h}:flags=lanczos",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3)


def mixar_audio(proj, pasta, dur, destino):
    """Voz + trilha (em loop, baixinha) + efeitos no tempo certo; normaliza para -14 LUFS (TikTok/YouTube)."""
    entradas, filtros, rotulos = ["-i", str(pasta / proj["audio"])], [], ["[0:a]"]
    k = 1
    if proj.get("musica"):
        m = proj["musica"]
        entradas += ["-stream_loop", "-1", "-i", str(pasta / m["arquivo"])]
        filtros.append(f"[{k}:a]volume={m.get('volume_db', -26)}dB,atrim=0:{dur:.3f},afade=t=in:d=1.5,"
                       f"afade=t=out:st={max(dur - 2.5, 0):.3f}:d=2.5[m{k}]")
        rotulos.append(f"[m{k}]"); k += 1
    for e in proj.get("efeitos", []):
        entradas += ["-i", str(pasta / e["arquivo"])]
        ms = int(float(e["t"]) * 1000)
        filtros.append(f"[{k}:a]volume={e.get('volume_db', -10)}dB,adelay={ms}|{ms}[e{k}]")
        rotulos.append(f"[e{k}]"); k += 1
    mix = (f"{''.join(rotulos)}amix=inputs={len(rotulos)}:normalize=0:duration=first," if len(rotulos) > 1
           else "[0:a]")
    filtros.append(f"{mix}loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]")
    subprocess.run(["ffmpeg", "-y", "-v", "error", *entradas, "-filter_complex", ";".join(filtros), "-map", "[a]",
                    "-ac", "2", "-c:a", "pcm_s16le", str(destino)], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pasta"); ap.add_argument("--rascunho", action="store_true")
    a = ap.parse_args()
    pasta = Path(a.pasta).resolve()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import projeto as P
    proj = P.carregar(pasta)                        # resolve elenco, estilo, música e o início de cada plano
    linha = json.loads((pasta / proj["linha_do_tempo"]).read_text(encoding="utf-8"))
    W, H = proj.get("formato", [1080, 1920])
    FPS = int(proj.get("fps", 30))
    if a.rascunho:
        W, H, FPS = 540, int(540 * H / W) // 2 * 2, 15
    dur = float(linha["duracao"])
    n = int(dur * FPS)
    saida = pasta / (proj.get("saida", "video.mp4") if not a.rascunho else "rascunho.mp4")

    # fontes da legenda: as do motor (Fredoka Legenda, OFL) são copiadas para a pasta do projeto
    import shutil
    (pasta / "fontes").mkdir(exist_ok=True)
    for f in (Path(__file__).parent / "fontes").glob("*.ttf"):
        if not (pasta / "fontes" / f.name).exists():
            shutil.copy2(f, pasta / "fontes" / f.name)
    ass = pasta / "legenda.ass"
    escrever_ass(proj, linha, W, H, ass)
    audio_mix = pasta / "_audio_mix.wav"
    mixar_audio(proj, pasta, dur, audio_mix)

    prof = None
    if not a.rascunho:
        from transformers import pipeline
        prof = pipeline("depth-estimation", model="depth-anything/Depth-Anything-V2-Small-hf",
                        device=0 if DEV == "cuda" else -1)
    ys = torch.linspace(-1, 1, H, device=DEV); xs = torch.linspace(-1, 1, W, device=DEV)
    gy, gx = torch.meshgrid(ys, xs, indexing="ij")
    planos = sorted(proj["planos"], key=lambda p: p["inicio"])
    cenas = []
    for i, p in enumerate(planos):
        img = Image.open(pasta / p["imagem"]).convert("RGB")
        w0, h0 = img.size
        a_src, a_out = w0 / h0, W / H
        sx, sy = (a_out / a_src, 1.0) if a_src > a_out else (1.0, a_src / a_out)   # "cover": preenche sem faixas
        base = torch.stack([gx * sx, gy * sy], -1).unsqueeze(0)
        if prof is not None:
            d = prof(img)["depth"].convert("L").resize((w0, h0), Image.BICUBIC).filter(ImageFilter.GaussianBlur(4))
            D = torch.from_numpy(np.asarray(d, np.float32) / 255).to(DEV)[None, None]
            D = (D - D.min()) / (D.max() - D.min() + 1e-6)
            D_out = F.grid_sample(D, base, mode="bilinear", align_corners=True)[0, 0]
        else:
            D_out = torch.zeros(H, W, device=DEV)
        falas = [dict(inicio=float(f["inicio"]), quadros=ler_video(pasta / f["video"], w0, h0, FPS))
                 for f in p.get("falas", [])]
        fim = planos[i + 1]["inicio"] if i + 1 < len(planos) else dur
        cenas.append(dict(id=p["id"], t0=float(p["inicio"]), t1=float(fim), base=base, D=D_out, falas=falas,
                          zoom=p.get("zoom", "in"),
                          img=torch.from_numpy(np.asarray(img, np.float32) / 255).permute(2, 0, 1)[None].to(DEV),
                          fase=i * 1.7))
        print(f"{p['id']}: {p['inicio']:6.2f}s  {len(falas)} trecho(s) falando", flush=True)
    if prof is not None:
        del prof; torch.cuda.empty_cache()

    AMP = 0.0 if a.rascunho else 14 / (W / 2)
    ff = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-i", "-", "-i", str(audio_mix), "-vf", f"ass={ass.name}:fontsdir=fontes",
                           "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
                           "-c:a", "aac", "-b:a", "192k", "-t", f"{dur:.3f}", "-movflags", "+faststart",
                           str(saida)], stdin=subprocess.PIPE, cwd=pasta)

    def render(c, t):
        rel = t - c["t0"]
        src = c["img"]
        for f in c["falas"]:
            k = int((t - f["inicio"]) * FPS)
            if 0 <= k < len(f["quadros"]):
                src = torch.from_numpy(f["quadros"][k].astype(np.float32) / 255).permute(2, 0, 1)[None].to(DEV)
                break
        span = c["t1"] - c["t0"] + XF
        prog = min(max((rel + XF / 2) / span, 0), 1)
        z = 1.0 + 0.05 * (prog if c["zoom"] == "in" else 1 - prog)       # zoom lento dentro do plano
        dx = AMP * math.sin(2 * math.pi * t / 11.0 + c["fase"])
        dy = AMP * 0.55 * math.sin(2 * math.pi * t / 15.0 + c["fase"] + 0.8)
        g = c["base"] / z
        g = g + torch.stack([dx * (c["D"] - 0.35), dy * (c["D"] - 0.35)], -1)[None]
        return F.grid_sample(src, g, mode="bicubic", padding_mode="border", align_corners=True)

    print(f"renderizando {n} quadros ({W}x{H}, {FPS} fps)...", flush=True)
    with torch.no_grad():
        for f in range(n):
            t = f / FPS
            ativos = [c for c in cenas if c["t0"] - XF / 2 <= t < c["t1"] + XF / 2]
            if len(ativos) >= 2:
                a_ = (t - (ativos[1]["t0"] - XF / 2)) / XF
                q = render(ativos[0], t) * (1 - a_) + render(ativos[1], t) * a_
            else:
                q = render(ativos[0], t)
            fade = min(1.0, t / 0.5, (dur - t) / 1.0)
            q = q.clamp(0, 1) * max(fade, 0) * 255
            ff.stdin.write(q[0].permute(1, 2, 0).to(torch.uint8).cpu().numpy().tobytes())
            if f % 600 == 0:
                print(f"  {f}/{n}", flush=True)
    ff.stdin.close(); ff.wait()
    audio_mix.unlink(missing_ok=True)
    # créditos para a descrição do vídeo (música com licença que exige crédito, fonte, aviso de IA)
    cred = [f"{proj.get('titulo', '')}", ""]
    if proj.get("musica", {}).get("credito"):
        cred.append(f"Música: {proj['musica']['credito']}")
    cred += ["Fonte das legendas: Fredoka (SIL Open Font License)",
             "Imagens e vozes geradas com inteligência artificial."]
    (pasta / "creditos.txt").write_text("\n".join(cred) + "\n", encoding="utf-8")
    print("pronto:", saida)


if __name__ == "__main__":
    main()
