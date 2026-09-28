"""Desenha os 203 pontos faciais numerados sobre um quadro — para conferir os índices da boca."""
import os, subprocess, sys
from pathlib import Path

JOY = Path(r"F:\Projeto IA\ferramentas\JoyVASA")
sys.path.insert(0, str(JOY)); os.chdir(JOY)
import numpy as np
from PIL import Image, ImageDraw
from src.config.crop_config import CropConfig
from src.utils.cropper import Cropper

img = np.asarray(Image.open(sys.argv[1]).convert("RGB"))
c = Cropper(crop_cfg=CropConfig(), image_type="human_face")
f = c.face_analysis_wrapper.get(np.ascontiguousarray(img[..., ::-1]), flag_do_landmark_2d_106=True, direction="large-small")
L = c.human_landmark_runner.run(img, f[0].landmark_2d_106)
x0, y0 = L.min(0) - 30; x1, y1 = L.max(0) + 30
cr = Image.fromarray(img).crop((int(x0), int(y0), int(x1), int(y1)))
esc = 1400 / cr.width
cr = cr.resize((1400, int(cr.height * esc)), Image.LANCZOS)
dr = ImageDraw.Draw(cr)
for i, (x, y) in enumerate(L):
    px, py = (x - x0) * esc, (y - y0) * esc
    cor = (255, 40, 40) if i % 2 else (40, 90, 255)
    dr.ellipse((px - 3, py - 3, px + 3, py + 3), fill=cor)
    dr.text((px + 4, py - 6), str(i), fill=cor)
cr.save(sys.argv[2])
print(L.shape)
