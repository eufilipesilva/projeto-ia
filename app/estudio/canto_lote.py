# -*- coding: utf-8 -*-
"""Cantar Música em LOTE: processa várias músicas de uma vez reaproveitando ao
máximo o custo fixo de cada etapa.

Ganho principal: o seed-vc carrega os modelos (~60s) UMA vez pro lote inteiro,
em vez de uma vez por música. Numa fila de N músicas isso economiza ~60s×(N-1).

Reaproveita as funções já otimizadas de `canto_musica.py` (separação com vocal
em memória, cálculo de pitch rápido, mixagem, limpeza). O fluxo é:
  1. Demucs separa TODAS as músicas (venv deste processo).
  2. Um único subprocess do seed-vc converte TODOS os vocais (modelos 1x).
  3. Mixa cada voz convertida com seu instrumental e salva o resultado final.
"""
import os, json, uuid, subprocess
import soundfile as sf
import canto_musica as cm


def gerar_canto_lote(caminhos_musicas, voz_referencia_path, pasta_saida,
                     diffusion_steps=50, vol_instrumental=0.6, inference_cfg_rate=0.7,
                     auto_f0_adjust=False, semi_tone_shift="auto", ajuste_fino=0,
                     progresso=lambda *a: None):
    """Processa uma lista de músicas com a mesma voz de referência. Salva um wav
    final por música em `pasta_saida` e retorna uma lista de dicts:
    {"musica": caminho, "saida": caminho|None, "ok": bool, "erro": str|None}.

    Os parâmetros de conversão são os mesmos de `canto_musica.gerar_canto`; ver
    lá a explicação de cada um. Uma faixa que falhar não derruba o lote."""
    # O seed-vc roda noutro cwd (SEEDVC_DIR); caminhos relativos não
    # resolveriam lá. Absolutiza tudo antes de montar o JSON de trabalhos.
    voz_referencia_path = os.path.abspath(voz_referencia_path)
    caminhos_musicas = [os.path.abspath(m) for m in caminhos_musicas]
    pasta_saida = os.path.abspath(pasta_saida)
    os.makedirs(pasta_saida, exist_ok=True)
    total = len(caminhos_musicas)

    progresso(0.02, "Liberando VRAM (descarregando OmniVoice)...")
    import motor_v2 as motor
    motor.descarregar_omni()

    # ── Fase 1: separar todas as músicas (Demucs) ───────────────────────────
    itens = []       # metadados por faixa que deu certo na separação
    trabalhos = []   # o que vai no JSON pro seed-vc
    resultados = []  # relatório final (inclui as que falharam)
    for i, musica in enumerate(caminhos_musicas, 1):
        base = os.path.splitext(os.path.basename(musica))[0]
        progresso(0.05 + 0.25 * (i - 1) / max(total, 1),
                  f"[{i}/{total}] Separando vocal de '{base}'...")
        try:
            vocal_path, inst_path, vocal_y, sr = cm.separar_vocal_instrumental(musica)
            if semi_tone_shift == "auto":
                shift = cm._limitar_shift(cm.calcular_semi_tone_shift(vocal_y, sr, voz_referencia_path))
            else:
                shift = int(semi_tone_shift)
            shift += int(ajuste_fino)
            vc_out = os.path.join(cm.TMP_DIR, f"{uuid.uuid4().hex}_vc.wav")
            trabalhos.append({"source": vocal_path, "output": vc_out, "pitch_shift": shift})
            itens.append({"musica": musica, "base": base, "vocal_path": vocal_path,
                          "inst_path": inst_path, "vc_out": vc_out})
        except Exception as e:
            resultados.append({"musica": musica, "saida": None, "ok": False, "erro": str(e)})

    if not trabalhos:
        return resultados

    # ── Fase 2: um subprocess seed-vc converte todos os vocais ──────────────
    # teto de belting: depende só da voz-alvo (mesma pro lote), calcula 1x
    teto = cm.calcular_teto_pitch(voz_referencia_path) or 0
    spec = {
        "target": voz_referencia_path,
        "diffusion_steps": diffusion_steps,
        "inference_cfg_rate": inference_cfg_rate,
        "auto_f0_adjust": bool(auto_f0_adjust),
        "teto_midi": teto,
        "suavizar_janela": cm._SUAVIZAR_JANELA,
        "trabalhos": trabalhos,
    }
    json_path = os.path.join(cm.TMP_DIR, f"lote_{uuid.uuid4().hex}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False)

    env = os.environ.copy()
    env["PATH"] = cm.FFMPEG_DIR + os.pathsep + env.get("PATH", "")
    cmd = [cm.SEEDVC_PYTHON, os.path.join(cm.SEEDVC_DIR, "converter_lote.py"), json_path]
    proc = subprocess.Popen(cmd, cwd=cm.SEEDVC_DIR, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, bufsize=1)
    n = len(trabalhos)
    erros_subprocess = []
    for linha in proc.stdout:
        linha = linha.strip()
        if linha.startswith("PROGRESSO "):
            try:
                feito, _tot = linha.split()[1].split("/")
                frac = 0.35 + 0.50 * (int(feito) - 1) / max(n, 1)
                progresso(frac, f"Convertendo voz [{feito}/{n}]...")
            except (ValueError, IndexError):
                pass
        elif linha.startswith("ERRO "):
            erros_subprocess.append(linha)
    proc.wait()
    if proc.returncode != 0:
        cm._limpar(json_path, *[it["vocal_path"] for it in itens],
                   *[it["inst_path"] for it in itens], *[it["vc_out"] for it in itens])
        detalhe = (" Detalhes: " + " | ".join(erros_subprocess)) if erros_subprocess else ""
        raise RuntimeError("seed-vc (lote) falhou ao converter os vocais." + detalhe)

    # ── Fase 3: mixar cada faixa e salvar resultado final ───────────────────
    for i, it in enumerate(itens, 1):
        progresso(0.85 + 0.13 * (i - 1) / max(len(itens), 1),
                  f"[{i}/{len(itens)}] Mixando '{it['base']}'...")
        saida = os.path.join(pasta_saida, f"{it['base']}_pandora.wav")
        try:
            if not os.path.exists(it["vc_out"]):
                raise RuntimeError("seed-vc não gerou a voz convertida desta faixa.")
            mix, sr = cm.mixar(it["vc_out"], it["inst_path"], vol_instrumental)
            sf.write(saida, mix, sr)
            resultados.append({"musica": it["musica"], "saida": saida, "ok": True, "erro": None})
        except Exception as e:
            resultados.append({"musica": it["musica"], "saida": None, "ok": False, "erro": str(e)})
        finally:
            cm._limpar(it["vocal_path"], it["inst_path"], it["vc_out"])

    cm._limpar(json_path)
    progresso(1.0, "Lote concluído!")
    return resultados
