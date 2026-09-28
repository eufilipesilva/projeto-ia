"""Gera o projeto.json da Chapeuzinho a partir do storyboard abaixo e da linha_do_tempo.json (alinhar.py).
Rode de novo sempre que mudar o storyboard: preserva as fichas já escolhidas."""
import json
from pathlib import Path

AQUI = Path(__file__).parent
linha = json.loads((AQUI / "linha_do_tempo.json").read_text(encoding="utf-8"))["falas"]

ESTILO = ("Children's picture book illustration, soft watercolor and colored pencil textures, warm gentle colors, "
          "clean friendly shapes, expressive cute characters, correct anatomy, vertical composition, no text, no letters.")
# fichas geradas a partir de outra ficha já escolhida (continuidade): o lobo disfarçado parte do lobo
REF_FICHA = {"lobo_disf": "fichas/lobo.png"}

PERSONAGENS = {
    "chapeu": ("Little Red Riding Hood, a cheerful 7-year-old girl with rosy cheeks, big brown eyes and short wavy "
               "chestnut hair, wearing a bright red hooded cape over a white blouse and a blue skirt", True),
    "mae": ("the girl's mother, a kind ADULT woman about 30 years old, tall and slender with adult body proportions, "
            "clearly a grown-up much taller than a 7-year-old child, chestnut hair in a low bun, green dress and "
            "cream apron", True),
    "vovo": ("a sweet elderly grandmother with white hair, round glasses, a white lace nightcap and a pink shawl", True),
    "lobo": ("the Big Bad Wolf, a tall anthropomorphic grey wolf standing on two legs, bushy tail, yellow eyes, "
             "sly toothy grin, wearing a patched brown vest, exactly ONE tail", False),
    "lobo_disf": ("the SAME tall grey wolf from the reference image (same face, yellow eyes and sly grin, exactly one "
                  "tail) in disguise, wearing a white lace nightcap, round glasses and a pink flowered nightgown", False),
    "cacador": ("a friendly bearded woodsman with a green hat with a feather, brown jacket and red checkered shirt, "
                "carrying a lantern", True),
}
CENARIOS = {
    "casa": "a charming cottage with a red door and flower boxes at the edge of a village, sunny morning",
    "bosque": "a sunny meadow path full of colorful wildflowers and butterflies",
    "floresta": "a dense green forest with tall trees and a winding dirt path, soft dappled light",
    "casa_vovo": "grandma's small stone cottage in a forest clearing, wooden door, smoke from the chimney",
    "quarto_vovo": "grandma's cozy bedroom with a wooden bed and patchwork quilt, a big wardrobe, lace curtains",
}

# (linha onde o plano começa, id, cenário, personagens, o que acontece, quem o fiscal cobra, falas [(linha, rosto)], mesma imagem de)
S = [
    (0, "p01", "casa", ["chapeu", "mae"], "the girl in her red cape stands happily in front of the cottage next to her mother", "chapeu", [], None),
    (1, "p02", "casa", ["chapeu"], "close-up portrait of the smiling girl wearing her red hooded cape", "chapeu", [], None),
    (2, "p03", "casa", ["mae", "chapeu"], "at the cottage door the mother hands the girl a wicker basket full of sweets", "chapeu", [], None),
    (3, "p04", "casa", ["mae"], "close-up of the mother speaking tenderly, holding the basket", "mae", [(3, None)], None),
    (4, "p05", "casa", ["mae", "chapeu"], "the mother on the left points to a dark forest path and a sunny flowery path, the girl on the right listens", "mae", [(4, "esquerda")], None),
    (5, "p06", "bosque", ["chapeu"], "the girl skips happily along the sunny path, singing, basket on her arm", "chapeu", [], None),
    (6, "p07", "bosque", ["chapeu"], "the girl kneels to pick colorful wildflowers", "chapeu", [], None),
    (7, "p08", "floresta", ["chapeu", "lobo"], "the wolf peeks from behind a big tree while the girl picks flowers, unaware", "chapeu", [], None),
    (8, "p09", "floresta", ["chapeu", "lobo"], "the girl smiles at the polite wolf, not scared at all", "chapeu", [], None),
    (9, "p10", "floresta", ["lobo"], "close-up of the wolf greeting politely with a sly smile, hat in hand", "estilo", [(9, None)], None),
    (10, "p11", "floresta", ["chapeu"], "close-up of the girl answering cheerfully", "chapeu", [(10, None)], None),
    (11, "p12", None, [], "", "estilo", [(11, None)], "p10"),
    (12, "p13", None, [], "", "chapeu", [(12, None)], "p11"),
    (13, "p14", "floresta", ["lobo", "chapeu"], "the wolf points toward the dark forest path with a sly grin, the girl looks", "chapeu", [], None),
    (15, "p15", "floresta", ["chapeu"], "the girl hesitates at a fork in the path, finger on her chin, doubtful", "chapeu", [], None),
    (16, "p16", "bosque", ["lobo"], "the wolf runs fast along the sunny path, tongue out", "estilo", [], None),
    (17, "p17", "casa_vovo", ["lobo"], "the wolf knocks on the wooden door of grandma's cottage", "estilo", [], None),
    (18, "p18", "quarto_vovo", ["vovo"], "grandma sitting in her bed, looking toward the door, asking who is there", "vovo", [(18, None)], None),
    (19, "p19", "casa_vovo", ["lobo"], "close-up of the wolf at the door speaking in a sweet fake voice, paw near his mouth", "estilo", [], None),
    (20, "p20", None, [], "", "vovo", [(20, None)], "p18"),
    (21, "p21", "quarto_vovo", ["lobo"], "cartoon gag: the wolf with a huge round belly next to an empty bed, a nightcap on the floor, gentle and not scary", "estilo", [], None),
    (22, "p22", "quarto_vovo", ["lobo_disf"], "the disguised wolf lies in grandma's bed under the quilt, waiting", "estilo", [], None),
    (23, "p23", "quarto_vovo", ["chapeu"], "add the girl in her red hooded cape standing at the foot of the bed, holding her basket and looking at the one lying in the bed", "chapeu", [], None),
    (24, "p24", "quarto_vovo", ["chapeu"], "close-up of the girl, curious, asking a question", "chapeu", [(24, None)], None),
    (25, "p25", "quarto_vovo", ["lobo_disf"], "close-up of the disguised wolf in bed with very big ears poking out of the nightcap", "estilo", [], None),
    (26, "p26", None, [], "", "chapeu", [(26, None)], "p24"),
    (27, "p27", None, [], "", "estilo", [], "p25"),
    (28, "p28", "quarto_vovo", ["chapeu"], "close-up of the girl a bit scared, hands near her face", "chapeu", [(28, None)], None),
    (29, "p29", "quarto_vovo", ["lobo_disf"], "the disguised wolf jumps out of the bed, arms wide, big cartoon grin, funny not scary", "estilo", [], None),
    (30, "p30", "quarto_vovo", ["lobo_disf", "chapeu"], "cartoon chase: the wolf runs after the girl around the bedroom", "chapeu", [], None),
    (31, "p31", "quarto_vovo", ["lobo_disf"], "the wolf trips on the rug and falls on the floor, little stars around his head", "estilo", [], None),
    (32, "p32", "quarto_vovo", ["chapeu"], "the girl hides inside the big wardrobe, peeking through the gap", "chapeu", [], None),
    (33, "p33", "quarto_vovo", ["lobo_disf"], "the wolf sleeps on the floor snoring, big Zzz bubbles", "estilo", [], None),
    (34, "p34", "casa_vovo", ["cacador"], "the woodsman walks past the cottage window and stops, hand at his ear, listening", "cacador", [(35, None)], None),
    (36, "p35", "quarto_vovo", ["cacador"], "add the woodsman standing at the bedroom doorway, pointing in surprise at the one sleeping on the floor", "cacador", [], None),
    (38, "p36", "quarto_vovo", ["chapeu"], "add the girl in her red hooded cape stepping out of the open wardrobe and talking to the woodsman", "chapeu", [], None),
    (39, "p37", "quarto_vovo", ["vovo", "cacador"], "grandma, safe and smiling, is helped up by the woodsman next to the sleeping wolf, gentle, no injuries", "vovo", [], None),
    (40, "p38", "quarto_vovo", ["chapeu", "vovo"], "the girl and grandma hug happily", "chapeu", [], None),
    (41, "p39", "quarto_vovo", ["cacador"], "close-up of the woodsman scratching his beard, thinking", "cacador", [(41, None)], None),
    (42, "p40", "quarto_vovo", ["chapeu", "vovo", "cacador"], "the three put round stones into a sack next to the sleeping wolf, playful", "chapeu", [], None),
    (43, "p41", "floresta", ["lobo"], "cartoon: the wolf tumbles down, dizzy with stars around his head, comedic", "estilo", [], None),
    (44, "p42", "casa_vovo", ["chapeu", "vovo", "cacador"], "everyone cheers happily in front of grandma's cottage", "chapeu", [], None),
    (45, "p43", "casa_vovo", ["chapeu", "vovo"], "the girl and grandma sit on the porch eating sweets from the basket, sunset", "chapeu", [], None),
    (46, "p44", "casa", ["chapeu", "mae"], "back home, the girl hugs her mother and promises to always listen to her", "chapeu", [], None),
]


# decisão do Filipe (28/09/2026): história infantil com narradora por trás -> sem boca falando;
# as falas dos personagens aparecem na legenda com a cor de cada um. Mude para True para animar as bocas.
BOCA_FALANDO = False


# o lobo disfarçado aparece DEITADO/DORMINDO nestes planos; a ficha dele é em pé -> só pela descrição
SEM_REFERENCIA = {}
# planos que EDITAM um plano já aprovado (continuidade: o lobo continua igual e no mesmo lugar)
BASE = {"p23": "p22", "p35": "p33", "p36": "p35"}   # um personagem acrescentado por vez
# trilha: Kevin MacLeod, "Fairytale Waltz", CC BY 3.0 (crédito obrigatório na descrição do vídeo)
MUSICA = {"arquivo": "musica/fairytale_waltz.mp3", "volume_db": -22,
          "credito": "Fairytale Waltz Kevin MacLeod (incompetech.com) Licensed under Creative Commons: By Attribution 3.0 License"}


def inicio(k):
    if k == 0:
        return 0.0
    return round((linha[k - 1]["fim"] + linha[k]["inicio"]) / 2, 2)      # corta no meio da pausa


antigo = json.loads((AQUI / "projeto.json").read_text(encoding="utf-8")) if (AQUI / "projeto.json").exists() else {}
fichas = {g: {n: d.get("ficha") for n, d in antigo.get(g, {}).items()} for g in ("personagens", "cenarios")}
proj = {
    "titulo": "Chapeuzinho Vermelho", "titulo_duracao": 3.0,
    "formato": [1080, 1920], "fps": 30, "tamanho_plano": [768, 1344],
    "roteiro": "roteiro.txt", "audio": "audio.wav", "linha_do_tempo": "linha_do_tempo.json", "saida": "chapeuzinho.mp4",
    "estilo": ESTILO,
    "legenda": {"tema": "magico", "cores": {"narra": "C9A7FF", "mae": "FFB3D9", "chapeu": "FF6B6B", "lobo": "8FB8FF",
                          "lobo_disf": "B8A6FF", "vovo": "FFD27F", "cacador": "8FE3A0"}},
    "personagens": {n: {"descricao": d, "humano": h, "ficha": f"fichas/{n}.png",
                        **({"especie": "wolf", "anatomia": "2 braços, 2 pernas, 1 cauda"} if not h else
                           {"anatomia": "2 braços, 2 pernas, sem cauda"}),
                        **({"ref": REF_FICHA[n]} if n in REF_FICHA else {})}
                    for n, (d, h) in PERSONAGENS.items()},
    "cenarios": {n: {"descricao": f"{d}, empty scene with no people and no animals", "ficha": f"fichas/{n}.png"}
                 for n, d in CENARIOS.items()},
    "planos": [],
    "musica": MUSICA,
}
for k, pid, cen, pers, prompt, checar, fal, igual in S:
    p = {"id": pid, "inicio": inicio(k), "imagem": f"planos/{igual or pid}.png"}
    if prompt:
        p.update(cenario=cen, personagens=pers, prompt=prompt, checar=checar)
        if pid in SEM_REFERENCIA:
            p["sem_referencia"] = SEM_REFERENCIA[pid]
        if pid in BASE:
            p["base"] = BASE[pid]
    if fal and BOCA_FALANDO:
        p["fala"] = [dict(linha=li, **({"rosto": r} if r else {})) for li, r in fal]
    proj["planos"].append(p)
(AQUI / "projeto.json").write_text(json.dumps(proj, ensure_ascii=False, indent=1), encoding="utf-8")
unicos = len({p["imagem"] for p in proj["planos"]})
print(f"{len(proj['planos'])} planos ({unicos} imagens únicas), {len(PERSONAGENS)} personagens, {len(CENARIOS)} cenários")
