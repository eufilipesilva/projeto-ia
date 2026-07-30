# -*- coding: utf-8 -*-
"""
CATÁLOGO DE EMOÇÕES (25) — referências para o Chatterbox imitar.

Cada emoção tem:
  desc      : a descrição acústica (do Filipe) — referência de intenção
  frase     : frase de REFERÊNCIA que evoca a emoção (o Chatterbox copia a entonação)
  exa_ref   : exaggeration ao GERAR a referência (energia alta -> mais expressivo)
  cfg_ref   : cfg_weight ao gerar a referência (mais baixo = mais dramático/solto)
  exa_final : exaggeration na síntese final (mantém a emoção viva no texto do usuário)

Obs: qualidades vocais especiais (soprosidade, vocal fry, tremor, anasalado) são
aproximadas — o modelo não as cria do nada; chegamos perto via energia/pitch/ritmo.
"""

CATALOGO = {
    # ── 1. PRIMÁRIAS UNIVERSAIS ───────────────────────────────────────────
    "alegria": {
        "desc": "Pitch levemente mais alto, tom aberto e sorridente, cadência ágil.",
        "frase": "Que dia lindo! Eu estou tão contente, tudo deu certo, a vida está maravilhosa!",
        "exa_ref": 1.1, "cfg_ref": 0.40, "exa_final": 0.8,
    },
    "tristeza": {
        "desc": "Pitch baixo, tom abafado, cadência arrastada e pausas longas.",
        "frase": "Eu... eu não consigo mais... dói tanto, tão fundo... perdi tudo o que eu amava... "
                 "e agora... não resta nada. Só esse vazio enorme dentro de mim.",
        "exa_ref": 0.60, "cfg_ref": 0.40, "exa_final": 0.55, "pitch": 0.88, "cfg_final": 0.30,
    },
    "raiva": {
        "desc": "Alta compressão vocal, articulação dura/marcada, volume elevado.",
        "frase": "Chega! Isso é um absurdo, eu não admito! Estou furioso, cansei dessa situação!",
        "exa_ref": 1.6, "cfg_ref": 0.30, "exa_final": 1.0,
    },
    "medo": {
        "desc": "Voz instável ou trêmula, respiração curta e audível.",
        "frase": "Tem... tem alguém aí? Eu estou com medo... por favor, eu não sei o que fazer...",
        "exa_ref": 0.7, "cfg_ref": 0.35, "exa_final": 0.6,
    },
    "surpresa": {
        "desc": "Ataque rápido na primeira sílaba, inflexão final fortemente ascendente.",
        "frase": "O quê?! Não acredito! Como assim?! Eu jamais imaginaria uma coisa dessas!",
        "exa_ref": 1.4, "cfg_ref": 0.30, "exa_final": 0.9,
    },
    "nojo": {
        "desc": "Fonação retraída ou levemente anasalada, som de garganta fechada.",
        "frase": "Que nojo... que coisa horrível, eu não suporto isso, me dá ânsia só de pensar.",
        "exa_ref": 0.8, "cfg_ref": 0.40, "exa_final": 0.6,
    },

    # ── 2. ESTADOS POSITIVOS E EMPÁTICOS ──────────────────────────────────
    "empolgacao": {
        "desc": "Alta energia, projeção forte, picos acentuados de pitch.",
        "frase": "Gente, que demais! Eu estou super empolgado, vai ser incrível, mal posso esperar!",
        "exa_ref": 1.5, "cfg_ref": 0.35, "exa_final": 0.9,
    },
    "ternura": {
        "desc": "Voz aveludada, com bastante ar/soprosidade, ritmo calmo (estilo falar com bebê).",
        "frase": "Ô meu amorzinho... fica calminho, eu estou bem aqui com você, vai ficar tudo bem.",
        "exa_ref": 0.5, "cfg_ref": 0.40, "exa_final": 0.5,
    },
    "serenidade": {
        "desc": "Estabilidade total da curva de pitch, respiração fluida e controlada.",
        "frase": "Respira fundo. Está tudo em paz, sem pressa nenhuma, cada coisa no seu tempo.",
        "exa_ref": 0.35, "cfg_ref": 0.55, "exa_final": 0.4,
    },
    "alivio": {
        "desc": "Começa com leve tensão que se desfaz no meio da frase com uma expiração.",
        "frase": "Ufa... ainda bem. Eu estava tão preocupado, mas agora finalmente posso relaxar.",
        "exa_ref": 0.6, "cfg_ref": 0.45, "exa_final": 0.55,
    },
    "confianca": {
        "desc": "Grave bem colocado, pausas limpas e simétricas, zero hesitação.",
        "frase": "Pode deixar comigo. Eu sei exatamente o que fazer, não tenha a menor dúvida.",
        "exa_ref": 0.7, "cfg_ref": 0.50, "exa_final": 0.6,
    },

    # ── 3. CARGAS DRAMÁTICAS E DE TENSÃO ──────────────────────────────────
    "ansiedade": {
        "desc": "Ritmo acelerado, pausas em lugares antinaturais, leve falta de ar.",
        "frase": "Eu não sei, não sei... e se der errado? Tem tanta coisa, e o tempo está acabando.",
        "exa_ref": 1.0, "cfg_ref": 0.30, "exa_final": 0.8,
    },
    "desespero": {
        "desc": "Mistura de choro contido com picos agudos de descontrole vocal.",
        "frase": "Não, não, isso não pode estar acontecendo! Por favor, me ajuda, eu não consigo!",
        "exa_ref": 1.7, "cfg_ref": 0.30, "exa_final": 1.0,
    },
    "frustracao": {
        "desc": "Maxilar travado, expiração pesada ao terminar as últimas palavras.",
        "frase": "Ah, de novo isso... eu já tentei de tudo, e nada funciona. Que saco, sério.",
        "exa_ref": 0.9, "cfg_ref": 0.40, "exa_final": 0.7,
    },
    "arrependimento": {
        "desc": "Volume baixo, tom intimista, pequenas hesitações (é..., hum...).",
        "frase": "Eu... eu sinto muito, de verdade. Foi tudo culpa minha, eu não devia ter feito aquilo.",
        "exa_ref": 0.5, "cfg_ref": 0.45, "exa_final": 0.5,
    },
    "exaustao": {
        "desc": "Vocal fry/crepitação no final das frases, falta de fôlego.",
        "frase": "Eu estou tão cansado... não tenho mais forças, só quero deitar e dormir agora.",
        "exa_ref": 0.35, "cfg_ref": 0.50, "exa_final": 0.4,
    },

    # ── 4. MATIZES SOCIAIS E INTELECTUAIS ─────────────────────────────────
    "sarcasmo": {
        "desc": "Alongamento exagerado de certas vogais, entonação de falso sorriso.",
        "frase": "Ah, claro... que ideia brilhante. Nossa, eu jamais teria pensado nisso sozinho.",
        "exa_ref": 0.8, "cfg_ref": 0.40, "exa_final": 0.6,
    },
    "ceticismo": {
        "desc": "Inflexão que sobe no meio e desce no final; sobrancelha levantada audível.",
        "frase": "Sei... será mesmo? Eu não sei não, isso me parece bem difícil de acreditar.",
        "exa_ref": 0.6, "cfg_ref": 0.45, "exa_final": 0.55,
    },
    "curiosidade": {
        "desc": "Projeção inclinada para a frente, tom investigativo e leve.",
        "frase": "Hum, que interessante... me conta mais. Como foi que isso aconteceu, afinal?",
        "exa_ref": 0.7, "cfg_ref": 0.40, "exa_final": 0.6,
    },
    "tedio": {
        "desc": "Voz estritamente monótona, achatamento quase total da variação de pitch.",
        "frase": "Aaai... que preguiça. Tanto faz, sério... pra mim dá tudo no mesmo. "
                 "Sei lá... que seja. Deixa quieto, não faz a menor diferença.",
        "exa_ref": 0.15, "cfg_ref": 0.55, "exa_final": 0.18, "pitch": 0.97, "cfg_final": 0.45,
    },
    "melancolia": {
        "desc": "Tom reflexivo, aéreo, olhar distante traduzido na colocação da voz.",
        "frase": "Lembra como era antes? Pois é... o tempo passa, e fica só a saudade daquilo tudo.",
        "exa_ref": 0.40, "cfg_ref": 0.50, "exa_final": 0.45,
    },

    # ── 5. ATITUDES E INTERPRETAÇÕES DE PERSONAGEM ────────────────────────
    "seducao": {
        "desc": "Proximidade do microfone, sussurrado, ritmo cadenciado e lento.",
        "frase": "Mmm... oi, vem cá. Bem pertinho de mim... eu adoro te sentir assim, "
                 "só nosso... bem devagar, sem nenhuma pressa...",
        "exa_ref": 0.35, "cfg_ref": 0.22, "exa_final": 0.38, "pitch": 0.98, "cfg_final": 0.20,
    },
    "arrogancia": {
        "desc": "Fala de nariz em pé, pronúncia excessivamente polida/arrastada com desdém.",
        "frase": "Por favor... eu obviamente sei mais do que todos vocês. Não me façam perder tempo.",
        "exa_ref": 0.7, "cfg_ref": 0.45, "exa_final": 0.6,
    },
    "timidez": {
        "desc": "Volume quase inaudível, atropelamento sutil de sílabas, pigarro leve.",
        "frase": "Ã... oi. Desculpa... eu só queria, sabe... ah, deixa pra lá, não é nada demais.",
        "exa_ref": 0.5, "cfg_ref": 0.35, "exa_final": 0.5,
    },
    "urgencia": {
        "desc": "Supressão das pausas de respiração, entrega metralhada e contínua.",
        "frase": "Rápido, rápido! Não temos tempo! Anda logo, precisa ser agora, vamos, vamos!",
        "exa_ref": 1.5, "cfg_ref": 0.30, "exa_final": 0.95,
    },
}


# ── MAPA DAS 25: cada emoção -> fonte da referência + ajustes de síntese ──────
#   fonte "ravdess:<base>" usa o áudio HUMANO real (app/refs_emocao/_rav_<base>.wav)
#   fonte "sintetico" gera a referência com o Chatterbox a partir da CATALOGO[emo]
#   (exa, cfg, pitch) = parâmetros da SÍNTESE FINAL (intensidade, ritmo, tom)
EMOCOES_REF = {
    # 1. primárias (direto do RAVDESS)
    "alegria":       {"fonte": "ravdess:happy",     "exa": 0.70, "cfg": 0.40, "pitch": 1.00},
    "tristeza":      {"fonte": "ravdess:sad",       "exa": 0.55, "cfg": 0.35, "pitch": 1.00},
    "raiva":         {"fonte": "ravdess:angry",     "exa": 0.90, "cfg": 0.35, "pitch": 1.00},
    "medo":          {"fonte": "ravdess:fearful",   "exa": 0.70, "cfg": 0.35, "pitch": 1.00},
    "surpresa":      {"fonte": "ravdess:surprised", "exa": 0.90, "cfg": 0.35, "pitch": 1.00},
    "nojo":          {"fonte": "ravdess:disgust",   "exa": 0.70, "cfg": 0.40, "pitch": 1.00},
    # 2. positivos/empáticos
    "empolgacao":    {"fonte": "ravdess:happy",     "exa": 1.20, "cfg": 0.30, "pitch": 1.00},
    "ternura":       {"fonte": "ravdess:calm",      "exa": 0.40, "cfg": 0.40, "pitch": 1.00},
    "serenidade":    {"fonte": "ravdess:calm",      "exa": 0.35, "cfg": 0.50, "pitch": 1.00},
    "alivio":        {"fonte": "ravdess:calm",      "exa": 0.50, "cfg": 0.45, "pitch": 1.00},
    "confianca":     {"fonte": "ravdess:neutral",   "exa": 0.60, "cfg": 0.50, "pitch": 0.97},
    # 3. dramáticas/tensão
    "ansiedade":     {"fonte": "ravdess:fearful",   "exa": 0.90, "cfg": 0.30, "pitch": 1.00},
    "desespero":     {"fonte": "ravdess:fearful",   "exa": 1.30, "cfg": 0.30, "pitch": 1.00},
    "frustracao":    {"fonte": "ravdess:angry",     "exa": 0.60, "cfg": 0.40, "pitch": 1.00},
    "arrependimento":{"fonte": "ravdess:sad",       "exa": 0.50, "cfg": 0.40, "pitch": 1.00},
    "exaustao":      {"fonte": "ravdess:sad",       "exa": 0.40, "cfg": 0.50, "pitch": 0.97},
    # 4. sociais/intelectuais
    "sarcasmo":      {"fonte": "sintetico",         "exa": 0.60, "cfg": 0.40, "pitch": 1.00},
    "ceticismo":     {"fonte": "sintetico",         "exa": 0.55, "cfg": 0.45, "pitch": 1.00},
    "curiosidade":   {"fonte": "sintetico",         "exa": 0.60, "cfg": 0.40, "pitch": 1.00},
    "tedio":         {"fonte": "ravdess:neutral",   "exa": 0.20, "cfg": 0.60, "pitch": 1.00},
    "melancolia":    {"fonte": "ravdess:sad",       "exa": 0.45, "cfg": 0.45, "pitch": 1.00},
    # 5. atitudes/personagem
    "seducao":       {"fonte": "sintetico",         "exa": 0.38, "cfg": 0.20, "pitch": 0.98},
    "arrogancia":    {"fonte": "sintetico",         "exa": 0.60, "cfg": 0.45, "pitch": 1.00},
    "timidez":       {"fonte": "sintetico",         "exa": 0.50, "cfg": 0.35, "pitch": 1.00},
    "urgencia":      {"fonte": "ravdess:fearful",   "exa": 1.10, "cfg": 0.30, "pitch": 1.00},
    # baseline útil
    "neutra":        {"fonte": "ravdess:neutral",   "exa": 0.50, "cfg": 0.50, "pitch": 1.00},
}

# rótulos bonitos + agrupamento pra interface
GRUPOS = [
    ("Primárias",      ["alegria", "tristeza", "raiva", "medo", "surpresa", "nojo"]),
    ("Positivas",      ["empolgacao", "ternura", "serenidade", "alivio", "confianca"]),
    ("Tensão/Drama",   ["ansiedade", "desespero", "frustracao", "arrependimento", "exaustao"]),
    ("Sociais",        ["sarcasmo", "ceticismo", "curiosidade", "tedio", "melancolia"]),
    ("Atitudes",       ["seducao", "arrogancia", "timidez", "urgencia"]),
    ("Base",           ["neutra"]),
]
