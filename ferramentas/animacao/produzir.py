"""Esteira do Estúdio de Animação: de um roteiro + áudio ao vídeo pronto, para QUALQUER história.

    F:\\Projeto IA\\.venv_omni\\Scripts\\python.exe produzir.py HISTORIA ETAPA [opções]

HISTORIA = nome da pasta em F:\\Projeto IA\\animacao\\historias\\ (ex.: chapeuzinho_vermelho) ou um caminho.
O passo a passo completo, com exemplos, está em F:\\Projeto IA\\animacao\\README.md.

Etapas:
  novo      cria a história: produzir.py nome novo --roteiro R.txt --audio A.wav [--titulo T] [--estilo E] [--musica M]
  alinhar   roteiro + áudio -> linha_do_tempo.json (quem fala, quando, palavra a palavra)
  status    o que está pronto e o que falta (confere o projeto.json)
  fichas    desenha as fichas de personagens/cenários que NÃO vêm do elenco (N opções cada, em fichas/opcoes/);
            depois o agente revisor-cenas sugere a melhor e você copia para fichas/<nome>.png
  elenco    guarda na biblioteca (animacao/elenco/) as fichas escolhidas desta história, para reaproveitar
  planos    gera as imagens dos planos (Kaggle, FLUX.2 klein) em planos/tentativas/
  escolhas  instala as versões escolhidas pelo agente revisor-cenas (planos/revisao*.json) + manifesto + folha
  compor    refaz os planos montados por composição (campo "composicao": personagem recortado de outro plano)
  falas     boca falando nos planos com "fala" (opcional; histórias com narradora por trás não usam)
  montar    monta o vídeo (--rascunho = prévia rápida)

Fluxo de uma história: novo -> (storyboard no projeto.json) -> fichas -> revisor -> elenco -> planos -> revisor
-> escolhas -> (planos --refazer-revisao -> revisor -> escolhas, até não sobrar reprovado) -> compor -> montar.
"""
import argparse, json, random, re, shutil, subprocess, sys, time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "cenas")); sys.path.insert(0, str(AQUI))
import projeto as P                                   # noqa: E402

JOY_PY = r"F:\Projeto IA\ferramentas\JoyVASA\.venv\Scripts\python.exe"
MAOS_PY = r"F:\Projeto IA\ferramentas\cenas\.venv_maos\Scripts\python.exe"      # rembg (recorte)
FISCAL = str(AQUI.parent / "cenas" / "fiscal.py")
FALAR = str(AQUI.parent / "visemas" / "falar.py")


def pasta_da(historia):
    p = Path(historia)
    return (p if p.is_absolute() or p.exists() else P.HISTORIAS / historia).resolve()


def fiscalizar_lote(cenas):
    """Fiscal automático (opcional, --com-fiscal): rosto/estilo com Qwen3-VL local. Não pega anatomia."""
    import os, tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump({n: {**c, "candidatos": [str(x) for x in c["candidatos"]], "padroes": [str(x) for x in c["padroes"]]}
                   for n, c in cenas.items()}, f)
    r = subprocess.run([JOY_PY, FISCAL, "--lote", f.name], stdout=subprocess.PIPE, text=True, encoding="utf-8",
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    os.unlink(f.name)
    linhas = [l for l in r.stdout.splitlines() if l.startswith("{")]
    if not linhas:
        raise RuntimeError("o fiscal falhou (veja as mensagens acima)")
    return json.loads(linhas[-1])


# ------------------------------------------------------------------------------------------ criar
def novo(pasta, proj, a):
    if (pasta / "projeto.json").exists():
        raise SystemExit(f"já existe: {pasta}")
    if not (a.roteiro and a.audio):
        raise SystemExit("use: produzir.py NOME novo --roteiro ROTEIRO.txt --audio AUDIO.wav")
    pasta.mkdir(parents=True)
    shutil.copy2(a.roteiro, pasta / "roteiro.txt")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", a.audio, "-ac", "1", "-ar", "24000", str(pasta / "audio.wav")],
                   check=True)
    modelo = {
        "titulo": a.titulo or pasta.name.replace("_", " ").title(), "titulo_duracao": 3.0,
        "formato": [1080, 1920], "fps": 30,
        "roteiro": "roteiro.txt", "audio": "audio.wav", "linha_do_tempo": "linha_do_tempo.json",
        "saida": f"{pasta.name}.mp4",
        "estilo": {"biblioteca": a.estilo},
        "legenda": {"cores": {"narra": "C9A7FF"}},
        "personagens": {}, "cenarios": {}, "planos": [],
    }
    if a.musica:
        modelo["musica"] = {"biblioteca": a.musica, "volume_db": -22}
    P.salvar(pasta, modelo)
    print(f"criada: {pasta}")
    alinhar(pasta, P.carregar(pasta), a)
    print("PRÓXIMO: storyboard. Preencha personagens, cenários e planos no projeto.json (ou peça ao Claude). "
          "Personagens já existentes: use {\"elenco\": \"id\"} (lista em animacao/elenco/).")


def alinhar(pasta, proj, a):
    subprocess.run([sys.executable, str(AQUI / "alinhar.py"), str(pasta / proj.get("roteiro", "roteiro.txt")),
                    str(pasta / proj["audio"]), str(pasta / proj["linha_do_tempo"])], check=True)


def status(pasta, proj, a):
    planos = proj.get("planos", [])
    com_img = sum((pasta / p["imagem"]).exists() for p in planos)
    print(f"{pasta.name}: {len(planos)} planos ({com_img} com imagem), "
          f"{len(proj.get('personagens', {}))} personagens, {len(proj.get('cenarios', {}))} cenários")
    for tipo in ("personagens", "cenarios"):
        for n, d in proj.get(tipo, {}).items():
            origem = f"elenco:{d['elenco']}" if d.get("elenco") else ("ficha local" if (pasta / d.get('ficha', '_')).exists() else "SEM FICHA")
            print(f"  {'personagem' if tipo == 'personagens' else 'cenário':10s} {n:14s} {origem}")
    saida = pasta / proj.get("saida", "video.mp4")
    print(f"  vídeo: {'pronto (' + saida.name + ')' if saida.exists() else 'ainda não montado'}")
    prob = P.conferir(pasta)
    print("tudo certo para montar" if not prob else "pendências:\n  - " + "\n  - ".join(prob))


# ------------------------------------------------------------------------------------------ fichas / elenco
def fichas(pasta, proj, a):
    from kaggle_cenas import gerar_lote
    estilo, (W, H) = proj.get("estilo", ""), proj.get("tamanho_plano", [768, 1344])
    itens = []
    for grupo, fundo in (("personagens", "full body, standing, simple plain light background, character design sheet"),
                         ("cenarios", "wide establishing shot, empty scene with no people and no animals")):
        for nome, d in proj.get(grupo, {}).items():
            if d.get("elenco") and nome not in a.refazer:
                continue                                    # vem da biblioteca
            d.setdefault("ficha", f"fichas/{nome}.png")
            if (pasta / d["ficha"]).exists() and nome not in a.refazer:
                continue
            # derivado de outro personagem (ex.: o mesmo lobo, disfarçado): a ficha dele entra como referência
            ref = None
            if d.get("derivado_de"):
                ref = Path(P.ficha_biblioteca("personagens", d["derivado_de"])["ficha"]) \
                    if (P.ELENCO / "personagens" / d["derivado_de"]).exists() else pasta / f"fichas/{d['derivado_de']}.png"
            elif d.get("ref"):
                ref = pasta / d["ref"]
            if ref is not None and not ref.exists():
                print(f"  {nome}: espera a ficha de referência {ref.name} ser escolhida; rode de novo depois")
                continue
            itens.append({"nome": f"{grupo[:4]}_{nome}", "prompt": f"{estilo} {d['descricao']}. {fundo}.",
                          "imagens": [ref] if ref else [],
                          "sementes": [random.randint(1, 2**31 - 1) for _ in range(a.opcoes)],
                          "largura": W, "altura": H})
    from conferencia import folha
    if not itens:
        fichas_ok = [pasta / d["ficha"] for g in ("personagens", "cenarios") for d in proj.get(g, {}).values()
                     if d.get("ficha") and (pasta / d["ficha"]).exists()]
        f = folha(fichas_ok, pasta / "fichas" / "elenco_escolhido.jpg", colunas=6)
        print(f"todas as fichas prontas; folha do elenco em {f}"); return
    arquivos, _ = gerar_lote(itens, pasta / "fichas" / "opcoes", motor="klein")
    f = folha(sorted(arquivos), pasta / "fichas" / "folha_conferencia.jpg")
    print(f"PRÓXIMO: agente revisor-cenas (etapa fichas) lê {f}; copie a escolhida de cada um para fichas/<nome>.png")


def elenco(pasta, proj, a):
    """Guarda as fichas locais desta história na biblioteca e troca, no projeto, por {"elenco": id}."""
    cru = P.carregar(pasta, resolver=False)
    cores = cru.get("legenda", {}).get("cores", {})
    ids = dict(x.split("=") for x in a.ids) if a.ids else {}
    salvos = 0
    for tipo in ("personagens", "cenarios"):
        for nome, d in cru.get(tipo, {}).items():
            if d.get("elenco"):
                continue
            ficha = pasta / d.get("ficha", f"fichas/{nome}.png")
            if not ficha.exists():
                print(f"  {nome}: sem ficha escolhida, fica de fora"); continue
            ident = ids.get(nome, nome)
            dst = P.ELENCO / tipo / ident
            if dst.exists():
                ident = f"{ident}_{pasta.name}"; dst = P.ELENCO / tipo / ident
            dst.mkdir(parents=True)
            shutil.copy2(ficha, dst / "ficha.png")
            info = {"id": ident, "descricao": d["descricao"]}
            if tipo == "personagens":
                info.update({k: d[k] for k in ("humano", "especie", "anatomia") if k in d})
                if cores.get(nome):
                    info["cor_legenda"] = cores[nome]
                if d.get("derivado_de"):
                    info["derivado_de"] = d["derivado_de"]
            est = cru.get("estilo")
            info["estilo"] = est.get("biblioteca") if isinstance(est, dict) else None
            side = next((pasta / "fichas" / "opcoes").glob(ficha.stem + "*.json"), None)
            info["origem"] = {"historia": pasta.name, "nome_na_historia": nome, "data": time.strftime("%Y-%m-%d"),
                              **(json.loads(side.read_text(encoding="utf-8")) if side else {})}
            (dst / "ficha.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
            cru[tipo][nome] = {"elenco": ident}
            salvos += 1
            print(f"  {tipo[:-1]} {nome} -> elenco/{tipo}/{ident}")
    P.salvar(pasta, cru)
    print(f"{salvos} ficha(s) guardadas no elenco")


# ------------------------------------------------------------------------------------------ planos
def planos(pasta, proj, a):
    from kaggle_cenas import gerar_lote
    estilo = proj.get("estilo", "")
    pers, cens = proj.get("personagens", {}), proj.get("cenarios", {})
    W, H = proj.get("tamanho_plano", [768, 1344])
    # correções do revisor (agente revisor-cenas): refaz as reprovadas com a instrução de pose que ele sugeriu
    correcoes = {}
    if a.refazer_revisao:
        por_img = {Path(p["imagem"]).name: p["id"] for p in proj["planos"] if p.get("prompt")}
        for rj in sorted((pasta / "planos").glob("revisao*.json")):
            for r in json.loads(rj.read_text(encoding="utf-8")).get("reprovadas", []):
                pid = r.get("plano") or por_img.get(Path(r["imagem"]).name)
                if pid:
                    correcoes[pid] = r.get("refazer_com", "")
        print(f"revisão: refazendo {len(correcoes)} plano(s) reprovado(s): {', '.join(correcoes)}")
    pend = {p["id"]: p for p in proj["planos"]
            if p.get("prompt") and not p.get("composicao")
            and (not (pasta / p["imagem"]).exists() or p["id"] in a.refazer or p["id"] in correcoes)}
    tent = pasta / "planos" / "tentativas"
    for rodada in range(1, a.rodadas + 1):
        if not pend:
            break
        itens, cfg = [], {}
        for pid, p in pend.items():
            # referência de pose primeiro (o klein copia a pose em vez de inventar), depois cenário e personagens
            pose = [pasta / p["pose"]] if p.get("pose") else []
            # "sem_referencia": personagens só pela descrição (pose muito diferente da ficha => sairia duplicado)
            sem_ref = set(p.get("sem_referencia", []))
            # "base": plano JÁ APROVADO que é EDITADO (acrescentar UM personagem por vez): continuidade garantida
            base = None
            if p.get("base"):
                bp = next(x for x in proj["planos"] if x["id"] == p["base"])
                base = pasta / bp["imagem"]
                ja = set(bp.get("personagens", []))
                refs = [base] + [pasta / pers[q]["ficha"] for q in p.get("personagens", []) if q not in ja and q not in sem_ref]
            else:
                refs = pose + ([pasta / cens[p["cenario"]]["ficha"]] if p.get("cenario") else []) + \
                       [pasta / pers[q]["ficha"] for q in p.get("personagens", []) if q not in sem_ref]
            descr = " ".join(f"{pers[q]['descricao']}." for q in p.get("personagens", []))
            extra = (" Copy the exact body pose from the first reference image." if pose else "") + \
                    (f" Anatomy: {correcoes[pid]}." if correcoes.get(pid) else "") + \
                    " Correct anatomy: each person has exactly two arms (one on each side) and two hands."
            # animal + pessoas na mesma cena: a cauda "vaza" para a pessoa e o animal duplica (regra por espécie)
            animais = [q for q in p.get("personagens", []) if not pers.get(q, {}).get("humano", True)]
            if animais and len(animais) < len(p.get("personagens", [])):
                especies = sorted({pers[q].get("especie", "animal") for q in animais})
                cada = " and ".join(f"ONE {e}" for e in especies)
                extra += (f" Exactly {cada} in the whole scene, never duplicated. Only the {'/'.join(especies)} "
                          f"has a tail and fur; the people have NO tail, no fur and no animal features.")
            if base is not None:
                extra = (" Keep image 1 exactly as it is: same room, same composition, and every character already "
                         "in image 1 stays identical in the same place and pose. Only add what is described." + extra)
            itens.append({"nome": pid, "prompt": f"{estilo} {descr} Scene: {p['prompt']}.{extra}", "imagens": refs[:4],
                          "sementes": [random.randint(1, 2**31 - 1) for _ in range(a.versoes)],
                          "largura": W, "altura": H})
            alvo = p.get("checar", "estilo")
            if alvo != "estilo" and pers.get(alvo, {}).get("humano", True):
                cfg[pid] = {"modo": "rosto", "padroes": [pasta / pers[alvo]["ficha"]]}
            else:
                cfg[pid] = {"modo": "estilo", "padroes": (refs[len(pose):] or refs)[:2]}
        print(f"rodada {rodada}: {len(itens)} plano(s)", flush=True)
        if a.so_fiscal and rodada == 1:
            arquivos = sorted(tent.glob("*.png"))
        else:
            arquivos, _ = gerar_lote(itens, tent, motor="klein")
        novos = [x for x in arquivos if any(x.name.startswith(pid + "_s") for pid in pend)]
        from conferencia import detalhes
        detalhes(novos, pasta / "planos" / "detalhes")           # recortes ampliados para o revisor
        if not a.com_fiscal:
            # padrão (28/09/2026): o fiscal automático é lento e não pega anatomia; quem escolhe é o revisor-cenas
            lista = [{"plano": pid, "mostra": pend[pid]["prompt"], "personagens": pend[pid].get("personagens", []),
                      "cenario": pend[pid].get("cenario"), "base": pend[pid].get("base"),
                      "candidatos": sorted(x.name for x in novos if x.name.startswith(pid + "_s"))} for pid in pend]
            (pasta / "planos" / "para_revisao.json").write_text(json.dumps(lista, ensure_ascii=False, indent=1),
                                                                 encoding="utf-8")
            print(f"PRÓXIMO: agente revisor-cenas com planos/para_revisao.json (recortes em planos/detalhes/); "
                  f"ele grava planos/revisao_N.json; depois: produzir.py {pasta.name} escolhas")
            return
        for pid in list(pend):
            cfg[pid]["candidatos"] = sorted(x for x in novos if x.name.startswith(pid + "_s"))
        res = fiscalizar_lote({k: v for k, v in cfg.items() if v["candidatos"]})
        with open(pasta / "fiscal_log.jsonl", "a", encoding="utf-8") as f:
            for pid, r in res.items():
                for v in r["vereditos"]:
                    f.write(json.dumps({**v, "plano": pid, "rodada": rodada}, ensure_ascii=False) + "\n")
                if r["aprovada"]:
                    shutil.copy2(r["aprovada"], pasta / pend[pid]["imagem"])
                    del pend[pid]


def escolhas(pasta, proj, a):
    """Instala as versões escolhidas pelo revisor, grava o manifesto (de onde veio cada imagem) e a folha."""
    tent = pasta / "planos" / "tentativas"
    manif_p = pasta / "planos" / "manifesto.json"
    manif = json.loads(manif_p.read_text(encoding="utf-8")) if manif_p.exists() else {}
    imgs = {p["id"]: p["imagem"] for p in proj["planos"]}
    feitos, reprov = 0, []
    for rj in sorted((pasta / "planos").glob("revisao*.json")):
        rev = json.loads(rj.read_text(encoding="utf-8"))
        for pid, arq in rev.get("escolhas", {}).items():
            if pid in imgs and (tent / arq).exists():
                shutil.copy2(tent / arq, pasta / imgs[pid]); feitos += 1
                side = tent / (Path(arq).stem + ".json")
                sem = re.search(r"_s(\d+)\.png$", arq)
                manif[pid] = {"arquivo": arq, "semente": int(sem.group(1)) if sem else None, "revisao": rj.name,
                              **(json.loads(side.read_text(encoding="utf-8")) if side.exists() else {})}
        reprov += [r.get("plano") or Path(r["imagem"]).stem for r in rev.get("reprovadas", [])
                   if (r.get("plano") or Path(r["imagem"]).stem) not in rev.get("escolhas", {})]
    manif_p.write_text(json.dumps(manif, ensure_ascii=False, indent=1), encoding="utf-8")
    # arquiva as revisões já aplicadas (o próximo --refazer-revisao só vê as novas)
    (pasta / "planos" / "revisoes_aplicadas").mkdir(exist_ok=True)
    for rj in (pasta / "planos").glob("revisao*.json"):
        shutil.move(str(rj), str(pasta / "planos" / "revisoes_aplicadas" / f"{time.strftime('%Y%m%d_%H%M%S')}_{rj.name}"))
    from conferencia import folha
    aprovadas = sorted({pasta / p["imagem"] for p in proj["planos"] if (pasta / p["imagem"]).exists()})
    f = folha(aprovadas, pasta / "planos" / "folha_planos.jpg", colunas=8)
    print(f"{feitos} plano(s) instalados; manifesto em {manif_p.name}; folha em {f}")
    if reprov:
        print(f"reprovados ({len(set(reprov))}): {', '.join(sorted(set(reprov)))} -> planos --refazer-revisao "
              f"(copie antes as reprovações para planos/revisao_*.json)")


def compor(pasta, proj, a):
    """Refaz os planos montados por composição: personagem recortado de um plano aprovado e colado em outro."""
    for p in proj["planos"]:
        c = p.get("composicao")
        if not c or ((pasta / p["imagem"]).exists() and p["id"] not in a.refazer and not a.refazer_tudo):
            continue
        cmd = [MAOS_PY, str(AQUI / "sobrepor.py"), str(pasta / c["origem"]), ",".join(map(str, c["caixa"])),
               str(pasta / c["sobre"]), str(pasta / p["imagem"]), "--posicao", ",".join(map(str, c["posicao"])),
               "--escala", str(c.get("escala", 1.0))] + (["--espelhar"] if c.get("espelhar") else [])
        subprocess.run(cmd, check=True)
        print(f"  {p['id']}: composto")


# ------------------------------------------------------------------------------------------ vídeo
def falas(pasta, proj, a):
    linha = json.loads((pasta / proj["linha_do_tempo"]).read_text(encoding="utf-8"))["falas"]
    cru = P.carregar(pasta, resolver=False)
    (pasta / "falando").mkdir(exist_ok=True)
    for p, pc in zip(proj["planos"], cru["planos"]):
        novos = []
        for k, f in enumerate(p.get("fala", [])):
            ln = linha[f["linha"]]
            ini, fim = max(ln["inicio"] - 0.12, 0), ln["fim"] + 0.25
            wav, mp4 = pasta / "falando" / f"{p['id']}_{k}.wav", pasta / "falando" / f"{p['id']}_{k}.mp4"
            if not mp4.exists() or p["id"] in a.refazer:
                subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{ini:.3f}", "-to", f"{fim:.3f}",
                                "-i", str(pasta / proj["audio"]), "-ac", "1", "-ar", "24000", str(wav)], check=True)
                cmd = [JOY_PY, FALAR, str(pasta / p["imagem"]), str(wav), str(mp4)]
                if f.get("rosto"):
                    cmd += ["--rosto", f["rosto"]]
                if f.get("regiao"):
                    cmd += ["--regiao", ",".join(map(str, f["regiao"]))]
                print(f"{p['id']} fala {k}: {ln['quem']} '{ln['texto'][:40]}'", flush=True)
                r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
                if r.returncode != 0:
                    print("   falhou:", (r.stderr or r.stdout)[-300:]); continue
            novos.append({"video": f"falando/{mp4.name}", "inicio": round(ini, 3)})
        if p.get("fala"):
            pc["falas"] = novos
    P.salvar(pasta, cru)


def montar(pasta, proj, a):
    subprocess.run([sys.executable, str(AQUI / "montar.py"), str(pasta)] + (["--rascunho"] if a.rascunho else []),
                   check=True)


ETAPAS = ["novo", "alinhar", "status", "fichas", "elenco", "planos", "escolhas", "compor", "falas", "montar"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("historia"); ap.add_argument("etapa", choices=ETAPAS)
    ap.add_argument("--roteiro"); ap.add_argument("--audio"); ap.add_argument("--titulo")
    ap.add_argument("--estilo", default="livro_aquarela"); ap.add_argument("--musica")
    ap.add_argument("--refazer", nargs="*", default=[])
    ap.add_argument("--refazer-tudo", action="store_true", help="compor: refaz todas as composições")
    ap.add_argument("--refazer-revisao", action="store_true", help="planos: refaz os reprovados em planos/revisao*.json")
    ap.add_argument("--opcoes", type=int, default=4, help="fichas: opções de cada personagem/cenário")
    ap.add_argument("--versoes", type=int, default=1, help="planos: versões por plano e rodada")
    ap.add_argument("--rodadas", type=int, default=1)
    ap.add_argument("--rascunho", action="store_true")
    ap.add_argument("--com-fiscal", action="store_true", help="planos: usa o fiscal automático (lento, sem anatomia)")
    ap.add_argument("--so-fiscal", action="store_true", help="planos: só julga o que já está em tentativas/")
    ap.add_argument("--ids", nargs="*", help="elenco: nome_na_historia=id_no_elenco (ex.: lobo=lobo_mau)")
    a = ap.parse_args()
    pasta = pasta_da(a.historia)
    t = time.time()
    proj = {} if a.etapa == "novo" else P.carregar(pasta)
    globals()[a.etapa](pasta, proj, a)
    print(f"[{a.etapa}] {(time.time() - t) / 60:.1f} min")


if __name__ == "__main__":
    main()
