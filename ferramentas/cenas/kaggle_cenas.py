"""Gera cenas numa GPU grátis do Kaggle (2x T4, 30 h/semana), com a mesma receita do Space que usávamos
(Qwen-Image-Edit-2511 + Rapid-AIO-V19 + LoRA Anime-V2). Tudo privado na conta do Filipe.

    from kaggle_cenas import gerar_lote
    arquivos = gerar_lote([{"nome": "o01_invocacao", "prompt": "...", "imagens": [base, extra], "sementes": [1, 2]}],
                          destino)

Fluxo: monta job.json + imagens -> dataset privado (nova versão) -> notebook privado com GPU (kaggle/gerador.py)
-> espera terminar -> baixa as imagens para `destino`. Precisa do token em ~/.kaggle/access_token.
Roda no .venv_omni (pacote `kaggle`).
"""
import json, shutil, subprocess, sys, time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
KAGGLE = str(Path(sys.executable).with_name("kaggle.exe"))
USUARIO = "filipepereira21"
DATASET = f"{USUARIO}/pandora-cenas-job"
KERNEL = f"{USUARIO}/pandora-gerador"
MODELOS = f"{USUARIO}/pandora-modelos"      # saída guardada com o klein pronto (kaggle/preparar.py, roda uma vez)
TRABALHO = Path(r"F:\Projeto IA\cache\kaggle")


def _k(*args, verificar=True):
    r = subprocess.run([KAGGLE, *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
    if verificar and r.returncode != 0:
        raise RuntimeError(f"kaggle {' '.join(args)} falhou: {(r.stderr or r.stdout)[-500:]}")
    return r.stdout + r.stderr


def _enviar_dataset(itens, passos, dtype, motor):
    pasta = TRABALHO / "job"
    shutil.rmtree(pasta, ignore_errors=True); pasta.mkdir(parents=True)
    job = {"motor": motor, "passos": passos, "dtype": dtype, "itens": []}
    for it in itens:
        nomes = []
        for k, img in enumerate(it["imagens"]):
            dst = f"{it['nome']}_{k}{Path(img).suffix.lower()}"
            shutil.copy2(img, pasta / dst); nomes.append(dst)
        job["itens"].append({"nome": it["nome"], "prompt": it["prompt"], "imagens": nomes,
                             "sementes": [int(s) for s in it["sementes"]],
                             **{k: int(it[k]) for k in ("largura", "altura") if it.get(k)}})
    (pasta / "job.json").write_text(json.dumps(job, ensure_ascii=False, indent=1), encoding="utf-8")
    (pasta / "dataset-metadata.json").write_text(json.dumps(
        {"title": "pandora-cenas-job", "id": DATASET, "licenses": [{"name": "CC0-1.0"}]}), encoding="utf-8")
    existe = "ready" in _k("datasets", "status", DATASET, verificar=False).lower()
    if existe:
        _k("datasets", "version", "-p", str(pasta), "-m", time.strftime("%Y-%m-%d %H:%M"), "-r", "zip")
    else:
        _k("datasets", "create", "-p", str(pasta), "-r", "zip")        # privado por padrão
    for _ in range(60):                                                  # espera o Kaggle processar a versão
        if "ready" in _k("datasets", "status", DATASET, verificar=False).lower():
            return
        time.sleep(10)
    raise RuntimeError("o dataset não ficou pronto no Kaggle")


def _disparar_kernel(limite_s, motor):
    pasta = TRABALHO / "kernel"
    shutil.rmtree(pasta, ignore_errors=True); pasta.mkdir(parents=True)
    shutil.copy2(AQUI / "kaggle" / "gerador.py", pasta / "gerador.py")
    # modelo klein guardado na conta: montado como entrada, sem baixar nada (se o notebook de cache já rodou)
    fontes = [MODELOS] if motor == "klein" and "COMPLETE" in _k("kernels", "status", MODELOS, verificar=False) else []
    (pasta / "kernel-metadata.json").write_text(json.dumps({
        "id": KERNEL, "title": "pandora-gerador", "code_file": "gerador.py", "language": "python",
        "kernel_type": "script", "is_private": True, "enable_gpu": True, "enable_internet": True,
        "machine_shape": "NvidiaTeslaT4", "dataset_sources": [DATASET],
        "competition_sources": [], "kernel_sources": fontes}), encoding="utf-8")
    _k("kernels", "push", "-p", str(pasta), "-t", str(limite_s))


def _esperar(limite_s):
    fim = time.time() + limite_s + 600
    while time.time() < fim:
        s = _k("kernels", "status", KERNEL, verificar=False)
        if "COMPLETE" in s:
            return True
        if "ERROR" in s or "CANCEL" in s:
            return False
        time.sleep(30)
    return False


def gerar_lote(itens, destino, motor="qwen", passos=None, dtype="fp16", limite_s=3 * 3600):
    """Gera todas as sementes de todos os itens numa rodada do Kaggle. Devolve (arquivos_png, resultado).
    motor: "qwen" (Qwen-Image-Edit 20B + Rapid-AIO + LoRA Anime-V2, mesmo traço do Space; 8 passos) ou
           "klein" (FLUX.2 klein 4B, bem mais leve; 4 passos)."""
    passos = passos or (4 if motor == "klein" else 8)
    destino = Path(destino); destino.mkdir(parents=True, exist_ok=True)
    t = time.time()
    print(f"kaggle ({motor}): enviando {len(itens)} cena(s), {sum(len(i['sementes']) for i in itens)} imagem(ns)...", flush=True)
    _enviar_dataset(itens, passos, dtype, motor)
    _disparar_kernel(limite_s, motor)
    print(f"kaggle: rodando (acompanhe em https://www.kaggle.com/code/{KERNEL})", flush=True)
    ok = _esperar(limite_s)
    saida = TRABALHO / "saida"
    shutil.rmtree(saida, ignore_errors=True); saida.mkdir(parents=True)
    _k("kernels", "output", KERNEL, "-p", str(saida), verificar=False)
    res_p = next(saida.rglob("resultado.json"), None)
    resultado = json.loads(res_p.read_text()) if res_p else {}
    arquivos = []
    por_nome = {f"{it['nome']}_s{int(s)}.png": (it, int(s)) for it in itens for s in it["sementes"]}
    for png in saida.rglob("*.png"):
        if png.name in resultado.get("invalidas", []):
            continue
        dst = destino / png.name
        shutil.copy2(png, dst); arquivos.append(dst)
        # manifesto de reprodução: tudo o que é preciso para gerar esta mesma imagem de novo
        if png.name in por_nome:
            it, s = por_nome[png.name]
            (destino / (png.stem + ".json")).write_text(json.dumps({
                "semente": s, "prompt": it["prompt"], "referencias": [str(x) for x in it["imagens"]],
                "largura": it.get("largura"), "altura": it.get("altura"), "motor": motor, "passos": passos,
                "dtype": dtype, "gerado_em": time.strftime("%Y-%m-%d %H:%M")}, ensure_ascii=False, indent=1),
                encoding="utf-8")
    print(f"kaggle: {'ok' if ok else 'FALHOU'} em {(time.time() - t) / 60:.0f} min, {len(arquivos)} imagem(ns) válidas"
          + (f", {len(resultado.get('invalidas', []))} inválidas" if resultado.get("invalidas") else ""), flush=True)
    if not ok and not arquivos:
        log = next(saida.rglob("*.log"), None)
        erro = ""
        if log:
            txt = log.read_text(encoding="utf-8", errors="replace")
            try:
                txt = "".join(e.get("data", "") for e in json.loads(txt))
            except ValueError:
                pass
            i = txt.rfind("Traceback")
            erro = txt[i:i + 2500] if i >= 0 else txt[-1500:]
        raise RuntimeError(f"rodada do Kaggle falhou (log em {log}):\n{erro}")
    return arquivos, resultado
