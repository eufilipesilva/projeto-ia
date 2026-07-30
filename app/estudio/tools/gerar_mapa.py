# -*- coding: utf-8 -*-
"""Gerador do censo do MAPA_FUNCOES.html.

Escaneia o código DE VERDADE (AST para .py, regex para o JS do index.html),
reconstrói a seção "Censo completo" do mapa entre os marcadores
<!-- CENSO:INICIO --> ... <!-- CENSO:FIM -->, atualiza o total e reporta no
console o que mudou (funções novas/removidas) desde a última geração.

Também confere se as funções citadas com "()" nas partes CURADAS do mapa
(diagrama e passo a passo) ainda existem no código — pega renomeações.

Uso:
    python tools/gerar_mapa.py            # atualiza o HTML
    python tools/gerar_mapa.py --check    # só relatório, não escreve

Função nova sem categoria vai pro grupo "🆕 sem categoria" — categorize-a em
CATEGORIAS abaixo quando der (o mapa continua completo mesmo sem isso).
"""
import ast, os, re, sys, html

sys.stdout.reconfigure(encoding="utf-8")
ESTUDIO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAIZ    = os.path.dirname(os.path.dirname(ESTUDIO))          # f:\Projeto IA
LAB     = os.path.join(RAIZ, "app", "laboratorios")
MAPA    = os.path.join(ESTUDIO, "MAPA_FUNCOES.html")

# ── Arquivos escaneados: (caminho, rótulo, classe-de-cor) ────────────────────
ARQUIVOS_PY = [
    (os.path.join(ESTUDIO, "motor_v2.py"),      "motor_v2.py",      "motor"),
    (os.path.join(ESTUDIO, "estudio_web.py"),   "estudio_web.py",   "web"),
    (os.path.join(ESTUDIO, "canto_musica.py"),  "canto_musica.py",  "canto"),
    (os.path.join(ESTUDIO, "canto_lote.py"),    "canto_lote.py",    "canto"),
    (os.path.join(ESTUDIO, "parodia.py"),       "parodia.py",       "motor"),
    (os.path.join(LAB, "seed-vc", "inference.py"),      "seed-vc/inference.py",      "seed"),
    (os.path.join(LAB, "seed-vc", "converter_lote.py"), "seed-vc/converter_lote.py", "seed"),
]
INDEX_HTML = os.path.join(ESTUDIO, "static", "index.html")

# ── Categorias curadas (subgrupos por arquivo). Nova função sem categoria
#    aparece em "🆕 sem categoria" — o censo nunca perde nada. ────────────────
CATEGORIAS = {
    "motor_v2.py": {
        "modelos & VRAM": ["_esperar_vram_livre", "carregar_omni", "descarregar_omni",
                            "_cfg", "_gemma", "descarregar_gemma"],
        "perfis & prompts de voz": ["estimar_ritmo", "perfil_voz", "perfil_de_design",
                            "_criar_prompt_voz", "_carregar_prompts_emocao",
                            "interpretar_descricao_voz", "_dedup_instruct"],
        "síntese": ["_gerar_um", "sintetizar_clone", "sintetizar_clone_lote",
                    "sintetizar_clone_pandora", "sintetizar_design",
                    "sintetizar_historia", "sintetizar_comedia"],
        "roteiros (Gemma)": ["_limpar_roteiro", "gerar_roteiro_comedia",
                    "gerar_gameshow_educativo", "gerar_gameshow_duelo",
                    "destilar_conteudo", "ler_pdf_completo", "_ler_pdf",
                    "gerar_roteiro_trailer", "gerar_meditacao", "gerar_radio",
                    "gerar_batalha", "gerar_batalha_persona", "responder_personagem",
                    "gerar_livro_capitulos", "gerar_temporada"],
        "beats & classificação": ["_achar_emocao", "_split_frases", "_beats_historia",
                    "_beats_comedia", "_ascii1", "_norm_nome", "_primeiro_nome",
                    "_falante_da_tag", "_quem_fala_gemma", "_classificar_beats",
                    "_emocao_lote", "_classificar_sfx", "_normalizar_fala", "_com_ponto"],
        "DSP & montagem": ["_pitch", "_rms", "_envelope", "_fade_in_cos", "_fade_exp",
                    "_zcr", "finalizar", "_roomtone", "_sussurro", "_brilho", "_tremolo",
                    "_eco", "_montar", "_carregar_fundo", "_misturar_fundo",
                    "_caimento_pandora", "_binaural_widen", "_saida", "salvar"],
        "sonoplastia (SFX)": ["_norm_sfx", "_catalogo_sfx", "_carregar_sfx", "_montar_comedia"],
    },
    "estudio_web.py": {
        "infra & tasks": ["_save_audio", "_perfil_de_voz", "_avaliar_meditacao",
                    "_parse_bool", "_audio_response", "_prog_fn", "_executar_tarefa",
                    "_worker_loop", "_podar_tasks", "_varrer_tmp_antigos", "_run_task",
                    "_new_task", "_salvar_upload", "_resolver_voz_ref", "_ler_texto_upload"],
        "rotas": ["status", "listar_vozes", "preview_voz", "task_status", "task_audio",
                    "task_audio_lote", "analisar_voz", "gerar_clone", "gerar_canto",
                    "gerar_canto_lote", "gerar_design", "gerar_historia", "gerar_comedia",
                    "roteiro_aleatorio", "ler_pdf", "gerar_gameshow", "gerar_trailer",
                    "gerar_meditacao", "gerar_radio", "gerar_batalha", "criar_personagem",
                    "listar_personagens", "conversar", "resetar_historico", "index"],
    },
}

def defs_python(path):
    """Nomes das funções top-level de um .py, na ordem de definição."""
    with open(path, encoding="utf-8") as f:
        arvore = ast.parse(f.read())
    return [n.name for n in arvore.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]

def defs_js(path):
    """Funções `function nome(` do index.html (inclui as aninhadas), sem repetir."""
    with open(path, encoding="utf-8") as f:
        src = f.read()
    vistos, nomes = set(), []
    for m in re.finditer(r"(?:async\s+)?function\s+([A-Za-z_$][\w$]*)", src):
        if m.group(1) not in vistos:
            vistos.add(m.group(1)); nomes.append(m.group(1))
    return nomes

def render_grupo(rotulo, cor, titulo, funcoes):
    corpo = " · ".join(html.escape(f) for f in funcoes)
    return (f'    <div class="grupo {cor}"><h3>{html.escape(rotulo)} · {html.escape(titulo)} '
            f'<em>{len(funcoes)}</em></h3>\n      <p>{corpo}</p></div>')

def main():
    so_checar = "--check" in sys.argv

    # 1) escaneia tudo
    censo = []          # [(rotulo, cor, titulo_grupo, [funcoes])]
    todas = set()
    for path, rotulo, cor in ARQUIVOS_PY:
        fns = defs_python(path)
        todas.update(fns)
        cats = CATEGORIAS.get(rotulo)
        if cats:
            sobras = [f for f in fns if not any(f in v for v in cats.values())]
            for titulo, lista in cats.items():
                presentes = [f for f in lista if f in fns]   # some se foi removida
                if presentes:
                    censo.append((rotulo, cor, titulo, presentes))
            if sobras:
                censo.append((rotulo, cor, "🆕 sem categoria", sobras))
        else:
            censo.append((rotulo, cor, "funções", fns))
    js = defs_js(INDEX_HTML)
    todas.update(js)
    censo.append(("index.html", "front", "JavaScript", js))
    total = sum(len(fns) for _, _, _, fns in censo)

    # 2) lê o mapa e compara com o censo anterior (o que estava publicado)
    with open(MAPA, encoding="utf-8") as f:
        pagina = f.read()
    ini, fim = "<!-- CENSO:INICIO", "<!-- CENSO:FIM -->"
    i1, i2 = pagina.find(ini), pagina.find(fim)
    if i1 < 0 or i2 < 0:
        print("ERRO: marcadores CENSO:INICIO/FIM não encontrados no MAPA_FUNCOES.html")
        sys.exit(1)
    bloco_antigo = pagina[i1:i2]
    antigas = set(re.findall(r"[\w$]+", re.sub(r"<[^>]+>", " ", bloco_antigo)))
    novas_fns = sorted(f for f in todas if f not in antigas)
    # removidas: nomes com cara de função (têm "_" ou estão na whitelist de nomes
    # simples) que estavam no censo publicado mas sumiram do código.
    # _ARQUIVOS: stems de nomes de arquivo que aparecem nos títulos dos grupos.
    _SIMPLES  = {"toast", "conversar", "desenhar", "draw", "play", "stop", "index",
                 "status", "salvar", "finalizar", "mixar", "main", "rimam"}
    _ARQUIVOS = {"motor_v2", "estudio_web", "canto_musica", "canto_lote",
                 "converter_lote", "parodia", "inference", "index", "html", "py", "js"}
    removidas = sorted(f for f in antigas - todas
                       if re.fullmatch(r"[a-z_$][\w$]*", f) and f not in _ARQUIVOS
                       and ("_" in f or f in _SIMPLES))

    # 3) confere as partes CURADAS: toda "funcao()" citada ainda existe?
    # Só nomes com "_" ou da whitelist (evita builtins do JS do próprio mapa,
    # tipo Set()/getBoundingClientRect(), que apareceriam como falso positivo).
    curado = pagina[:i1] + pagina[i2:]
    citadas = set(re.findall(r"([A-Za-z_$][\w$]*)\(\)", re.sub(r"<[^>]+>", " ", curado)))
    quebradas = sorted(c for c in citadas
                       if c not in todas and ("_" in c.strip("_") or c in _SIMPLES))

    # 4) monta o bloco novo e grava
    linhas = [f"{ini} (gerado automaticamente — NÃO editar à mão; rode tools/gerar_mapa.py) -->",
              '  <div class="censo">']
    linhas += [render_grupo(r, c, t, fns) for r, c, t, fns in censo]
    linhas.append("  </div>\n  ")
    bloco_novo = "\n".join(linhas)
    pagina_nova = pagina[:i1] + bloco_novo + pagina[i2:]
    pagina_nova = re.sub(r'(<span data-total>)\d+(</span>)', rf'\g<1>{total}\g<2>', pagina_nova)
    pagina_nova = re.sub(r'(Censo completo — todas as (?:<span data-total>)?)\d+',
                         rf'\g<1>{total}', pagina_nova) if '<span data-total>' not in pagina_nova else pagina_nova

    # 5) relatório
    print(f"Censo: {total} funções em {len(ARQUIVOS_PY)+1} arquivos.")
    if novas_fns:  print(f"  🆕 novas desde a última geração: {', '.join(novas_fns)}")
    if removidas:  print(f"  ➖ sumiram do código: {', '.join(removidas)}")
    if not novas_fns and not removidas: print("  (sem mudanças no inventário)")
    if quebradas:
        print(f"  ⚠ citadas no diagrama/passo-a-passo mas INEXISTENTES no código: {', '.join(quebradas)}")
        print("    → atualize as seções curadas do mapa (renomeação?).")

    if so_checar:
        print("(--check: nada gravado)")
        return
    with open(MAPA, "w", encoding="utf-8") as f:
        f.write(pagina_nova)
    print(f"OK: {os.path.relpath(MAPA, RAIZ)} atualizado.")

if __name__ == "__main__":
    main()
