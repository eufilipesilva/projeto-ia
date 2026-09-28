"""Motor da boca: move a boca (e, opcionalmente, a cabeça) de UMA imagem, no traço dela, com o LivePortrait.

Usado por falar.py. Roda no venv do JoyVASA, que traz o LivePortrait.
"""
import os, sys
from pathlib import Path

JOY = Path(r"F:\Projeto IA\ferramentas\JoyVASA")
sys.path.insert(0, str(JOY)); os.chdir(JOY)   # os caminhos dos pesos no config são relativos ao repositório

import pathlib
pathlib.PosixPath = pathlib.WindowsPath       # o checkpoint do JoyVASA foi salvo no Linux
import numpy as np
import cv2
import torch

from src.config.crop_config import CropConfig
from src.config.inference_config import InferenceConfig
from src.utils.cropper import Cropper
from src.utils.crop import prepare_paste_back, paste_back
from src.live_portrait_wmg_wrapper import LivePortraitWrapper

CONTORNO = list(range(108, 145))            # contorno do rosto nos 203 pontos
NARIZ_PONTA = 202
LAB_SUP, LAB_INF, CANTO_E, CANTO_D = 90, 102, 48, 66
ESTREITAR = (14, 1, +1)                     # ponto de expressão, eixo (y), sinal que estreita a boca sem abrir
                                            # (achado por busca medida; igual nas cenas o01z e o06)

# formatos de boca (nomes do Rhubarb): abertura = lábio sup→inf ÷ largura da boca; estreita 0..1
FORMATOS = {
    "X": dict(abre=0.00),                   # repouso / pausa
    "A": dict(abre=0.00),                   # M, B, P: lábios fechados
    "B": dict(abre=0.10),                   # maioria das consoantes, I: dentes quase juntos
    "C": dict(abre=0.26),                   # É, E: aberta média
    "D": dict(abre=0.45),                   # Á: bem aberta
    "E": dict(abre=0.20, estreita=0.5),     # Ó: arredondada
    "F": dict(abre=0.08, estreita=1.0),     # U, W: biquinho
    "G": dict(abre=0.05),                   # F, V: dente no lábio
    "H": dict(abre=0.22),                   # L
}


def ler_rgb(p):
    """Lê imagem (aceita caminho com acento, ao contrário do cv2.imread) cortada para lados pares."""
    img = cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)[..., ::-1]
    return np.ascontiguousarray(img[: img.shape[0] // 2 * 2, : img.shape[1] // 2 * 2])


def gravar_rgb(p, img):
    cv2.imencode(Path(p).suffix, np.ascontiguousarray(img[..., ::-1]))[1].tofile(str(p))


class Boca:
    """Rosto de uma imagem pronto para ser redesenhado com outra abertura de boca e outra pose."""

    def __init__(self, img_rgb):
        self.cropper = Cropper(crop_cfg=CropConfig(), image_type="human_face")
        self.lp = LivePortraitWrapper(inference_cfg=InferenceConfig())
        self.img = img_rgb
        self.crop = self.cropper.crop_source_image(img_rgb, self.cropper.crop_cfg)
        if self.crop is None:
            raise SystemExit("nenhum rosto detectado na imagem")
        I_s = self.lp.prepare_source(self.crop["img_crop_256x256"])
        self.info = self.lp.get_kp_info(I_s)
        self.f_s = self.lp.extract_feature_3d(I_s)
        self.x_s = self.lp.transform_keypoint(self.info)
        self.mask_colar = prepare_paste_back(self.lp.inference_cfg.mask_crop, self.crop["M_c2o"],
                                             dsize=(img_rgb.shape[1], img_rgb.shape[0]))
        self.lmk0 = self.pontos(img_rgb)
        self.calibrar()

    # ------------------------------------------------------------ medidas
    def pontos(self, img):
        """Os 203 pontos do rosto na imagem inteira."""
        f = self.cropper.face_analysis_wrapper.get(np.ascontiguousarray(img[..., ::-1]),
                                                   flag_do_landmark_2d_106=True, direction="large-small")
        return self.cropper.human_landmark_runner.run(img, f[0].landmark_2d_106)

    @staticmethod
    def abertura(l):
        return float(np.linalg.norm(l[LAB_SUP] - l[LAB_INF]) / np.linalg.norm(l[CANTO_E] - l[CANTO_D]))

    @staticmethod
    def largura(l):
        return float(np.linalg.norm(l[CANTO_E] - l[CANTO_D]))

    def calibrar(self):
        """O módulo do LivePortrait recebe uma abertura "pedida"; mede-se a abertura que ele realmente
        desenha neste rosto, para depois pedir o valor certo para cada formato."""
        self.pedidas = np.round(np.arange(0.0, 0.81, 0.1), 2)
        medidas = [self.abertura(self.pontos(self._render(float(p)))) for p in self.pedidas]
        self.medidas = np.maximum.accumulate(np.array(medidas))

    # ------------------------------------------------------------ desenho
    @torch.no_grad()
    def _render(self, pedida, estreita=0.0, pose=None):
        if pose is not None:                  # pose = (dpitch, dyaw, droll) em graus, somada à original
            info = dict(self.info)
            for k, d in zip(("pitch", "yaw", "roll"), pose):
                info[k] = self.info[k] + d
            x_d = self.lp.transform_keypoint(info)
        else:
            x_d = self.x_s.clone()
        if estreita > 1e-3:
            d = torch.zeros_like(self.info["exp"]).reshape(1, 21, 3)
            ponto, eixo, sinal = ESTREITAR
            d[0, ponto, eixo] = 0.03 * sinal * estreita
            x_d = x_d + self.info["scale"] * d     # soma no espaço da expressão (antes da escala)
        r = self.lp.calc_combined_lip_ratio([pedida], self.crop["lmk_crop"])
        x_d = x_d + self.lp.retarget_lip(self.x_s, r)
        x_d = self.lp.stitching(self.x_s, x_d)
        out = self.lp.parse_output(self.lp.warp_decode(self.f_s, self.x_s, x_d)["out"])[0]
        return paste_back(out, self.crop["M_c2o"], self.img, self.mask_colar)

    def quadro(self, abre, estreita=0.0, pose=None):
        """Imagem inteira com a boca na abertura-alvo (medida nos pontos) e a pose pedida."""
        pedida = float(np.interp(abre, self.medidas, self.pedidas)) if abre > self.medidas[0] else 0.0
        return self._render(pedida, estreita, pose)

    def mascara_boca(self):
        """Região do nariz para baixo, dentro do contorno do rosto, dilatada e com borda suave. Com a
        cabeça parada, só essa região é colada: olhos, cabelo e cenário ficam idênticos ao original."""
        h, w = self.img.shape[:2]
        l, larg = self.lmk0, self.largura(self.lmk0)
        y_nariz = l[NARIZ_PONTA, 1] + 0.15 * larg
        baixo = l[CONTORNO][l[CONTORNO][:, 1] > y_nariz]
        cx = (l[CANTO_E, 0] + l[CANTO_D, 0]) / 2
        topo = np.array([[cx - 1.1 * larg, y_nariz], [cx + 1.1 * larg, y_nariz]])
        m = np.zeros((h, w), np.float32)
        cv2.fillConvexPoly(m, cv2.convexHull(np.concatenate([topo, baixo]).astype(np.float32)).astype(np.int32), 1.0)
        k = max(3, int(0.25 * larg) | 1)
        m = cv2.dilate(m, np.ones((k, k), np.uint8))
        return cv2.GaussianBlur(m, (0, 0), 0.18 * larg)[..., None]

    def folha(self, caminho):
        """Folha de conferência: um recorte da boca em cada formato."""
        l = self.lmk0
        cx, cy, s = int((l[CANTO_E, 0] + l[CANTO_D, 0]) / 2), int(l[LAB_INF, 1]), int(1.4 * self.largura(l))
        recs = []
        for letra, f in FORMATOS.items():
            r = self.quadro(f["abre"], f.get("estreita", 0.0))[max(0, cy - s):cy + s, max(0, cx - s):cx + s]
            r = cv2.resize(np.ascontiguousarray(r), (220, 220))
            cv2.putText(r, letra, (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 0), 2)
            recs.append(r)
        gravar_rgb(caminho, np.concatenate(recs, 1))
