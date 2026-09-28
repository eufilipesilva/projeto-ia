"""Esteira do Estúdio de Animação: de um projeto.json (roteiro + áudio + storyboard) ao vídeo pronto.

    F:\\Projeto IA\\.venv_omni\\Scripts\\python.exe produzir.py PASTA_DO_PROJETO ETAPA [opções]

Etapas (nesta ordem; cada uma retoma de onde parou):
  alinhar  roteiro.txt + audio.wav -> linha_do_tempo.json (quem fala, quando, palavra a palavra)
  fichas   desenha personagens e cenários do zero (FLUX.2 klein no Kaggle), N opções de cada, em
           fichas/opcoes/. O FILIPE ESCOLHE: copie a escolhida para o caminho "ficha" do projeto.json
           (ex.: fichas/chapeu.png). Só gera o que ainda não tem ficha.
  planos   gera cada plano com as fichas como referência (até 4 por plano) e o fiscal escolhe; só gera os
           planos que ainda não têm imagem. --refazer p07 p12 força.
  falas    corta o áudio de cada fala marcada nos planos e anima o rosto de quem fala (falar.py);
           opcional: histórias com narradora por trás não marcam "fala" e pulam esta etapa

Anatomia (mãos, braços, caudas) NÃO é pega pelo fiscal: depois de fichas e de planos, rode o agente
revisor-cenas (.claude/agents/revisor-cenas.md), que grava revisao.json; "planos --refazer-revisao" refaz só as
reprovadas com a correção de pose dele. Um plano pode ter "pose": "poses/x.png" (imagem com a pose certa), que
vira a 1ª referência do gerador: ele copia a pose em vez de inventar.
  montar   monta o vídeo (montar.py); --rascunho para uma prévia rápida

projeto.json, além do que o montar.py usa:
  "estilo": "texto de estilo que vai em TODO prompt",
  "tamanho_plano": [768, 1344],                        # geração (vertical 9:16); a montagem amplia
  "personagens": {"chapeu": {"descricao": "...", "ficha": "fichas/chapeu.png", "humano": true}},
  "cenarios":    {"casa":   {"descricao": "...", "ficha": "fichas/casa.png"}},
  "planos": [{"id": "p09", "inicio": 47.82, "imagem": "planos/p09.png", "cenario": "floresta",
              "personagens": ["lobo", "chapeu"], "prompt": "o que acontece no plano",
              "checar": "chapeu" | "estilo",
              "fala": [{"linha": 10, "rosto": "esquerda"}]}]    # índices em linha_do_tempo.json["falas"]
"""
import argparse, json, random, shutil, subprocess, sys, time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "cenas")); sys.path.insert(0, str(AQUI))
JOY_PY = r"F:\Projeto IA\ferramentas\JoyVASA\.venv\Scripts\python.exe"
FISCAL = str(AQUI.parent / "cenas" / "fiscal.py")
FALAR = str(AQUI.parent / "visemas" / "falar.py")


def carregar(pasta):
    return json.loads((pasta / "projeto.json").read_text(encoding="utf-8"))


def salvar(pasta, proj):
    (pasta / "projeto.json").write_text(json.dumps(proj, ensure_ascii=False, indent=1), encoding="utf-8")


def fiscalizar_lote(cenas):
    """Uma chamada do fiscal para a rodada inteira. cenas = {nome: {"candidatos", "padroes", "modo"}}."""
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


# ------------------------------------------------------------------------------------------ etapas
def alinhar(pasta, proj, a):
    subprocess.run([sys.executable, str(AQUI / "alinhar.py"), str(pasta / proj.get("roteiro", "roteiro.txt")),
                    str(pasta / proj["audio"]), str(pasta / proj["linha_do_tempo"])], check=True)


def fichas(pasta, proj, a):
    from kaggle_cenas import gerar_lote
    estilo = proj.get("estilo", "")
    itens = []
    for grupo, fundo in (("personagens", "full body, standing, simple plain light background, character design sheet"),
                         ("cenarios", "wide establishing shot, no people")):
        for nome, d in proj.get(grupo, {}).items():
            if d.get("ficha") and (pasta / d["ficha"]).exists() and nome not in a.refazer:
                continue
            if d.get("ref") and not (pasta / d["ref"]).exists():
                print(f"  {nome}: espera a ficha {d['ref']} ser escolhida (é a referência dele); rode de novo depois")
                continue
            W, H = proj.get("tamanho_plano", [768, 1344])
            itens.append({"nome": f"{grupo[:4]}_{nome}", "prompt": f"{estilo} {d['descricao']}. {fundo}.",
                          "imagens": [pasta / d["ref"]] if d.get("ref") else [],
                          "sementes": [random.randint(1, 2**31 - 1) for _ in range(a.opcoes)],
                          "largura": W, "altura": H})
    if not itens:
        print("todas as fichas já existem"); return
    destino = pasta / "fichas" / "opcoes"
    arquivos, _ = gerar_lote(itens, destino, motor="klein")
    from conferencia import folha
    f = folha(sorted(arquivos), pasta / "fichas" / "folha_conferencia.jpg")
    print(f"\nopções em {destino}. Escolha uma de cada e copie para o caminho 'ficha' do projeto.json.")
    print(f"PRÓXIMO: rode o agente revisor-cenas (etapa fichas); ele lê {f}, aponta defeitos de anatomia\n"
          f"(o fiscal não pega) e sugere a melhor opção de cada item em fichas/revisao.json.")


def planos(pasta, proj, a):
    from kaggle_cenas import gerar_lote
    estilo = proj.get("estilo", "")
    pers, cens = proj.get("personagens", {}), proj.get("cenarios", {})
    W, H = proj.get("tamanho_plano", [768, 1344])
    # correções do revisor (agente revisor-cenas): refaz as reprovadas com a instrução de pose que ele sugeriu
    correcoes = {}
    if a.refazer_revisao and (pasta / "planos" / "revisao.json").exists():
        rev = json.loads((pasta / "planos" / "revisao.json").read_text(encoding="utf-8"))
        por_img = {Path(p["imagem"]).name: p["id"] for p in proj["planos"] if p.get("prompt")}
        for r in rev.get("reprovadas", []):
            pid = por_img.get(Path(r["imagem"]).name)
            if pid:
                correcoes[pid] = r.get("refazer_com", "")
        print(f"revisão: refazendo {len(correcoes)} plano(s) reprovado(s): {', '.join(correcoes)}")
    pend = {p["id"]: p for p in proj["planos"]
            if p.get("prompt") and (not (pasta / p["imagem"]).exists() or p["id"] in a.refazer or p["id"] in correcoes)}
    tent = pasta / "planos" / "tentativas"
    for rodada in range(1, a.rodadas + 1):
        if not pend:
            break
        itens, cfg = [], {}
        for pid, p in pend.items():
            # referência de pose primeiro (o klein copia a pose em vez de inventar), depois cenário e personagens
            pose = [pasta / p["pose"]] if p.get("pose") else []
            refs = pose + ([pasta / cens[p["cenario"]]["ficha"]] if p.get("cenario") else []) + \
                   [pasta / pers[q]["ficha"] for q in p.get("personagens", [])]
            descr = " ".join(f"{pers[q]['descricao']}." for q in p.get("personagens", []))
            extra = (" Copy the exact body pose from the first reference image." if pose else "") + \
                    (f" Anatomy: {correcoes[pid]}." if correcoes.get(pid) else "") + \
                    " Correct anatomy: each person has exactly two arms (one on each side) and two hands."
            itens.append({"nome": pid, "prompt": f"{estilo} {descr} Scene: {p['prompt']}.{extra}", "imagens": refs[:4],
                          "sementes": [random.randint(1, 2**31 - 1) for _ in range(a.versoes)],
                          "largura": W, "altura": H})
            alvo = p.get("checar", "estilo")
            if alvo != "estilo" and pers.get(alvo, {}).get("humano", True):
                cfg[pid] = {"modo": "rosto", "padroes": [pasta / pers[alvo]["ficha"]]}
            else:
                cfg[pid] = {"modo": "estilo", "padroes": (refs[len(pose):] or refs)[:2]}   # a pose não é padrão de estilo
        print(f"rodada {rodada}: {len(itens)} plano(s)", flush=True)
        arquivos, _ = gerar_lote(itens, tent, motor="klein")
        for pid in list(pend):
            cfg[pid]["candidatos"] = sorted(x for x in arquivos if x.name.startswith(pid + "_s"))
        res = fiscalizar_lote({k: v for k, v in cfg.items() if v["candidatos"]})
        with open(pasta / "fiscal_log.jsonl", "a", encoding="utf-8") as f:
            for pid, r in res.items():
                for v in r["vereditos"]:
                    f.write(json.dumps({**v, "plano": pid, "rodada": rodada}, ensure_ascii=False) + "\n")
                if r["aprovada"]:
                    (pasta / pend[pid]["imagem"]).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(r["aprovada"], pasta / pend[pid]["imagem"])
                    del pend[pid]
    for pid in pend:
        print(f"  {pid}: nenhuma versão passou; veja planos/tentativas/")
    from conferencia import folha
    aprovadas = sorted({pasta / p["imagem"] for p in proj["planos"] if (pasta / p["imagem"]).exists()})
    f = folha(aprovadas, pasta / "planos" / "folha_conferencia.jpg")
    print(f"PRÓXIMO: rode o agente revisor-cenas nesta pasta (etapa planos); ele lê {f} e grava planos/revisao.json.\n"
          f"Depois: produzir.py PASTA planos --refazer-revisao")


def falas(pasta, proj, a):
    linha = json.loads((pasta / proj["linha_do_tempo"]).read_text(encoding="utf-8"))["falas"]
    (pasta / "falando").mkdir(exist_ok=True)
    for p in proj["planos"]:
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
            p["falas"] = novos
    salvar(pasta, proj)


def montar(pasta, proj, a):
    subprocess.run([sys.executable, str(AQUI / "montar.py"), str(pasta)] + (["--rascunho"] if a.rascunho else []),
                   check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pasta"); ap.add_argument("etapa", choices=["alinhar", "fichas", "planos", "falas", "montar"])
    ap.add_argument("--refazer", nargs="*", default=[])
    ap.add_argument("--refazer-revisao", action="store_true",
                    help="planos: refaz os reprovados no planos/revisao.json do agente revisor-cenas")
    ap.add_argument("--opcoes", type=int, default=4, help="fichas: opções de cada personagem/cenário")
    ap.add_argument("--versoes", type=int, default=2, help="planos: versões por plano e rodada")
    ap.add_argument("--rodadas", type=int, default=3)
    ap.add_argument("--rascunho", action="store_true")
    a = ap.parse_args()
    pasta = Path(a.pasta).resolve()
    t = time.time()
    globals()[a.etapa](pasta, carregar(pasta), a)
    print(f"[{a.etapa}] {(time.time() - t) / 60:.1f} min")


if __name__ == "__main__":
    main()
