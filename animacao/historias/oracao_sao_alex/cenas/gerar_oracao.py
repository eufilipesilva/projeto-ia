"""Gera as cenas da oração a São Alex, uma por trecho, mantendo a personagem.

    python gerar_oracao.py                         gera só as cenas que ainda não existem
    python gerar_oracao.py --refazer o01_invocacao o05_malware o07_amem [--tentativas 4] [--rodadas 2]
    (--motor klein é o padrão: FLUX.2 klein na GPU grátis do Kaggle, em lote; qwen-kaggle e space são alternativas)

Toda cena gerada passa pelo fiscal (ferramentas/cenas/fiscal.py), que compara o rosto com as cenas
APROVADAS e manda gerar de novo se houver traço fantasma ou traço diferente.
"""
import argparse
from pathlib import Path

from gerar_cena import gerar_ate_passar

ALEX = Path(r"C:\Users\Filipe Pereira\Downloads\saoalex.jpeg")
ICONE = ("On the desk, the small framed icon is now the stained-glass saint from image 2 "
         "(man with grey hair, sunglasses, red robe, golden halo, vacuum cleaner). ")
MANTER = "Keep the small framed stained-glass saint icon with sunglasses on the desk exactly as in image 1. "

CENAS = [
    ("o01_invocacao", [ALEX],
     "same bedroom-office at blue hour, she sits at the desk praying with hands together and eyes closed. "
     + ICONE + "Medium shot, the icon clearly visible next to the laptop."),
    ("o02_quinze_dias", [],
     "same room, she looks worried at a paper wall calendar where the next 15 days are circled in red, "
     "including the weekends, one hand on her cheek, laptop open on the desk."),
    ("o03_instabilidade", [],
     "same desk late at night, she holds her head with both hands, stressed, the laptop screen shows red "
     "error alerts and falling server graphs, a digital clock reads FRI 23:47, room lit only by the screen."),
    ("o04_luz", [ALEX],
     "same desk at night, a soft warm golden light shines from the small framed icon on the desk and "
     "illuminates her face and the laptop; she looks at it with a hopeful gentle smile, BOTH hands pressed "
     "together in prayer in front of her chest (exactly two arms, one on each side of her body). " + ICONE),
    ("o05_malware", [],
     "same desk, the laptop screen now shows a big green shield with a check mark and green system graphs, "
     "a dark blue book titled DATAJUD lies on the desk, she smiles relieved, leaning back in the chair."),
    ("o06_tres_vezes", [],
     "close-up of her face, eyes closed, whispering softly, three small glowing golden sparks float in the "
     "air in front of her, dark blue night background of the same room."),
    ("o07_amem", [],
     "same room late at night, she gently closes the laptop and smiles peacefully with eyes closed, the "
     "city lights glow through the window, calm and serene atmosphere."),
]

# cenas aprovadas pelo Filipe: servem de padrão de rosto/traço para o fiscal
# desde 27/09/2026 as cenas são do FLUX.2 klein (traço de quadrinho da referência); o padrão é a cena 1
# nova, aprovada pelo Filipe, mais a própria referência
PADROES = ["o01_invocacao", "00_referencia"]

def pedido(nome, extras, cena, aqui):
    # a cena 1 parte da referência; as outras partem da cena 1 (St. Alex já no porta-retrato da mesa),
    # que só serve de base depois de aprovada pelo fiscal
    base = aqui / ("00_referencia.png" if nome == "o01_invocacao" else "o01_invocacao.png")
    if nome not in ("o01_invocacao", "o06_tres_vezes"):
        cena = MANTER + cena
    return dict(nome=nome, cena=cena, extras=extras, base=base)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--refazer", nargs="*", default=[], help="cenas a gerar de novo mesmo já existindo")
    ap.add_argument("--motor", choices=["klein", "qwen-kaggle", "space"], default="klein",
                    help="klein = FLUX.2 klein no Kaggle, em lote (padrão, 25 s/imagem); qwen-kaggle = Qwen+LoRA anime "
                         "no Kaggle (lento); space = Space do Hugging Face (usa a cota ZeroGPU)")
    ap.add_argument("--tentativas", type=int, default=2, help="versões por cena (por rodada, no kaggle)")
    ap.add_argument("--rodadas", type=int, default=3, help="(kaggle) rodadas para as cenas que não passarem")
    a = ap.parse_args()
    aqui = Path(__file__).parent
    padroes = [aqui / f"{p}.png" for p in PADROES]
    pedidos = []
    for nome, extras, cena in CENAS:
        if (aqui / f"{nome}.png").exists() and nome not in a.refazer:
            print(nome, "já existe"); continue
        pedidos.append(pedido(nome, extras, cena, aqui))

    if a.motor != "space":
        motor = "klein" if a.motor == "klein" else "qwen"
        from gerar_cena import gerar_ate_passar_kaggle
        # a cena 1 vai sozinha primeiro: é a base das outras
        primeira = [p for p in pedidos if p["nome"] == "o01_invocacao"]
        resto = [p for p in pedidos if p["nome"] != "o01_invocacao"]
        if primeira and gerar_ate_passar_kaggle(primeira, padroes, a.tentativas, a.rodadas, motor)["o01_invocacao"] is None:
            print("a cena 1 não passou; as outras dependem dela como base — parando aqui.")
            resto = []
        if resto:
            gerar_ate_passar_kaggle(resto, padroes, a.tentativas, a.rodadas, motor)
    else:
        for p in pedidos:
            print(p["nome"])
            ok = gerar_ate_passar(p["cena"], p["nome"], p["extras"], base=p["base"], padroes=padroes,
                                  tentativas=a.tentativas)
            if ok is None and p["nome"] == "o01_invocacao":
                print("a cena 1 não passou; as outras dependem dela como base — parando aqui.")
                break
