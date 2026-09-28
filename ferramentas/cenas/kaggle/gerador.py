"""Roda NO KAGGLE (2x T4). Gera cenas com a mesma receita do Space prithivMLmods/Qwen-Image-Edit-2511-LoRAs-Fast:
Qwen-Image-Edit-2511 + transformer Rapid-AIO-V19 (8 passos) + LoRA Anime-V2, guidance 1.

Entrada: job.json (dataset anexado) — {"passos": 8, "dtype": "fp16", "itens": [
    {"nome": "o01_invocacao", "prompt": "...", "imagens": ["o01_base.png", "o01_extra1.jpeg"], "sementes": [1, 2]}]}
Saída (/kaggle/working/saida): <nome>_s<semente>.png + resultado.json (tempos, imagens inválidas).

Duas placas: o codificador de texto (Qwen2.5-VL 7B, 8 bits) fica na cuda:1 e codifica todos os prompts;
o gerador (20B, 4 bits NF4) fica na cuda:0.
"""
import glob, json, math, os, subprocess, sys, time

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "bitsandbytes"], check=True)
os.environ["HF_HOME"] = "/tmp/hf"

import numpy as np
import torch
from PIL import Image
from huggingface_hub import snapshot_download

BASE = "Qwen/Qwen-Image-Edit-2511"
TRANSFORMER = "prithivMLmods/Qwen-Image-Edit-Rapid-AIO-V19"
LORA = ("prithivMLmods/Qwen-Image-Edit-2511-Anime", "Qwen-Image-Edit-2511-Anime-2000.safetensors")
SAIDA = "/kaggle/working/saida"
os.makedirs(SAIDA, exist_ok=True)
t0 = time.time()
log = {"tempos": {}, "invalidas": [], "geradas": []}


def marca(etapa):
    log["tempos"][etapa] = round(time.time() - t0, 1)
    print(f"[{time.time() - t0:7.1f}s] {etapa}", flush=True)
    json.dump(log, open(f"{SAIDA}/resultado.json", "w"), indent=1)


job_path = glob.glob("/kaggle/input/**/job.json", recursive=True)[0]
PASTA = os.path.dirname(job_path)
job = json.load(open(job_path))
DT = {"fp16": torch.float16, "bf16": torch.bfloat16, "fp32": torch.float32}[job.get("dtype", "fp16")]
marca(f"job: {len(job['itens'])} cenas, dtype {job.get('dtype', 'fp16')}")

def rodar_klein():
    """Motor leve: FLUX.2 klein 4B (4 passos, edita com até 4 imagens de referência, Apache 2.0).
    1) o codificador de texto (Qwen3 4B, só lê o texto) codifica todos os prompts e sai da placa;
    2) gerador + VAE (~8 GB) carregam em CADA T4 e as imagens são geradas duas a duas, em paralelo.
    Usa o modelo guardado na conta (notebook pandora-modelos) quando estiver montado; senão, baixa."""
    import threading, queue
    from diffusers import Flux2KleinPipeline
    guardado = glob.glob("/kaggle/input/**/klein/model_index.json", recursive=True)
    fonte = os.path.dirname(guardado[0]) if guardado else "black-forest-labs/FLUX.2-klein-4B"
    marca(f"klein: {'modelo guardado na conta' if guardado else 'baixando do Hugging Face'}")

    te = Flux2KleinPipeline.from_pretrained(fonte, transformer=None, vae=None, torch_dtype=DT).to("cuda:0")
    embeds = {}
    with torch.no_grad():
        for it in job["itens"]:
            embeds[it["nome"]] = te.encode_prompt(prompt=it["prompt"], device=torch.device("cuda:0"))[0].cpu()
    # libera o codificador DE VERDADE: sem o gc, ele ficava na placa 0 e o gerador dela estourava a memória
    # (28/09/2026: a placa 0 morreu na 1ª imagem e a placa 1 fez as 77 sozinha, em 81 min)
    import gc
    te.text_encoder.to("cpu"); del te; gc.collect(); torch.cuda.empty_cache()
    marca(f"prompts codificados; placa 0 com {torch.cuda.memory_allocated(0) / 1e9:.1f} GB ocupados")

    def carregar(gpu):
        p = Flux2KleinPipeline.from_pretrained(fonte, text_encoder=None, tokenizer=None, torch_dtype=DT)
        p.to(f"cuda:{gpu}")
        p.vae.to(torch.float32)                  # VAE em fp32: evita imagem preta por estouro em fp16
        dec = p.vae.decode                       # ... mas o pipeline entrega os latentes em 16 bits
        p.vae.decode = lambda z, *a, **k: dec(z.to(torch.float32), *a, **k)
        return p

    gpus = list(range(torch.cuda.device_count())) or [0]
    pipes = {g: carregar(g) for g in gpus}
    marca(f"gerador carregado em {len(pipes)} placa(s) ({DT})")

    tarefas = queue.Queue()
    for it in job["itens"]:
        # até 4 imagens de referência (limite do klein); sem nenhuma = criar do zero (fichas de personagem)
        imgs = [Image.open(os.path.join(PASTA, x)).convert("RGB") for x in it["imagens"][:4]]
        if it.get("largura") and it.get("altura"):            # tamanho pedido (ex.: vertical 9:16)
            W, H = int(it["largura"]), int(it["altura"])
        elif imgs:
            w0, h0 = imgs[0].size
            W, H = (1024, int(1024 * h0 / w0)) if w0 > h0 else (int(1024 * w0 / h0), 1024)
        else:
            W, H = 1024, 1024
        for s in it["sementes"]:
            tarefas.put((it["nome"], imgs or None, W // 16 * 16, H // 16 * 16, s))
    trava = threading.Lock()

    def trabalhador(gpu):
        p = pipes[gpu]
        while True:
            try:
                nome_it, imgs, W, H, s = tarefas.get_nowait()
            except queue.Empty:
                return
            ti = time.time()
            try:
                with torch.no_grad():
                    img = p(image=imgs, prompt=None, prompt_embeds=embeds[nome_it].to(f"cuda:{gpu}"), height=H,
                            width=W, num_inference_steps=job.get("passos", 4), guidance_scale=1.0,
                            generator=torch.Generator("cpu").manual_seed(int(s))).images[0]
            except Exception as e:
                # esta placa falhou (ex.: memória): devolve a tarefa para a outra placa e sai
                tarefas.put((nome_it, imgs, W, H, s))
                with trava:
                    log.setdefault("erros", []).append({"gpu": gpu, "erro": str(e)[:300]})
                    marca(f"placa {gpu} saiu: {str(e)[:120]}")
                return
            a = np.asarray(img, np.float32)
            nome = f"{nome_it}_s{s}.png"
            img.save(f"{SAIDA}/{nome}")
            with trava:
                if a.std() < 3:
                    log["invalidas"].append(nome)   # preta/lisa: estouro numérico (tente dtype bf16 no job)
                log["geradas"].append({"arquivo": nome, "segundos": round(time.time() - ti, 1), "gpu": gpu,
                                       "desvio": round(float(a.std()), 1), "calculo": str(DT), "motor": "klein"})
                marca(f"{nome} (placa {gpu}, {time.time() - ti:.0f}s, desvio {a.std():.1f})")

    fios = [threading.Thread(target=trabalhador, args=(g,)) for g in pipes]
    for f in fios:
        f.start()
    for f in fios:
        f.join()
    marca("fim")


if job.get("motor") == "klein":
    rodar_klein()
    sys.exit(0)

from diffusers import QwenImageEditPlusPipeline, QwenImageTransformer2DModel
from diffusers import BitsAndBytesConfig as DiffBnb
from transformers import Qwen2_5_VLForConditionalGeneration, BitsAndBytesConfig as TrBnb

base_dir = snapshot_download(BASE, allow_patterns=["model_index.json", "text_encoder/*", "tokenizer/*",
                                                   "processor/*", "vae/*", "scheduler/*"])
marca("base baixada")


def dims(area, razao):
    w = math.sqrt(area * razao); h = w / razao
    return round(w / 32) * 32, round(h / 32) * 32


# ---------------------------------------------------------------- fase 1: prompts (cuda:1)
te = Qwen2_5_VLForConditionalGeneration.from_pretrained(
    base_dir, subfolder="text_encoder", quantization_config=TrBnb(load_in_8bit=True),
    torch_dtype=DT, device_map={"": 1})
pipe_te = QwenImageEditPlusPipeline.from_pretrained(base_dir, transformer=None, text_encoder=te, torch_dtype=DT)
marca("codificador de texto carregado")
embeds = {}
for it in job["itens"]:
    imgs = [Image.open(os.path.join(PASTA, p)).convert("RGB") for p in it["imagens"]]
    cond = []
    for im in imgs:
        w, h = dims(384 * 384, im.width / im.height)
        cond.append(pipe_te.image_processor.resize(im, h, w))
    with torch.no_grad():
        e, m = pipe_te.encode_prompt(prompt=it["prompt"], image=cond, device=torch.device("cuda:1"))
    # a máscara vem None quando o prompt não tem preenchimento (diffusers >= 0.37), mas o pipeline
    # exige uma quando recebe prompt_embeds: nesse caso é tudo 1
    if m is None:
        m = torch.ones(e.shape[:2], dtype=torch.long, device=e.device)
    embeds[it["nome"]] = (e.to("cuda:0"), m.to("cuda:0"), imgs)
del pipe_te, te
torch.cuda.empty_cache()
marca("prompts codificados")

# ---------------------------------------------------------------- fase 2: imagens (cuda:0)
def converter_fp8(repo, destino="/tmp/v19_fp16", lote_gb=4.0):
    """O Rapid-AIO V19 vem em fp8, e o bitsandbytes só quantiza 16/32 bits: converte para fp16 no disco,
    em pedaços de ~4 GB (cabe na RAM), com o índice apontando para os pedaços novos."""
    from safetensors import safe_open
    from safetensors.torch import save_file
    if os.path.exists(f"{destino}/config.json"):
        return destino
    src = snapshot_download(repo)
    os.makedirs(destino, exist_ok=True)
    mapa, buf, tam, n = {}, {}, 0, 0
    def gravar():
        nonlocal buf, tam, n
        if buf:
            nome = f"diffusion_pytorch_model-{n:05d}.safetensors"
            save_file(buf, f"{destino}/{nome}")
            mapa.update({k: nome for k in buf}); buf, tam, n = {}, 0, n + 1
    escalas = 0
    for shard in sorted(glob.glob(f"{src}/*.safetensors")):
        with safe_open(shard, "pt") as f:
            for k in f.keys():
                t = f.get_tensor(k)
                escalas += "scale" in k
                if t.dtype in (torch.float8_e4m3fn, torch.float8_e5m2, torch.bfloat16, torch.float32):
                    t = t.to(torch.float16)
                buf[k] = t; tam += t.numel() * t.element_size()
                if tam > lote_gb * 1e9:
                    gravar()
    gravar()
    json.dump({"metadata": {}, "weight_map": mapa},
              open(f"{destino}/diffusion_pytorch_model.safetensors.index.json", "w"))
    import shutil
    shutil.copy2(f"{src}/config.json", f"{destino}/config.json")
    print(f"convertido para fp16 ({len(mapa)} tensores; chaves com 'scale': {escalas})", flush=True)
    return destino


tr_dir = converter_fp8(TRANSFORMER)
marca("gerador convertido fp8 -> fp16")
def carregar_gerador(dt):
    """Gerador em 4 bits (NF4) na cuda:0, com o LoRA Anime-V2. O VAE fica sempre em fp32: em fp16 ele
    estoura e a imagem sai preta; a entrada/saída dele é convertida para o resto do pipeline."""
    tr = QwenImageTransformer2DModel.from_pretrained(
        tr_dir, quantization_config=DiffBnb(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=dt),
        torch_dtype=dt, device_map={"": 0})
    p = QwenImageEditPlusPipeline.from_pretrained(base_dir, transformer=tr, text_encoder=None, tokenizer=None,
                                                  torch_dtype=dt)
    # VAE em fp32 na cuda:1 (livre depois do codificador de texto): na cuda:0 não cabe junto do gerador
    p.vae.to("cuda:1", torch.float32)
    type(p)._execution_device = property(lambda self: torch.device("cuda:0"))
    original, dec = p._encode_vae_image, p.vae.decode
    p._encode_vae_image = lambda image, generator: original(image.to("cuda:1", torch.float32), generator).to("cuda:0", dt)
    p.vae.decode = lambda z, *a, **k: dec(z.to("cuda:1", torch.float32), *a, **k)
    p.load_lora_weights(LORA[0], weight_name=LORA[1], adapter_name="anime")
    p.set_adapters(["anime"], adapter_weights=[1.0])
    return p


pipe = carregar_gerador(DT)
marca(f"gerador carregado (NF4, cálculo {DT}) + LoRA Anime-V2")
estouro = {"passo": None}


def vigia(p, i, t, kw):
    if estouro["passo"] is None and not torch.isfinite(kw["latents"]).all():
        estouro["passo"] = i
    return kw


def gerar(e, m, imgs, H, W, semente):
    estouro["passo"] = None
    with torch.no_grad():
        return pipe(image=imgs, prompt=None, prompt_embeds=e.to(DT), prompt_embeds_mask=m, height=H, width=W,
                    num_inference_steps=job.get("passos", 8), true_cfg_scale=1.0,
                    generator=torch.Generator("cuda:0").manual_seed(int(semente)),
                    callback_on_step_end=vigia, callback_on_step_end_tensor_inputs=["latents"]).images[0]


for it in job["itens"]:
    e, m, imgs = embeds[it["nome"]]
    w0, h0 = imgs[0].size
    if w0 > h0:
        W, H = 1024, int(1024 * h0 / w0)
    else:
        W, H = int(1024 * w0 / h0), 1024
    W, H = W // 8 * 8, H // 8 * 8
    for s in it["sementes"]:
        ti = time.time()
        img = gerar(e, m, imgs, H, W, s)
        a = np.asarray(img, np.float32)
        if (a.std() < 3 or estouro["passo"] is not None) and DT == torch.float16:
            # o gerador estourou em fp16: recarrega calculando em bf16 (a T4 emula; mais lento) e refaz
            log["estouro_fp16"] = {"passo": estouro["passo"], "desvio": round(float(a.std()), 1)}
            marca(f"estouro em fp16 (passo {estouro['passo']}); recarregando em bf16")
            del pipe; torch.cuda.empty_cache()
            DT = torch.bfloat16
            pipe = carregar_gerador(DT)
            marca("gerador recarregado em bf16")
            ti = time.time()
            img = gerar(e, m, imgs, H, W, s)
            a = np.asarray(img, np.float32)
        nome = f"{it['nome']}_s{s}.png"
        if not np.isfinite(a).all() or a.std() < 3:
            log["invalidas"].append(nome)
        img.save(f"{SAIDA}/{nome}")
        log["geradas"].append({"arquivo": nome, "segundos": round(time.time() - ti, 1), "desvio": round(float(a.std()), 1),
                               "calculo": str(DT), "estouro_no_passo": estouro["passo"]})
        marca(f"{nome} ({time.time() - ti:.0f}s, {DT}, desvio {a.std():.1f})")
marca("fim")
