"""Recorta um close quadrado-ish em volta do rosto e amplia (para o rosto ficar grande o bastante para animar).

    python close_rosto.py ENTRADA.png SAIDA.png [fator_de_enquadramento=3.0]
"""
import os, sys
from pathlib import Path

JOY = Path(r"F:\Projeto IA\ferramentas\JoyVASA")
sys.path.insert(0, str(JOY)); os.chdir(JOY)
import numpy as np
from PIL import Image
from src.config.crop_config import CropConfig
from src.utils.cropper import Cropper

ent, sai = sys.argv[1], sys.argv[2]
fator = float(sys.argv[3]) if len(sys.argv) > 3 else 3.0
img = Image.open(ent).convert("RGB"); a = np.asarray(img)
c = Cropper(crop_cfg=CropConfig(), image_type="human_face")
f = c.face_analysis_wrapper.get(np.ascontiguousarray(a[..., ::-1]), flag_do_landmark_2d_106=True, direction="large-small")
L = f[0].landmark_2d_106
x0, y0 = L.min(0); x1, y1 = L.max(0)
cx, cy, lado = (x0 + x1) / 2, (y0 + y1) / 2 + (y1 - y0) * 0.35, max(x1 - x0, y1 - y0)
wc, hc = lado * fator * 16 / 9, lado * fator            # enquadramento 16:9, rosto no terço de cima
bx0 = int(np.clip(cx - wc / 2, 0, img.width - wc)); by0 = int(np.clip(cy - hc / 2, 0, img.height - hc))
crop = img.crop((bx0, by0, int(bx0 + wc), int(by0 + hc)))
crop.resize((1024, round(1024 * crop.height / crop.width)), Image.LANCZOS).save(sai)
print(f"rosto {x1 - x0:.0f}px -> close {crop.size} ampliado para 1024 (rosto ~{(x1 - x0) * 1024 / crop.width:.0f}px)")
