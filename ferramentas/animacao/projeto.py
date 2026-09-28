"""Carrega e confere o projeto.json de uma história (fonte única da verdade da esteira).

Resolve as referências às bibliotecas compartilhadas em F:\\Projeto IA\\animacao\\:
  personagens / cenários   {"elenco": "lobo_mau"}        -> elenco\\personagens\\lobo_mau\\ficha.json + ficha.png
  estilo                   {"biblioteca": "livro_aquarela"} -> estilos\\livro_aquarela.json
  música                   {"biblioteca": "fairytale_waltz", "volume_db": -22} -> musicas\\catalogo.json
Campos escritos no próprio projeto sempre têm prioridade sobre os da biblioteca.

Planos: "linha": k (índice da fala em linha_do_tempo.json onde o plano começa) vira "inicio" automaticamente
(corta no meio da pausa entre a fala anterior e esta). Assim o storyboard é só dados, sem código por história.
"""
import json
from pathlib import Path

RAIZ = Path(r"F:\Projeto IA\animacao")
ELENCO, ESTILOS, MUSICAS, HISTORIAS = RAIZ / "elenco", RAIZ / "estilos", RAIZ / "musicas", RAIZ / "historias"


def _ler(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def ficha_biblioteca(tipo, ident):
    """tipo = 'personagens' | 'cenarios'. Devolve os dados da biblioteca com 'ficha' em caminho absoluto."""
    d = ELENCO / tipo / ident
    if not (d / "ficha.json").exists():
        raise FileNotFoundError(f"{tipo[:-1]} '{ident}' não está no elenco ({d})")
    dados = _ler(d / "ficha.json")
    dados["ficha"] = str(d / "ficha.png")
    return dados


def carregar(pasta, resolver=True):
    """Lê projeto.json; com resolver=True devolve a versão pronta para a esteira (bibliotecas e tempos resolvidos).
    Com resolver=False devolve o arquivo cru (para editar e salvar sem 'achatar' as referências)."""
    pasta = Path(pasta)
    proj = _ler(pasta / "projeto.json")
    if not resolver:
        return proj
    for tipo in ("personagens", "cenarios"):
        for nome, d in list(proj.get(tipo, {}).items()):
            if d.get("elenco"):
                proj[tipo][nome] = {**ficha_biblioteca(tipo, d["elenco"]), **{k: v for k, v in d.items() if k != "elenco"},
                                    "elenco": d["elenco"]}
    est = proj.get("estilo")
    if isinstance(est, dict) and est.get("biblioteca"):
        e = _ler(ESTILOS / f"{est['biblioteca']}.json")
        proj["estilo"] = e["texto"]
        proj.setdefault("tamanho_plano", e.get("tamanho_plano", [768, 1344]))
        proj.setdefault("legenda", {}).setdefault("tema", e.get("tema_legenda"))
        proj["legenda"].setdefault("fonte", e.get("fonte_legenda", "Fredoka Legenda"))
    mus = proj.get("musica")
    if isinstance(mus, dict) and mus.get("biblioteca"):
        cat = _ler(MUSICAS / "catalogo.json")[mus["biblioteca"]]
        proj["musica"] = {"arquivo": str(MUSICAS / cat["arquivo"]), "volume_db": mus.get("volume_db", cat.get("volume_db", -22)),
                          "credito": cat["credito"], "licenca": cat["licenca"]}
    # cor da legenda de cada personagem: a do projeto; senão a da ficha do elenco
    cores = proj.setdefault("legenda", {}).setdefault("cores", {})
    for nome, d in proj.get("personagens", {}).items():
        if d.get("cor_legenda"):
            cores.setdefault(nome, d["cor_legenda"])
    # início de cada plano a partir da fala
    lt = pasta / proj.get("linha_do_tempo", "linha_do_tempo.json")
    if lt.exists():
        falas = _ler(lt)["falas"]
        for p in proj.get("planos", []):
            if "linha" in p and "inicio" not in p:
                k = p["linha"]
                p["inicio"] = 0.0 if k == 0 else round((falas[k - 1]["fim"] + falas[k]["inicio"]) / 2, 2)
    return proj


def salvar(pasta, proj):
    (Path(pasta) / "projeto.json").write_text(json.dumps(proj, ensure_ascii=False, indent=1), encoding="utf-8")


def conferir(pasta):
    """Lista de problemas do projeto (vazia = tudo certo para montar)."""
    pasta = Path(pasta)
    prob = []
    try:
        proj = carregar(pasta)
    except Exception as e:
        return [f"projeto.json não carrega: {e}"]
    for arq in ("roteiro", "audio", "linha_do_tempo"):
        if proj.get(arq) and not (pasta / proj[arq]).exists():
            prob.append(f"falta {arq}: {proj[arq]}")
    for tipo in ("personagens", "cenarios"):
        for nome, d in proj.get(tipo, {}).items():
            if not d.get("descricao"):
                prob.append(f"{tipo[:-1]} {nome}: sem descrição")
            if not d.get("ficha") or not (pasta / d["ficha"]).exists():
                prob.append(f"{tipo[:-1]} {nome}: sem ficha escolhida")
    ids = {p["id"] for p in proj.get("planos", [])}
    for p in proj.get("planos", []):
        if "inicio" not in p:
            prob.append(f"plano {p['id']}: sem 'linha' nem 'inicio'")
        for q in p.get("personagens", []):
            if q not in proj.get("personagens", {}):
                prob.append(f"plano {p['id']}: personagem desconhecido '{q}'")
        if p.get("base") and p["base"] not in ids:
            prob.append(f"plano {p['id']}: base '{p['base']}' não existe")
        if not (pasta / p["imagem"]).exists():
            prob.append(f"plano {p['id']}: falta a imagem {p['imagem']}")
    m = proj.get("musica")
    if m and not Path(pasta / m["arquivo"]).exists():
        prob.append(f"música não encontrada: {m['arquivo']}")
    return prob
