"""Sobrepõe um personagem recortado de um plano aprovado em outro plano (continuidade sem gerar de novo).

Uso típico: um personagem deitado/dormindo que precisa continuar em cena nos planos seguintes. Gerar a cena
inteira com ele faz o modelo misturar personagens (28/09/2026: menina "fundida" no lobo); recortar e colar é
determinístico. Remove o fundo com o rembg (modelo isnet-anime, feito para ilustração) e cola com sombra suave.

Roda no ambiente .venv_maos (rembg):
    F:\\Projeto IA\\ferramentas\\cenas\\.venv_maos\\Scripts\\python.exe sobrepor.py ORIGEM.png x0,y0,x1,y1 DESTINO.png SAIDA.png
        --posicao X,Y [--escala 0.6] [--espelhar]
  x0,y0,x1,y1  região da ORIGEM que contém o personagem (o fundo dessa região é removido)
  --posicao    onde fica o PÉ/base do recorte no destino (centro-baixo), em px do destino
"""
import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageOps

_sessao = None
MODELO_RECORTE = "birefnet-general"   # isnet-anime deixou móveis junto (28/09/2026)


def recortar(origem, caixa):
    global _sessao
    from rembg import new_session, remove
    if _sessao is None:
        _sessao = new_session(MODELO_RECORTE)
    reg = Image.open(origem).convert("RGB").crop(caixa)
    rgba = remove(reg, session=_sessao)                       # RGBA com o fundo transparente
    # só a maior mancha conectada (tira pedaços soltos de móveis que o modelo achou "personagem")
    a = np.asarray(rgba)[..., 3]
    from scipy import ndimage
    rot, n = ndimage.label(a > 128)
    if n > 1:
        maior = 1 + int(np.argmax(ndimage.sum(np.ones_like(rot), rot, range(1, n + 1))))
        a = np.where(rot == maior, a, 0).astype(np.uint8)
        rgba.putalpha(Image.fromarray(a))
    return rgba.crop(rgba.getbbox())


def colar(recorte, destino, pos, escala=1.0, espelhar=False):
    dst = Image.open(destino).convert("RGBA")
    r = ImageOps.mirror(recorte) if espelhar else recorte
    r = r.resize((int(r.width * escala), int(r.height * escala)), Image.LANCZOS)
    # sombra de contato suave no chão
    sombra = Image.new("RGBA", r.size, (60, 40, 30, 0))
    sombra.putalpha(r.getchannel("A").point(lambda v: int(v * 0.35)).filter(ImageFilter.GaussianBlur(6)))
    x, y = int(pos[0] - r.width / 2), int(pos[1] - r.height)
    dst.alpha_composite(sombra, (x + 6, y + 10))
    dst.alpha_composite(r, (x, y))
    return dst.convert("RGB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("origem"); ap.add_argument("caixa"); ap.add_argument("destino"); ap.add_argument("saida")
    ap.add_argument("--posicao", required=True); ap.add_argument("--escala", type=float, default=1.0)
    ap.add_argument("--espelhar", action="store_true")
    a = ap.parse_args()
    rec = recortar(a.origem, [int(v) for v in a.caixa.split(",")])
    out = colar(rec, a.destino, [int(v) for v in a.posicao.split(",")], a.escala, a.espelhar)
    out.save(a.saida)
    rec.save(Path(a.saida).with_name(Path(a.saida).stem + "_recorte.png"))
    print("pronto:", a.saida)


if __name__ == "__main__":
    main()
