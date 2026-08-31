# -*- coding: utf-8 -*-
"""Cria a voz de cada personagem por DESIGN, sem gravar e sem clonar ninguém.

O OmniVoice gera um timbre a partir de atributos, mas gera um timbre NOVO a
cada chamada — dois "rei" sairiam diferentes. `motor_v2.perfil_de_design` já
resolvia isso e o caminho aqui é o mesmo: gerar UMA frase-semente por
personagem, salvar esse áudio como referência, e daí em diante todas as falas
dele — em todos os contos — clonam essa semente.

Por que não buscar vozes na internet: a voz de uma pessoa real é direito de
personalidade dela. O arquivo estar disponível não é consentimento para gerar
falas novas com aquela voz. Aqui o timbre é sintético desde a origem e é
reproduzível — apagou, roda de novo, sai igual.

Uso:
    python -m acervo.gerar_vozes --listar
    python -m acervo.gerar_vozes --personagem lobo
    python -m acervo.gerar_vozes --todos
"""
import argparse
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acervo import base, personagens          # noqa: E402
import motor_v2 as motor                      # noqa: E402

# Frase-semente: neutra e com boa cobertura de fonemas do português. Vira o
# `ref_text` do perfil de clone, gravado no .txt ao lado do .wav — assim
# `perfil_voz` não precisa do ASR (desligado no projeto).
SEMENTE = ("Era uma vez, num lugar bem distante daqui, uma história que "
           "começava assim, com calma e bastante clareza.")

# Fração de quadros com pitch detectável para o áudio ser aceito como fala.
# Começou em 0.30 e ficou frouxo demais: 'alfaiate' passou com 31% e 'pedro'
# com 34%, e o F0 nem correspondia aos atributos pedidos ('joao' saiu com 96 Hz
# sendo "moderate pitch"). Uma amostra sadia fica entre 70% e 88%.
VOZEADO_MINIMO = 0.60
TENTATIVAS = 6

# Personagens que são o mesmo papel escrito de formas diferentes. `raina` é
# "rainha" com erro de digitação da própria Gemma — sem fundir, viraria um
# personagem fantasma com voz própria.
ALIASES = {
    "mamae": "mae", "papai": "pai", "filhos": "filho", "raina": "rainha",
    "criados": "criada", "fadas": "fada", "camponesa": "campones",
    "irmaos": "irmao", "meninas": "menina", "meninos": "menino",
}

# ── Assinatura de voz: três eixos INDEPENDENTES ──────────────────────────────
#
# Só o pitch não diferencia pessoas — muda a altura, não a identidade, e o
# resultado é a mesma voz acelerada (efeito "esquilo"). Cada personagem tem:
#
#   instruct  timbre-base do OmniVoice (gênero, idade, altura)
#             female/male · child, teenager, young adult, middle-aged, elderly
#             · very low, low, moderate, high, very high pitch
#   formante  TAMANHO DO CORPO, independente do pitch (`motor._formantes`)
#             < 1  trato longo: corpo grande, voz encorpada (lobo, gigante)
#             > 1  trato curto: corpo pequeno, voz miúda (rato, galo, anão)
#   speed     tempo de fala: pesado e arrastado, ou miúdo e apressado
#
# O formante é assado na própria semente, então o clone herda o corpo do
# personagem sem nenhuma mudança no caminho de síntese. A velocidade entra como
# `base_speed` do perfil, na hora de sintetizar.
#   maligno   tratamento de vilão (`motor._maligno`): subarmônico uma oitava
#             abaixo + escurecimento + aspereza. Aplicado na SÍNTESE, não na
#             semente — assado na referência, o clone tentaria copiar o rosnado
#             como se fosse timbre e o resultado embola. Escala 0 a 1; acima de
#             ~0.75 atrapalha a inteligibilidade, que numa história para
#             criança pequena importa mais que o susto.
def _v(instruct, formante=1.0, speed=1.0, maligno=0.0):
    return dict(instruct=instruct, formante=formante, speed=speed,
                maligno=maligno)


VOZES = {
    # ── realeza e família ────────────────────────────────────────────────
    "rei":       _v("male, elderly, low pitch",            0.88, 0.88),
    "rainha":    _v("female, middle-aged, low pitch",      0.93, 0.92),
    "principe":  _v("male, young adult, moderate pitch",   1.00, 1.00),
    "princesa":  _v("female, young adult, high pitch",     1.06, 1.02),
    "pai":       _v("male, middle-aged, moderate pitch",   0.96, 0.95),
    "mae":       _v("female, middle-aged, moderate pitch", 1.00, 0.98),
    "madrasta":  _v("female, elderly, low pitch",          0.90, 0.94, 0.30),
    "madrinha":  _v("female, elderly, moderate pitch",     1.03, 0.90),
    "filho":     _v("male, teenager, moderate pitch",      1.06, 1.05),
    "filha":     _v("female, teenager, high pitch",        1.08, 1.05),
    "irmao":     _v("male, young adult, moderate pitch",   1.01, 1.03),
    "esposa":    _v("female, middle-aged, high pitch",     1.02, 1.00),
    "menina":    _v("female, child, high pitch",           1.14, 1.05),
    "menino":    _v("male, child, high pitch",             1.14, 1.06),
    "pequeno":   _v("male, child, very high pitch",        1.20, 1.10),
    # ── gente do povo ────────────────────────────────────────────────────
    "homem":     _v("male, middle-aged, moderate pitch",   0.98, 1.00),
    "senhor":    _v("male, elderly, moderate pitch",       0.94, 0.90),
    "senhora":   _v("female, elderly, moderate pitch",     0.98, 0.90),
    "velhinha":  _v("female, elderly, high pitch",         0.96, 0.85),
    "velho":     _v("male, elderly, very low pitch",       0.88, 0.85),
    "pastor":    _v("male, elderly, low pitch",            0.92, 0.88),
    "moleiro":   _v("male, middle-aged, low pitch",        0.95, 0.96),
    # o alfaiate valente é pequeno e esperto — miúdo e apressado
    "alfaiate":  _v("male, young adult, high pitch",       1.10, 1.12),
    "cacador":   _v("male, middle-aged, low pitch",        0.90, 0.94),
    "criada":    _v("female, young adult, moderate pitch", 1.04, 1.05),
    "campones":  _v("male, middle-aged, low pitch",        0.94, 0.92),
    "lenhador":  _v("male, middle-aged, low pitch",        0.90, 0.92),
    "soldado":   _v("male, young adult, low pitch",        0.94, 1.00),
    # ── nomes próprios ───────────────────────────────────────────────────
    "joao":      _v("male, young adult, moderate pitch",   1.00, 1.02),
    "pedro":     _v("male, teenager, high pitch",          1.08, 1.06),
    "lucas":     _v("male, young adult, low pitch",        0.96, 0.98),
    "lila":      _v("female, child, high pitch",           1.12, 1.05),
    "sofia":     _v("female, teenager, high pitch",        1.06, 1.02),
    "clara":     _v("female, child, very high pitch",      1.16, 1.06),
    # ── mágicos ──────────────────────────────────────────────────────────
    "fada":      _v("female, young adult, very high pitch", 1.12, 1.08),
    "bruxa":     _v("female, elderly, very low pitch",     0.86, 0.90, 0.62),
    "diabo":     _v("male, elderly, very low pitch",       0.80, 0.86, 0.72),
    "anao":      _v("male, child, high pitch",             1.18, 1.08),
    "gigante":   _v("male, middle-aged, very low pitch",   0.72, 0.82, 0.58),
    # ── bichos: o TAMANHO é a alavanca principal ─────────────────────────
    "lobo":      _v("male, middle-aged, very low pitch",   0.80, 0.90, 0.55),
    "urso":      _v("male, elderly, very low pitch",       0.76, 0.85, 0.35),
    "cavalo":    _v("male, middle-aged, low pitch",        0.86, 0.92),
    "burro":     _v("male, elderly, low pitch",            0.84, 0.86),
    "cachorro":  _v("male, middle-aged, low pitch",        0.94, 1.05),
    "raposa":    _v("female, young adult, moderate pitch", 1.04, 1.08),
    "gato":      _v("female, young adult, high pitch",     1.08, 0.96),
    # "male, teenager, very high pitch" falhou 4x seguidas na geração —
    # combinação instável no OmniVoice. O agudo do galo vem do formante.
    "galo":      _v("male, child, high pitch",             1.22, 1.10),
    "galinha":   _v("female, middle-aged, high pitch",     1.10, 1.06),
    "sapo":      _v("male, elderly, very low pitch",       0.82, 0.84),
    "rato":      _v("male, child, very high pitch",        1.24, 1.12),
    "passaro":   _v("female, child, very high pitch",      1.26, 1.14),
    "coelhinho": _v("male, child, high pitch",             1.16, 1.10),
}


def resolver_alias(nome):
    return ALIASES.get(nome, nome)


def assinatura_de(nome, usar_gemma=True, verbose=True):
    """Assinatura de voz de um personagem.

    Tabela primeiro (revisável e determinística); só cai na Gemma para nome que
    não está nela, e aí com formante/velocidade neutros."""
    nome = resolver_alias(nome)
    if nome in VOZES:
        return VOZES[nome]
    if not usar_gemma:
        return None
    desc = f"personagem de conto de fadas chamado '{nome}', narração infantil"
    instruct, _msg = motor.interpretar_descricao_voz(desc)
    if verbose:
        print(f"      (Gemma sugeriu para '{nome}': {instruct})")
    return _v(instruct) if instruct else None


def medir_voz(audio, sr):
    """(fração vozeada, F0 mediana) — como o áudio se comporta como fala."""
    import librosa
    f, vf, _ = librosa.pyin(np.asarray(audio, dtype=float), fmin=60, fmax=450,
                            sr=sr, frame_length=2048)
    v = f[~np.isnan(f)]
    return float(np.mean(vf)), (float(np.median(v)) if len(v) else 0.0)


def _eh_fala(audio, sr):
    """O modo design falha em silêncio: às vezes devolve ruído com volume
    normal e nenhuma periodicidade — não é fala, mas o arquivo parece válido.
    Aconteceu com 3 das 40 primeiras vozes ('principe', 'filho' e 'galo' saíram
    com 0%, 0% e 5% de quadros vozeados). Como a falha é aleatória e não vem
    dos atributos (`joao` tem os mesmos de `principe` e saiu bem), basta
    detectar e gerar de novo."""
    vozeado, _f0 = medir_voz(audio, sr)
    return vozeado >= VOZEADO_MINIMO, vozeado


def gerar_para(nome, instruct=None, formante=None, forcar=False, verbose=True):
    """Sintetiza a semente, aplica o formante e salva como voz do personagem."""
    nome = resolver_alias(nome)
    pasta = os.path.join(base.VOZES_PERS, nome)
    os.makedirs(pasta, exist_ok=True)
    destino = os.path.join(pasta, f"{nome}.wav")
    if os.path.exists(destino) and not forcar:
        return "pulado"

    ass = assinatura_de(nome, verbose=verbose) or {}
    instruct = instruct or ass.get("instruct")
    formante = ass.get("formante", 1.0) if formante is None else formante
    speed = ass.get("speed", 1.0)
    if not instruct:
        return None
    if verbose:
        print(f"  {nome:<12} {instruct}  | formante {formante:.2f} · "
              f"speed {speed:.2f}")

    audio = None
    for n in range(1, TENTATIVAS + 1):
        cand = np.asarray(motor.sintetizar_design(instruct, SEMENTE, "pt",
                                                  32, 3.0, 1.0),
                          dtype=np.float32)
        ok, vozeado = _eh_fala(cand, motor.SR)
        if ok:
            audio = cand
            if verbose and n > 1:
                print(f"               (deu certo na tentativa {n})")
            break
        if verbose:
            print(f"               tentativa {n}: só {100*vozeado:.0f}% vozeado "
                  f"— não é fala, gerando de novo")
    if audio is None:
        if verbose:
            print(f"               FALHOU após {TENTATIVAS} tentativas")
        return "erro"

    # O corpo do personagem é assado na referência: o clone herda o trato vocal
    # sem que a síntese precise saber de nada.
    if abs(formante - 1.0) > 1e-3:
        audio = motor._formantes(audio, formante)

    sf.write(destino, audio, motor.SR)
    with open(destino[:-4] + ".txt", "w", encoding="utf-8") as f:
        f.write(SEMENTE)

    mapa = personagens.carregar_mapa()
    reg = mapa.setdefault(nome, {})
    reg["voz"] = os.path.basename(destino)
    reg["instruct"] = instruct
    reg["formante"] = formante
    reg["speed"] = speed
    personagens.gravar_mapa(mapa)
    if verbose:
        _voc, f0 = medir_voz(audio, motor.SR)
        print(f"               {len(audio)/motor.SR:.1f}s · F0 {f0:.0f} Hz "
              f" ->  {destino}")
    return "ok"


def gerar_todos(minimo=2, forcar=False, verbose=True):
    el = personagens.levantar(verbose=False)
    alvos = sorted({resolver_alias(n) for n, d in el.items()
                    if len(d["historias"]) >= minimo})
    if verbose:
        print(f"{len(alvos)} personagem(ns) recorrente(s) para gerar voz.\n")
    motor.descarregar_gemma()
    contagem = {}
    for nome in alvos:
        try:
            r = gerar_para(nome, forcar=forcar, verbose=verbose)
        except Exception as e:
            r = "erro"
            if verbose:
                print(f"  {nome}: FALHOU — {e}")
        if r:
            contagem[r] = contagem.get(r, 0) + 1
    if verbose:
        print(f"\n{contagem}")
    return contagem


def listar(minimo=2):
    el = personagens.levantar(verbose=False)
    rec = sorted(((resolver_alias(n), len(d["historias"]), d["falas"])
                  for n, d in el.items() if len(d["historias"]) >= minimo),
                 key=lambda x: -x[1])
    vistos = set()
    print(f"{'personagem':<12} {'hist':>4} {'form':>5} {'spd':>5}  instruct")
    print("-" * 74)
    for nome, h, _f in rec:
        if nome in vistos:
            continue
        vistos.add(nome)
        a = VOZES.get(nome)
        if a:
            print(f"{nome:<12} {h:>4} {a['formante']:>5.2f} {a['speed']:>5.2f}"
                  f"  {a['instruct']}")
        else:
            print(f"{nome:<12} {h:>4} {'—':>5} {'—':>5}  (pela Gemma)")


def main():
    ap = argparse.ArgumentParser(description="Gera as vozes dos personagens por design")
    ap.add_argument("--listar", action="store_true")
    ap.add_argument("--personagem")
    ap.add_argument("--instruct", help="atributos manuais, ignora a tabela")
    ap.add_argument("--formante", type=float, help="fator manual de formante")
    ap.add_argument("--todos", action="store_true")
    ap.add_argument("--minimo", type=int, default=2)
    ap.add_argument("--forcar", action="store_true")
    a = ap.parse_args()
    base.console_utf8()

    if a.listar:
        listar(a.minimo)
    elif a.personagem:
        gerar_para(a.personagem, a.instruct, a.formante, forcar=True)
    elif a.todos:
        gerar_todos(a.minimo, a.forcar)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
