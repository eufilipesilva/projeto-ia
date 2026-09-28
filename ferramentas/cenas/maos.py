"""Detector de erro de mãos/braços em ilustração (complementa o fiscal, cujo juiz de visão não conta membros).

Usa o MediaPipe Hands (Google, grátis, CPU) para achar cada mão e dizer se é ESQUERDA ou DIREITA pelo
formato (lado do polegar). Suspeita quando:
  - aparecem mais mãos do que o esperado (padrão: 2 por personagem);
  - aparecem duas mãos do MESMO lado com confiança (ex.: "dois braços esquerdos" da cena 4 da oração).

Roda no ambiente separado .venv_maos (o MediaPipe briga com as versões do venv do JoyVASA):
    F:\\Projeto IA\\ferramentas\\cenas\\.venv_maos\\Scripts\\python.exe maos.py IMAGEM.png [...] [--esperado 2]
Imprime um JSON por imagem: {"arquivo", "maos": [...], "suspeita": bool, "motivo": "..."}
"""
import argparse, json
from pathlib import Path

import cv2
import numpy as np
import mediapipe as mp

MIN_CONF = 0.3          # mão só conta com essa confiança de detecção
MIN_LADO = 0.80         # e com essa certeza de lado (esquerda/direita)


def ler(p):
    return cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)


def recorte_tronco(img, rosto_det):
    """Recorta do rosto para baixo (cabeça, tronco e braços) e amplia: em cena aberta as mãos são pequenas
    demais para o detector. Sem rosto detectado, usa a imagem inteira."""
    h, w = img.shape[:2]
    r = rosto_det.process(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    if not r.detections:
        return img, (0, 0)
    b = max(r.detections, key=lambda d: d.location_data.relative_bounding_box.width).location_data.relative_bounding_box
    fx, fy, fw, fh = b.xmin * w, b.ymin * h, b.width * w, b.height * h
    x0, x1 = int(max(0, fx + fw / 2 - 3.2 * fw)), int(min(w, fx + fw / 2 + 3.2 * fw))
    y0, y1 = int(max(0, fy - 0.5 * fh)), int(min(h, fy + 6 * fh))
    return img[y0:y1, x0:x1], (x0, y0)


def analisar(caminho, esperado=2, detector=None, rosto_det=None):
    img, (ox, oy) = recorte_tronco(ler(caminho), rosto_det) if rosto_det else (ler(caminho), (0, 0))
    h, w = img.shape[:2]
    esc = 1400 / max(h, w)                                    # mãos pequenas: ampliar ajuda o detector
    img = cv2.resize(img, (int(w * esc), int(h * esc)), interpolation=cv2.INTER_CUBIC)
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    r = detector.process(rgb)
    maos = []
    for lm, lado in zip(r.multi_hand_landmarks or [], r.multi_handedness or []):
        c = lado.classification[0]
        xs = [ox + p.x * w for p in lm.landmark]; ys = [oy + p.y * h for p in lm.landmark]
        maos.append({"lado": "esquerda" if c.label == "Right" else "direita",   # MediaPipe assume imagem espelhada
                     "certeza": round(c.score, 2),
                     "caixa": [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]})
    firmes = [m for m in maos if m["certeza"] >= MIN_LADO]
    motivo = ""
    if len(maos) > esperado:
        motivo = f"{len(maos)} mãos (esperado até {esperado})"
    else:
        for lado in ("esquerda", "direita"):
            n = sum(m["lado"] == lado for m in firmes)
            if n >= 2 and esperado <= 2:
                motivo = f"{n} mãos {lado}s"
    return {"arquivo": Path(caminho).name, "maos": maos, "suspeita": bool(motivo), "motivo": motivo}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("imagens", nargs="+"); ap.add_argument("--esperado", type=int, default=2)
    a = ap.parse_args()
    with mp.solutions.hands.Hands(static_image_mode=True, max_num_hands=6, min_detection_confidence=MIN_CONF,
                                  model_complexity=1) as det,             mp.solutions.face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.3) as rosto:
        for p in a.imagens:
            print(json.dumps(analisar(p, a.esperado, det, rosto), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
