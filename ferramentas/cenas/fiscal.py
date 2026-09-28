"""Fiscal de cenas: diz se uma cena gerada pode entrar no vídeo, olhando o ROSTO da personagem de perto.

Reprova quando:
  - aparece traço fantasma, mancha ou linha solta na pele (ex.: testa/entre os olhos da o01);
  - o rosto sai mais rabiscado ou num traço diferente das cenas aprovadas (ex.: o05 e o07);
  - não há rosto detectável (quando a cena deveria ter a personagem).

Como: recorta o rosto (203 pontos do LivePortrait, funcionam em desenho), põe ao lado do rosto de uma
cena APROVADA e pergunta a um modelo de visão local (Qwen3-VL no Ollama, grátis).

GPU: antes de julgar, pede ao Estúdio Web (se estiver aberto) para descarregar OmniVoice/Gemma e tira
os outros modelos do Ollama da placa; o recorte do rosto roda na CPU. No fim, descarrega o Qwen3-VL.

Roda no venv do JoyVASA:
    F:\\Projeto IA\\ferramentas\\JoyVASA\\.venv\\Scripts\\python.exe fiscal.py CENA.png --padrao APROVADA.png [...]
Imprime um JSON: {"aprovada": bool, "nota": 0-10, "problemas": "...", ...}
"""
import argparse, base64, io, json, sys, urllib.request
from pathlib import Path

sys.path.insert(0, r"F:\Projeto IA\ferramentas\visemas")
import numpy as np
import cv2

OLLAMA = "http://127.0.0.1:11434"
ESTUDIO = "http://127.0.0.1:5008"
MODELO = "qwen3-vl:4b"
NOTA_MINIMA = 7

PERGUNTA = """This image has two face crops of the same illustrated character.
LEFT = approved reference. RIGHT = new image to inspect.
The expression, eyes open or closed, mouth, hands and head pose MAY be different: that is fine, ignore it.
Judge ONLY the drawing quality of the RIGHT face compared with the LEFT one. Answer ONLY with JSON:
{"ghost_lines": true/false, "sketchy": true/false, "same_style": 0-10, "problems": "short description"}
ghost_lines = a clear DEFECT on the skin: a stray stroke, smudge, duplicated or ghost line across the forehead,
between the eyes, the nose bridge or the cheeks that does not belong to any facial feature. Normal blush,
shading, wrinkles of a worried expression or hands touching the face are NOT ghost lines.
sketchy = the RIGHT face is clearly rougher or messier than the LEFT: scribbled or doubled eyebrow lines,
extra pencil-like strokes, uneven linework. Only true if it is obvious.
same_style = how closely the RIGHT drawing style matches the LEFT (line quality, coloring, proportions)."""

PERGUNTA_ESTILO = """This image has two illustrations side by side. LEFT = approved reference of the art style.
RIGHT = new illustration to inspect. The scene, characters, pose and composition MAY be different: that is fine.
Judge ONLY the RIGHT image quality and whether it keeps the same art style as the LEFT. Answer ONLY with JSON:
{"defects": true/false, "style_off": true/false, "same_style": 0-10, "problems": "short description"}
defects = a clear rendering defect in the RIGHT image: deformed or melted face, extra or missing limbs or fingers,
duplicated body parts, ghost lines or smudges on skin, garbled objects. Only true if it is obvious.
style_off = the RIGHT image clearly uses a different art style (line quality, coloring, rendering) than the LEFT.
same_style = how closely the RIGHT art style matches the LEFT."""

_cropper = None


def cropper():
    global _cropper
    if _cropper is None:
        import boca  # noqa: F401  (prepara o caminho do JoyVASA/LivePortrait)
        from src.utils.cropper import Cropper
        from src.config.crop_config import CropConfig
        _cropper = Cropper(crop_cfg=CropConfig(), image_type="human_face", flag_force_cpu=True)  # placa fica p/ o juiz
    return _cropper


def _post(url, corpo=None, timeout=60):
    req = urllib.request.Request(url, json.dumps(corpo or {}).encode(), {"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=timeout).read()


def liberar_gpu():
    """Tira da placa o que não é o juiz: OmniVoice/Gemma do Estúdio e outros modelos do Ollama."""
    try:
        _post(ESTUDIO + "/api/gpu/liberar", timeout=60)
    except Exception:
        pass                                   # Estúdio fechado (ou versão sem a rota): nada a liberar
    try:
        ativos = json.loads(urllib.request.urlopen(OLLAMA + "/api/ps", timeout=5).read()).get("models", [])
        for m in ativos:
            if m["name"] != MODELO:
                _post(OLLAMA + "/api/generate", {"model": m["name"], "keep_alive": 0})
    except Exception:
        pass


def descarregar_juiz():
    try:
        _post(OLLAMA + "/api/generate", {"model": MODELO, "keep_alive": 0})
    except Exception:
        pass


def ler_rgb(p):
    return np.ascontiguousarray(cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)[..., ::-1])


def rosto(caminho, tam=448):
    """Recorte quadrado do rosto (da testa ao queixo, com margem) ou None se não achar rosto."""
    img = ler_rgb(caminho)
    c = cropper()
    f = c.face_analysis_wrapper.get(np.ascontiguousarray(img[..., ::-1]), flag_do_landmark_2d_106=True,
                                    direction="large-small")
    if not f:
        return None
    L = c.human_landmark_runner.run(img, f[0].landmark_2d_106)
    cx, cy = L[108:145].mean(0)
    lado = 1.5 * np.ptp(L[108:145, 0])
    x0, y0 = int(max(0, cx - lado / 2)), int(max(0, cy - lado * 0.6))
    x1, y1 = int(min(img.shape[1], cx + lado / 2)), int(min(img.shape[0], cy + lado * 0.4))
    return cv2.resize(img[y0:y1, x0:x1], (tam, tam), interpolation=cv2.INTER_LANCZOS4), int(x1 - x0)


def lado_a_lado(esq, dir_, altura=512):
    """Duas imagens na mesma altura, lado a lado, com uma faixa branca no meio."""
    a = cv2.resize(esq, (int(esq.shape[1] * altura / esq.shape[0]), altura), interpolation=cv2.INTER_AREA)
    b = cv2.resize(dir_, (int(dir_.shape[1] * altura / dir_.shape[0]), altura), interpolation=cv2.INTER_AREA)
    par = np.full((altura, a.shape[1] + b.shape[1] + 8, 3), 255, np.uint8)
    par[:, :a.shape[1]] = a; par[:, a.shape[1] + 8:] = b
    return par


def perguntar(esq, dir_, pergunta=PERGUNTA):
    par = lado_a_lado(esq, dir_, altura=esq.shape[0] if pergunta is PERGUNTA else 512)
    ok, buf = cv2.imencode(".png", par[..., ::-1])
    corpo = {"model": MODELO, "stream": False, "format": "json", "think": False,
             "options": {"temperature": 0, "num_ctx": 4096},
             "messages": [{"role": "user", "content": pergunta, "images": [base64.b64encode(buf).decode()]}]}
    for _ in range(3):   # o modelo às vezes gasta a resposta "pensando" e devolve vazio: tenta de novo
        txt = json.loads(_post(OLLAMA + "/api/chat", corpo, timeout=600))["message"].get("content", "")
        try:
            j = json.loads(txt[txt.find("{"): txt.rfind("}") + 1])
            if "defects" in j or "style_off" in j:          # modo estilo -> mesmas chaves do modo rosto
                j["ghost_lines"], j["sketchy"] = bool(j.pop("defects", False)), bool(j.pop("style_off", False))
            return j
        except ValueError:
            corpo["options"]["num_ctx"] = 8192
    raise RuntimeError("o juiz não devolveu JSON: " + txt[:200])


def confirmado(detalhes, chave):
    """Um defeito só conta se aparecer em TODAS as comparações, ou vier junto com nota de estilo <= 7 na
    mesma comparação. (Calibrado em 27/09/2026 nas 7 cenas da oração: um voto isolado com nota 8 era
    alarme falso — sobrancelha franzida de preocupação lida como "rabisco".)"""
    votos = [d for d in detalhes if d.get(chave)]
    return bool(votos) and (len(votos) == len(detalhes) or any(float(d.get("same_style", 0)) <= 7 for d in votos))


def fiscalizar(cena, padroes):
    """Compara o rosto da cena com o de cada cena aprovada e decide se ela passa."""
    r = rosto(cena)
    if r is None:
        return dict(aprovada=False, nota=0, problemas="nenhum rosto detectado", rosto_px=0)
    cand, px = r
    detalhes = []
    for p in padroes:
        ref = rosto(p)
        if ref is not None:
            detalhes.append(dict(padrao=Path(p).stem, **perguntar(ref[0], cand)))
    nota = float(np.mean([float(d.get("same_style", 0)) for d in detalhes])) if detalhes else 0.0
    fantasma, rabisco = confirmado(detalhes, "ghost_lines"), confirmado(detalhes, "sketchy")
    return dict(aprovada=bool(detalhes) and not fantasma and not rabisco and nota >= NOTA_MINIMA,
                nota=round(nota, 1), traco_fantasma=fantasma, rabiscado=rabisco,
                problemas=" | ".join(str(d["problems"]) for d in detalhes if d.get("problems")),
                rosto_px=px, detalhes=detalhes)


def _julgar(cand_img, refs, pergunta, nota_rapida):
    """Compara com o 1º padrão; só consulta os demais se houver dúvida. Devolve (detalhes, nota, fantasma, rabisco)."""
    detalhes = [dict(padrao=refs[0][0], **perguntar(refs[0][1], cand_img, pergunta))]
    d = detalhes[0]
    if d.get("ghost_lines") or d.get("sketchy") or float(d.get("same_style", 0)) < nota_rapida:
        detalhes += [dict(padrao=n, **perguntar(f, cand_img, pergunta)) for n, f in refs[1:]]
    nota = float(np.mean([float(x.get("same_style", 0)) for x in detalhes]))
    return detalhes, nota, confirmado(detalhes, "ghost_lines"), confirmado(detalhes, "sketchy")


def fiscalizar_lote(cenas, padroes=(), nota_rapida=8):
    """Julga uma rodada inteira num processo só (modelo carregado uma vez; padrões recortados uma vez).
    cenas = {nome: [candidatos]}  ou  {nome: {"candidatos": [...], "padroes": [...], "modo": "rosto"|"estilo"}}
      modo rosto  = compara o rosto do candidato com o rosto dos padrões (personagem humano);
      modo estilo = compara a imagem inteira com os padrões (traço + defeitos gerais), p/ cenas sem rosto humano.
    Se o modo é rosto e não há rosto humano no candidato (ex.: o lobo), cai para o modo estilo.
    Para em cada cena na primeira aprovada."""
    cache_rosto, cache_img = {}, {}

    def ref_rosto(p):
        if p not in cache_rosto:
            r = rosto(p)
            cache_rosto[p] = r[0] if r is not None else None
        return cache_rosto[p]

    def ref_img(p):
        if p not in cache_img:
            cache_img[p] = ler_rgb(p)
        return cache_img[p]

    saida = {}
    for nome, cfg in cenas.items():
        if isinstance(cfg, list):
            cfg = {"candidatos": cfg}
        pads = [str(p) for p in (cfg.get("padroes") or padroes)]
        modo = cfg.get("modo", "rosto")
        saida[nome] = {"aprovada": None, "vereditos": []}
        for c in cfg["candidatos"]:
            r = rosto(c) if modo == "rosto" else None
            usado = "rosto" if r is not None else "estilo"
            if usado == "rosto":
                refs = [(Path(p).stem, f) for p in pads if (f := ref_rosto(p)) is not None]
            else:
                refs = [(Path(p).stem, ref_img(p)) for p in pads]
            if not refs:
                v = dict(arquivo=Path(c).name, aprovada=False, nota=0, problemas="sem padrão utilizável", modo=usado)
            else:
                cand = r[0] if usado == "rosto" else ler_rgb(c)
                try:
                    detalhes, nota, fantasma, rabisco = _julgar(
                        cand, refs, PERGUNTA if usado == "rosto" else PERGUNTA_ESTILO, nota_rapida)
                    v = dict(arquivo=Path(c).name, aprovada=not fantasma and not rabisco and nota >= NOTA_MINIMA,
                             nota=round(nota, 1), traco_fantasma=fantasma, rabiscado=rabisco, modo=usado,
                             rosto_px=r[1] if r is not None else 0,
                             problemas=" | ".join(str(x["problems"]) for x in detalhes if x.get("problems")),
                             consultas=len(detalhes), detalhes=detalhes)
                except Exception as e:
                    # o juiz às vezes não responde (fica "pensando" e devolve vazio): uma imagem sem veredito
                    # não pode derrubar a rodada inteira
                    v = dict(arquivo=Path(c).name, aprovada=False, sem_veredito=True, nota=0, modo=usado,
                             problemas=f"juiz sem resposta: {str(e)[:120]}")
            saida[nome]["vereditos"].append(v)
            print(f"  {v['arquivo']}: {'APROVADA' if v['aprovada'] else 'SEM VEREDITO' if v.get('sem_veredito') else 'reprovada'}"
                  f"  ({usado}) nota {v['nota']}  {v['problemas'][:140]}", file=sys.stderr, flush=True)
            if v["aprovada"]:
                saida[nome]["aprovada"] = str(c)
                break
        if not saida[nome]["aprovada"]:
            # nenhuma aprovada mas alguma ficou sem veredito (falha do juiz, não defeito): entra a primeira delas,
            # marcada, e o revisor visual (agente revisor-cenas) confere depois
            sem = [v for v in saida[nome]["vereditos"] if v.get("sem_veredito")]
            if sem:
                c = next(x for x in cfg["candidatos"] if Path(x).name == sem[0]["arquivo"])
                saida[nome].update(aprovada=str(c), sem_fiscal=True)
                print(f"  {nome}: entra {sem[0]['arquivo']} SEM FISCAL (confira na revisão)", file=sys.stderr, flush=True)
    return saida


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cena", nargs="?"); ap.add_argument("--padrao", nargs="+", default=[])
    ap.add_argument("--lote", help="JSON {nome: [candidatos]}: julga a rodada inteira num processo só")
    ap.add_argument("--manter-juiz", action="store_true", help="não descarrega o modelo no fim")
    a = ap.parse_args()
    a.padrao = [Path(p).resolve() for p in a.padrao]
    liberar_gpu()
    try:
        if a.lote:
            cenas = json.loads(Path(a.lote).read_text(encoding="utf-8"))
            for n, cfg in cenas.items():
                if isinstance(cfg, list):
                    cenas[n] = [str(Path(c).resolve()) for c in cfg]
                else:
                    cfg["candidatos"] = [str(Path(c).resolve()) for c in cfg["candidatos"]]
                    cfg["padroes"] = [str(Path(c).resolve()) for c in cfg.get("padroes", [])]
            print(json.dumps(fiscalizar_lote(cenas, a.padrao), ensure_ascii=False))
        else:
            print(json.dumps(fiscalizar(Path(a.cena).resolve(), a.padrao), ensure_ascii=False))
    finally:
        if not a.manter_juiz:
            descarregar_juiz()


if __name__ == "__main__":
    main()
