"""Sincronia labial pelo SyncNet (Chung & Zisserman, Oxford) — métricas padrão da literatura:
  LSE-C (confiança, maior = melhor; vídeos reais bem sincronizados ficam ~6-8, ruins < 3)
  LSE-D (distância mínima, menor = melhor; bons ~6-8, ruins > 9)
  offset (quadros a 25 fps; >0 = áudio adiantado em relação à boca)

O recorte do rosto imita o run_pipeline.py oficial (bs = metade do lado do rosto, cs = 0,4, 224x224),
mas usa os 203 pontos do LivePortrait em vez do detector S3FD.
"""
import sys
from pathlib import Path

import numpy as np
import cv2
import torch
import python_speech_features

SYNC = Path(r"F:\Projeto IA\ferramentas\syncnet")
sys.path.insert(0, str(SYNC))
from SyncNetModel import S   # noqa: E402

_modelo = None


def modelo(dev):
    global _modelo
    if _modelo is None:
        m = S(num_layers_in_fc_layers=1024).to(dev).eval()
        est = torch.load(SYNC / "data" / "syncnet_v2.model", map_location="cpu", weights_only=True)
        sd = m.state_dict()
        for k, v in est.items():
            sd[k].copy_(v)
        _modelo = m
    return _modelo


def recortar(quadros, L, cs=0.4, tam=224):
    """Recorte do rosto por quadro, suavizado no tempo, no estilo do pipeline oficial (saída BGR)."""
    x0, y0 = L[:, :, 0].min(1), L[:, :, 1].min(1)
    x1, y1 = L[:, :, 0].max(1), L[:, :, 1].max(1)
    k = np.ones(9) / 9
    liso = lambda v: np.convolve(np.pad(v, (4, 4), mode="edge"), k, mode="valid")
    cx, cy = liso((x0 + x1) / 2), liso((y0 + y1) / 2)
    bs = liso(np.maximum(x1 - x0, y1 - y0) / 2)
    out = []
    for q, mx, my, b in zip(quadros, cx, cy, bs):
        bsi = int(b * (1 + 2 * cs))
        pad = np.pad(q[..., ::-1], ((bsi, bsi), (bsi, bsi), (0, 0)), constant_values=110)
        my_, mx_ = my + bsi, mx + bsi
        face = pad[int(my_ - b):int(my_ + b * (1 + 2 * cs)), int(mx_ - b * (1 + cs)):int(mx_ + b * (1 + cs))]
        out.append(cv2.resize(face, (tam, tam)))
    return np.stack(out)


def medir(quadros, L, fps, audio16k, vshift=15, dev=None, deslocar_s=0.0):
    dev = dev or ("cuda" if torch.cuda.is_available() else "cpu")
    if abs(fps - 25) > 0.01:                                   # SyncNet exige 25 fps
        idx = np.round(np.arange(0, len(quadros) / fps, 1 / 25) * fps).astype(int)
        idx = idx[idx < len(quadros)]
        quadros, L = quadros[idx], L[idx]
    if deslocar_s:                                             # controle negativo: áudio fora de sincronia
        n = int(abs(deslocar_s) * 16000)
        audio16k = np.concatenate([np.zeros(n, np.float32), audio16k])[:len(audio16k)] if deslocar_s > 0 \
            else np.concatenate([audio16k[n:], np.zeros(n, np.float32)])
    faces = recortar(quadros, L)
    im = torch.from_numpy(faces.transpose(3, 0, 1, 2)[None].astype(np.float32))   # 1,3,T,224,224
    a16 = (np.clip(audio16k, -1, 1) * 32767).astype(np.int16)
    mfcc = python_speech_features.mfcc(a16, 16000).T                              # 13, T*100
    cc = torch.from_numpy(mfcc[None, None].astype(np.float32))
    n = min(len(faces), mfcc.shape[1] // 4) - 5
    m = modelo(dev)
    fi, fa = [], []
    with torch.no_grad():
        for i in range(0, n, 20):
            fr = range(i, min(n, i + 20))
            fi.append(m.forward_lip(torch.cat([im[:, :, v:v + 5] for v in fr]).to(dev)).cpu())
            fa.append(m.forward_aud(torch.cat([cc[:, :, :, v * 4:v * 4 + 20] for v in fr]).to(dev)).cpu())
    fi, fa = torch.cat(fi), torch.cat(fa)
    fap = torch.nn.functional.pad(fa, (0, 0, vshift, vshift))
    win = 2 * vshift + 1
    dists = torch.stack([torch.nn.functional.pairwise_distance(fi[[i]].repeat(win, 1), fap[i:i + win])
                         for i in range(len(fi))], 1)
    mdist = dists.mean(1)
    minval, minidx = torch.min(mdist, 0)
    return {
        "lse_c": round(float(torch.median(mdist) - minval), 3),
        "lse_d": round(float(minval), 3),
        "offset_quadros": int(vshift - minidx),
        "offset_ms": int((vshift - minidx) * 40),
        "curva_distancia": [round(float(x), 3) for x in mdist],
    }, faces
