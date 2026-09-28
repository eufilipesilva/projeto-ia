"""Folha de conferência: junta as imagens de uma rodada numa grade, com o nome de cada uma, para conferir
anatomia (mãos, braços, caudas) a olho antes de seguir. Nenhum juiz automático grátis testado pega esses
erros de forma confiável (qwen3-vl 4B/8B, MediaPipe e Gemini 2.5 Flash deixaram passar "dois braços
esquerdos" em 28/09/2026), então essa conferência é a garantia.

    F:\\Projeto IA\\.venv_omni\\Scripts\\python.exe conferencia.py PASTA_OU_IMAGENS... [--saida folha.jpg] [--colunas 4]
"""
import argparse, math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def folha(imagens, saida, colunas=4, largura=420):
    imagens = [Path(p) for p in imagens]
    if not imagens:
        return None
    ims = [Image.open(p).convert("RGB") for p in imagens]
    alt = max(int(largura * im.height / im.width) for im in ims)
    faixa = 34
    linhas = math.ceil(len(ims) / colunas)
    g = Image.new("RGB", (colunas * largura, linhas * (alt + faixa)), (24, 24, 28))
    d = ImageDraw.Draw(g)
    try:
        fonte = ImageFont.truetype("arial.ttf", 20)
    except OSError:
        fonte = ImageFont.load_default()
    for k, (p, im) in enumerate(zip(imagens, ims)):
        x, y = (k % colunas) * largura, (k // colunas) * (alt + faixa)
        im = im.resize((largura, int(largura * im.height / im.width)), Image.LANCZOS)
        g.paste(im, (x, y + faixa))
        d.text((x + 8, y + 6), f"{k + 1}. {p.stem}"[:38], fill=(255, 230, 120), font=fonte)
    saida = Path(saida)
    g.save(saida, quality=90)
    return saida


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("entradas", nargs="+"); ap.add_argument("--saida", default="folha_conferencia.jpg")
    ap.add_argument("--colunas", type=int, default=4)
    a = ap.parse_args()
    imgs = []
    for e in map(Path, a.entradas):
        imgs += sorted(e.glob("*.png")) if e.is_dir() else [e]
    print("folha:", folha(imgs, a.saida, a.colunas))


if __name__ == "__main__":
    main()
