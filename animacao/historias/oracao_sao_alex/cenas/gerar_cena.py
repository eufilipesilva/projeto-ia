"""Gera uma cena nova mantendo a personagem e o estilo da imagem de referência,
usando Qwen-Image-Edit 2511 (versão rápida, Space grátis no Hugging Face).

    python gerar_cena.py "descrição da cena" nome_saida [referencia_extra.png ...]
"""
import base64, json, os, sys, time
from pathlib import Path

from gradio_client import Client

AQUI = Path(__file__).parent
REF = AQUI / "00_referencia.png"
SPACE = "prithivMLmods/Qwen-Image-Edit-2511-LoRAs-Fast"
ESTILO = "Anime-V2"   # a referência já é ilustração estilo anime; este LoRA não briga com ela

FICHA = (
    "Keep EXACTLY the same woman from image 1: same face, long wavy black hair, fair skin, "
    "black long-sleeve top, thin silver necklace with pendant. Keep the exact same illustration style "
    "of image 1: clean digital anime-like illustration, soft colors, blue-hour evening light with warm "
    "interior lamps. Do not change her face, hair or the art style. New scene: "
)


def b64(p):
    return "data:image/png;base64," + base64.b64encode(Path(p).read_bytes()).decode()


def token():
    try:
        from huggingface_hub import get_token
        return os.environ.get("HF_TOKEN") or get_token()
    except Exception:
        return os.environ.get("HF_TOKEN")


def gerar(cena, nome, extras=(), passos=8, guidance=1.0, semente=None, base=REF):
    cli = Client(SPACE, verbose=False, token=token())
    imgs = json.dumps([b64(p) for p in [base, *extras]])
    t = time.time()
    r = cli.predict(imgs, FICHA + cena, ESTILO, semente or 0, semente is None, guidance, passos, api_name="/edit_image")
    if r.get("status") != "success":
        raise RuntimeError(r)
    dst = AQUI / f"{nome}.png"
    dst.write_bytes(base64.b64decode(r["image"].split(",", 1)[1]))
    print(f"{dst.name}  seed={r['seed']}  {time.time() - t:.0f}s")
    return dst


FISCAL_PY = r"F:\Projeto IA\ferramentas\JoyVASA\.venv\Scripts\python.exe"
FISCAL = r"F:\Projeto IA\ferramentas\cenas\fiscal.py"
LOG = AQUI / "fiscal_log.jsonl"


def fiscalizar(cena_png, padroes):
    """Chama o fiscal (outro venv) e devolve o veredito dele como dict."""
    import subprocess
    caminhos = [str(Path(x).resolve()) for x in (cena_png, *padroes)]   # o fiscal muda de pasta ao carregar
    r = subprocess.run([FISCAL_PY, FISCAL, caminhos[0], "--padrao", *caminhos[1:]],
                       capture_output=True, text=True, encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    linhas = [l for l in r.stdout.splitlines() if l.startswith("{")]
    if not linhas:
        raise RuntimeError("fiscal falhou: " + (r.stderr or r.stdout)[-400:])
    return json.loads(linhas[-1])


def gerar_ate_passar(cena, nome, extras=(), base=REF, padroes=(), tentativas=4):
    """Gera a cena até o fiscal aprovar (cada tentativa com semente nova). As tentativas ficam em
    tentativas/<nome>_tN.png; a aprovada vira <nome>.png. Se nenhuma passar, <nome>.png não é tocado
    e a melhor fica indicada no log. Devolve o caminho aprovado ou None."""
    import shutil
    pasta = AQUI / "tentativas"; pasta.mkdir(exist_ok=True)
    melhor = None
    for k in range(1, tentativas + 1):
        try:
            png = gerar(cena, f"tentativas/{nome}_t{k}", extras, base=base)
        except Exception as e:
            msg = str(e)
            if "quota" in msg.lower():
                print("  cota grátis de GPU do Hugging Face esgotada; tente de novo mais tarde.")
                break
            print(f"  tentativa {k} falhou na geração: {msg[:160]}")
            continue
        v = fiscalizar(png, padroes)
        v.update(cena=nome, tentativa=k, arquivo=png.name, quando=time.strftime("%Y-%m-%d %H:%M"))
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(v, ensure_ascii=False) + "\n")
        print(f"  {png.name}: {'APROVADA' if v['aprovada'] else 'reprovada'}  nota {v['nota']}  {v['problemas'][:160]}")
        chave = (v["aprovada"], not v.get("traco_fantasma"), not v.get("rabiscado"), v["nota"])
        if melhor is None or chave > melhor[0]:
            melhor = (chave, png)
        if v["aprovada"]:
            dst = AQUI / f"{nome}.png"
            if dst.exists():
                shutil.copy2(dst, pasta / f"{nome}_anterior.png")
            shutil.copy2(png, dst)
            return dst
    if melhor:
        print(f"  nenhuma tentativa passou; a melhor foi {melhor[1].name} ({nome}.png não foi alterado)")
    return None


def fiscalizar_lote(cenas, padroes):
    """Uma chamada do fiscal para a rodada inteira (modelo carregado uma vez). cenas = {nome: [pngs]}.
    Devolve {nome: {"aprovada": caminho ou None, "vereditos": [...]}}; o progresso sai na tela."""
    import subprocess, tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump({n: [str(Path(c).resolve()) for c in cs] for n, cs in cenas.items()}, f)
    r = subprocess.run([FISCAL_PY, FISCAL, "--lote", f.name, "--padrao", *[str(Path(p).resolve()) for p in padroes]],
                       stdout=subprocess.PIPE, text=True, encoding="utf-8",
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    os.unlink(f.name)
    linhas = [l for l in r.stdout.splitlines() if l.startswith("{")]
    if not linhas:
        raise RuntimeError("fiscal falhou (veja as mensagens acima)")
    return json.loads(linhas[-1])


def gerar_ate_passar_kaggle(pedidos, padroes=(), por_rodada=2, rodadas=3, motor="klein"):
    """Como gerar_ate_passar, mas em lote na GPU grátis do Kaggle (sem a cota do Hugging Face).
    pedidos: [{"nome", "cena", "extras", "base"}]. Cada rodada gera `por_rodada` versões de TODAS as cenas
    pendentes de uma vez; o fiscal julga a rodada inteira numa chamada, a primeira aprovada de cada cena vira
    <nome>.png e só as reprovadas voltam na rodada seguinte. Devolve {nome: caminho aprovado ou None}."""
    import random, shutil
    sys.path.insert(0, str(Path(FISCAL).parent))
    from kaggle_cenas import gerar_lote
    pasta = AQUI / "tentativas"; pasta.mkdir(exist_ok=True)
    pendentes = {p["nome"]: p for p in pedidos}
    aprovadas = {n: None for n in pendentes}
    for rodada in range(1, rodadas + 1):
        if not pendentes:
            break
        itens = [{"nome": n, "prompt": FICHA + p["cena"], "imagens": [p.get("base", REF), *p.get("extras", ())],
                  "sementes": [random.randint(1, 2**31 - 1) for _ in range(por_rodada)]}
                 for n, p in pendentes.items()]
        print(f"rodada {rodada}: {', '.join(pendentes)}", flush=True)
        arquivos, _ = gerar_lote(itens, pasta, motor=motor)
        cenas = {n: sorted(a for a in arquivos if a.name.startswith(n + "_s")) for n in pendentes}
        t = time.time()
        res = fiscalizar_lote({n: cs for n, cs in cenas.items() if cs}, padroes)
        print(f"fiscal: {time.time() - t:.0f} s para a rodada", flush=True)
        with open(LOG, "a", encoding="utf-8") as f:
            for n, r in res.items():
                for v in r["vereditos"]:
                    v.update(cena=n, rodada=rodada, motor=motor, quando=time.strftime("%Y-%m-%d %H:%M"))
                    f.write(json.dumps(v, ensure_ascii=False) + "\n")
        for n, r in res.items():
            if r["aprovada"]:
                dst = AQUI / f"{n}.png"
                if dst.exists():
                    shutil.copy2(dst, pasta / f"{n}_anterior.png")
                shutil.copy2(r["aprovada"], dst)
                aprovadas[n] = dst
                del pendentes[n]
    for n in pendentes:
        print(f"  {n}: nenhuma versão passou em {rodadas} rodada(s); {n}.png não foi alterado")
    return aprovadas


if __name__ == "__main__":
    gerar(sys.argv[1], sys.argv[2], [Path(p) for p in sys.argv[3:]])
