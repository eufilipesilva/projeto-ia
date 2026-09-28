"""Faz um personagem desenhado falar: imagem parada + áudio -> vídeo com boca sincronizada e cabeça viva.

    F:\\Projeto IA\\ferramentas\\JoyVASA\\.venv\\Scripts\\python.exe falar.py IMAGEM.png AUDIO.wav SAIDA.mp4
        [--cabeca 1.5] [--suavizar-ms 15] [--adiantar-ms 40] [--fps 25] [--folha]

Como funciona (detalhes no README.md):
  1. fonemas.py ouve a fala e diz qual formato de boca usar em cada instante (funciona em português);
  2. os formatos viram uma curva suave de abertura/arredondamento (a boca desliza entre as sílabas);
  3. boca.py redesenha o rosto em cada quadro com o LivePortrait, no traço da própria imagem.

--cabeca GRAUS  balanço lento e sutil da cabeça, previsível (não reage à voz). 0 = cabeça parada e só a
                região da boca é colada (olhos, cabelo e cenário ficam idênticos ao original).
--suavizar-ms   quanto a boca "desliza" entre fonemas (15 aprovado; mais = mais mole).
--adiantar-ms   mostra a boca um pouco antes do som, como fazem os animadores (40 = 1 quadro).
--folha         grava também SAIDA_bocas.png com os 9 formatos de boca, para conferir o desenho.
--regiao x0,y0,x1,y1  anima só o rosto dentro dessa região (px da imagem): escolhe QUEM fala quando há
                mais de um rosto. Deixe folga em volta da cabeça (a região inteira é redesenhada).
--rosto esquerda|direita|maior  escolhe o rosto automaticamente (detector de rostos) e monta a região.

Também pode ser usado de outro script:  from falar import falar; falar(imagem, audio, saida)
"""
import argparse, subprocess, sys, time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

import numpy as np


def trajetoria(cues, n, fps, adiantar_s, suavizar_ms, formatos):
    """Curvas de abertura e estreitamento por quadro: degraus das marcas, suavizados por uma gaussiana."""
    dt = 0.005
    T = np.arange(0, n / fps + 1.0, dt)
    abre, estr = np.zeros_like(T), np.zeros_like(T)
    for c in cues:
        m = (T >= c["start"]) & (T < c["end"])
        abre[m] = formatos[c["value"]]["abre"]
        estr[m] = formatos[c["value"]].get("estreita", 0.0)
    if suavizar_ms > 0:
        sig = suavizar_ms / 1000 / dt
        k = np.exp(-0.5 * (np.arange(-int(4 * sig), int(4 * sig) + 1) / sig) ** 2); k /= k.sum()
        abre = np.convolve(abre, k, mode="same"); estr = np.convolve(estr, k, mode="same")
    t = np.arange(n) / fps + adiantar_s
    return np.interp(t, T, abre), np.interp(t, T, estr)


def balanco_cabeca(n, fps, graus, semente=7):
    """Pose (pitch, yaw, roll) por quadro: soma de senoides lentas (períodos de 3 a 9 s), começando e
    terminando na pose original. Movimento contínuo e contido, sem picos."""
    rng = np.random.default_rng(semente)
    t = np.arange(n) / fps
    pose = np.zeros((n, 3))
    for eixo, peso in enumerate((0.8, 1.0, 0.6)):          # pitch, yaw, roll
        for _ in range(2):
            per, fase = rng.uniform(3, 9), rng.uniform(0, 2 * np.pi)
            pose[:, eixo] += np.sin(2 * np.pi * t / per + fase)
        pose[:, eixo] *= graus * peso / 2
    pose -= pose[0]                                        # parte da pose original
    rampa = np.clip(np.minimum(t, t[-1] - t) / 0.8, 0, 1)  # entra e sai suave
    return pose * rampa[:, None]


def regiao_do_rosto(img, qual):
    """Região (com folga) em volta de um dos rostos da imagem: o mais à esquerda, à direita ou o maior."""
    import boca as B
    from src.utils.cropper import Cropper
    from src.config.crop_config import CropConfig
    c = Cropper(crop_cfg=CropConfig(), image_type="human_face")
    faces = c.face_analysis_wrapper.get(np.ascontiguousarray(img[..., ::-1]), flag_do_landmark_2d_106=True,
                                        direction="large-small")
    if not faces:
        raise SystemExit("nenhum rosto detectado na imagem")
    chave = {"esquerda": lambda f: f.bbox[0], "direita": lambda f: -f.bbox[0],
             "maior": lambda f: -(f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1])}[qual]
    x0, y0, x1, y1 = sorted(faces, key=chave)[0].bbox
    cx, cy, lado = (x0 + x1) / 2, (y0 + y1) / 2, max(x1 - x0, y1 - y0) * 2.4
    h, w = img.shape[:2]
    return [int(max(0, cx - lado / 2)), int(max(0, cy - lado / 2)), int(min(w, cx + lado / 2)), int(min(h, cy + lado / 2))]


def falar(imagem, audio, saida, cabeca=1.5, suavizar_ms=15, adiantar_ms=40, fps=25, folha=False, regiao=None, rosto=None):
    imagem, audio, saida = (Path(x).resolve() for x in (imagem, audio, saida))
    t0 = time.time()
    import fonemas
    marcas = fonemas.gerar(audio)
    import boca as B                                       # carrega o LivePortrait
    inteira = B.ler_rgb(imagem)
    if rosto and not regiao:
        regiao = regiao_do_rosto(inteira, rosto)
        print(f"rosto {rosto}: região {regiao}")
    if regiao:                                             # anima só o rosto desta região e cola de volta
        x0, y0, x1, y1 = (int(v) for v in regiao)
        x1, y1 = x0 + (x1 - x0) // 2 * 2, y0 + (y1 - y0) // 2 * 2
        img = inteira[y0:y1, x0:x1].copy()
    else:
        img = inteira
    b = B.Boca(img)
    if folha:
        b.folha(saida.with_name(saida.stem + "_bocas.png"))

    n = int(round(marcas["metadata"]["duration"] * fps))
    abre, estr = trajetoria(marcas["mouthCues"], n, fps, adiantar_ms / 1000, suavizar_ms, B.FORMATOS)
    pose = balanco_cabeca(n, fps, cabeca) if cabeca > 0 else None
    mask = b.mascara_boca() if pose is None else None

    h, w = inteira.shape[:2]
    ff = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                           "-r", str(fps), "-i", "-", "-i", str(audio), "-c:v", "libx264", "-crf", "18",
                           "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(saida)], stdin=subprocess.PIPE)
    cache = {}                                             # cabeça parada: quadros iguais se repetem
    for i in range(n):
        if pose is not None:
            q = b.quadro(float(abre[i]), float(estr[i]), tuple(pose[i]))
        else:
            chave = (round(float(abre[i]), 3), round(float(estr[i]), 3))
            if chave not in cache:
                r = b.quadro(*chave)
                cache[chave] = (mask * r + (1 - mask) * img).astype(np.uint8)
            q = cache[chave]
        if regiao:
            quadro = inteira.copy(); quadro[y0:y1, x0:x1] = q; q = quadro
        ff.stdin.write(np.ascontiguousarray(q).tobytes())
    ff.stdin.close(); ff.wait()
    print(f"pronto: {saida} ({n} quadros, {time.time() - t0:.0f} s)")
    return saida


def main():
    ap = argparse.ArgumentParser(description="imagem parada + áudio -> personagem falando")
    ap.add_argument("imagem"); ap.add_argument("audio"); ap.add_argument("saida")
    ap.add_argument("--cabeca", type=float, default=1.5)
    ap.add_argument("--suavizar-ms", type=float, default=15)
    ap.add_argument("--adiantar-ms", type=float, default=40)
    ap.add_argument("--fps", type=int, default=25)
    ap.add_argument("--folha", action="store_true")
    ap.add_argument("--regiao", help="x0,y0,x1,y1: anima só o rosto dentro dessa região")
    ap.add_argument("--rosto", choices=["esquerda", "direita", "maior"], help="escolhe o rosto automaticamente")
    a = ap.parse_args()
    falar(a.imagem, a.audio, a.saida, a.cabeca, a.suavizar_ms, a.adiantar_ms, a.fps, a.folha,
          [int(v) for v in a.regiao.split(",")] if a.regiao else None, a.rosto)


if __name__ == "__main__":
    main()
