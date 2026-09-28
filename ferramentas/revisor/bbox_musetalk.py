"""Caixa do rosto no formato do MuseTalk, calculada com os 203 pontos do LivePortrait
(substitui o pré-processamento do MuseTalk, que depende do mmpose/mmcv — difícil no Windows).

Regra do MuseTalk (preprocessing.get_landmark_and_bbox): x de ponta a ponta do contorno do rosto,
y2 = queixo, y1 = meio do nariz menos a distância meio-do-nariz→queixo.

    python bbox_musetalk.py ENTRADA(.png|.mp4) SAIDA.pkl
"""
import os, pickle, subprocess, sys, json
from pathlib import Path

JOY = Path(r"F:\Projeto IA\ferramentas\JoyVASA")
sys.path.insert(0, str(JOY)); os.chdir(JOY)
import numpy as np
from PIL import Image
from src.config.crop_config import CropConfig
from src.utils.cropper import Cropper

CONTORNO = list(range(108, 145))     # contorno do rosto (têmpora → queixo → têmpora)
NARIZ_TOPO, NARIZ_PONTA = 199, 202


def quadros_de(caminho):
    p = Path(caminho)
    if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
        return np.asarray(Image.open(p).convert("RGB"))[None]
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-of", "json", str(p)], capture_output=True, text=True)
    s = json.loads(r.stdout)["streams"][0]
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, s["height"], s["width"], 3)


def caixa(l, h):
    x1, x2 = int(l[CONTORNO, 0].min()), int(l[CONTORNO, 0].max())
    y2 = int(l[CONTORNO, 1].max())
    meio = l[NARIZ_TOPO, 1] + (l[NARIZ_PONTA, 1] - l[NARIZ_TOPO, 1]) * 0.66
    y1 = int(max(0, meio - (y2 - meio)))
    return (max(x1, 0), y1, x2, min(y2, h))


def main():
    q = quadros_de(sys.argv[1])
    c = Cropper(crop_cfg=CropConfig(), image_type="human_face")
    f = c.face_analysis_wrapper.get(np.ascontiguousarray(q[0][..., ::-1]), flag_do_landmark_2d_106=True,
                                    direction="large-small")
    if not f:
        raise SystemExit("nenhum rosto detectado")
    lmk = f[0].landmark_2d_106
    caixas = []
    for fr in q:
        lmk = c.human_landmark_runner.run(fr, lmk)
        caixas.append(caixa(lmk, fr.shape[0]))
    with open(sys.argv[2], "wb") as fh:
        pickle.dump(caixas, fh)
    x1, y1, x2, y2 = caixas[0]
    print(f"{len(caixas)} quadros; 1ª caixa {caixas[0]} ({x2 - x1}x{y2 - y1}px)")


if __name__ == "__main__":
    main()
