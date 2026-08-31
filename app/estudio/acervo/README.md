# Acervo — histórias infantis narradas, da coleta ao áudio

Esteira que baixa contos de domínio público, adapta para uma faixa etária,
detecta as falas por personagem e sintetiza com o Contador do estúdio.

```
coletar ─► limpar ─► medir ─► adaptar ─► validar ─► roteirizar ─► [vozes] ─► sintetizar
  auto      auto      auto      Gemma      auto        Gemma        manual     OmniVoice
```

## Estado (31/ago/2026)

```
roteirizado   27   prontas para áudio
adaptado      28   reprovadas na validação, fila manual
descartado    18   barradas por conteúdo ou aparato editorial
classificado   4   longas demais para adaptar
total         77   contos coletados do Wikisource
```

Vozes: **57 locutores humanos** do MLS Portuguese em `vozes_corpus/` (32 M, 25 F)
mais blends do Kokoro em `vozes_personagens/`. O mapa `personagem → voz` está em
`vozes_personagens/mapa.json`.

**Onde parou:** o casamento automático de voz não convenceu de ouvido. A escolha
final de cada voz será feita à mão (ver *Escolher vozes* abaixo). Todo o resto
da esteira está funcionando.

## Comandos

```bash
python -m acervo.wikisource --coletar        # baixa (API, em lote, com recuo)
python -m acervo.limpar                      # wikitext -> texto
python -m acervo.metricas                    # mede e estima faixa etária
python -m acervo.adaptar --idade 6           # adapta (laço de correção)
python -m acervo.reparar                     # conserto cirúrgico das reprovadas
python -m acervo.validar --todos             # regras do FORMATO.md
python -m acervo.roteirizar                  # falas classificadas por personagem
python -m acervo.personagens --levantar      # elenco global + pastas de voz
python -m acervo.sintetizar                  # roteiro -> áudio
python -m acervo.fila --status               # onde tudo está
python -m acervo.fila --revisar              # o que pede olho humano no conteúdo
```

## Escolher vozes (o passo manual)

```bash
python -m acervo.casar_vozes --audicao lobo --top 5    # ouvir as opções
python -m acervo.personagens --definir lobo --voz mls_m_4405.wav
```

Para usar a **sua própria gravação** — o que rende mais nos vilões, porque
ameaça é atuação e nenhum filtro fabrica isso:

```
vozes_personagens/lobo/lobo.wav    10 a 15 segundos
vozes_personagens/lobo/lobo.txt    a transcrição do que foi falado
```

O `.txt` é obrigatório: o ASR do OmniVoice está desligado neste projeto (bug de
FFmpeg, ver `DOCUMENTACAO.md` §4.1), então sem ele o clone não sabe o que a
referência diz.

Marque `"travado": true` no `mapa.json` para o que aprovar — um `--aplicar`
futuro não sobrescreve entradas travadas.

## Documentos

| arquivo | o que é |
|---|---|
| `ELENCO_VOZES.md` | **direção**: como cada voz deve soar, e os pares de contraste que servem de teste |
| `FORMATO.md` | as 7 regras que uma adaptação precisa cumprir, com o erro que originou cada uma |

## Decisões que custaram caro (não refazer)

**A idade medida é da TRADUÇÃO, não do conto.** "Os músicos de Bremen" mede 8
anos porque *este texto* de 1800 tem 10 minutos — a história é ideal para 5.
Por isso o pipeline mede duas vezes: antes (triagem) e depois de adaptar
(rótulo real).

**ILF e comprimento de frase não discriminam nada aqui.** Medido sobre os 73
contos: sílabas/palavra é praticamente constante (1,9) e palavras/frase quase
não varia — é a assinatura do tradutor, não dos contos. O que varia 70× é a
**duração**, e é ela que manda na faixa etária.

**A barreira de conteúdo não pode ser por palavra-chave.** A Gemma devolve temas
abstratos ("maldição", "ganância"), não descrições concretas: "A donzela sem
mãos" voltou como "maldição, morte, violência". O que funciona é o **número** de
idade que ela atribui — 14 para essa, 6 para "A noiva do coelhinho".

**Ruído aditivo não vira ameaça, vira chiado.** A tentativa de dar voz "maligna"
somando aspereza foi reprovada de ouvido. Em saída de TTS, ruído lê como defeito
de gravação. Ameaça tem que vir do timbre da referência.

**Identidade de voz mora na REFERÊNCIA.** O modo Design do OmniVoice varia ~3
semitons entre gerações com a mesma instrução: é a mesma voz repetida. O
clonador é fiel — então a variedade tem que entrar como referência, não como
processamento.

**Limiar que reprova 100% dos casos é limiar errado.** Aconteceu duas vezes: a
regra de repetição cortando refrão legítimo de conto cumulativo, e o filtro de
achatamento espectral em 0,010 reprovando todos os locutores do MLS — quando a
própria `Pandora.wav` marca 0,0348. Calibrar contra a distribuição real, sempre.

## Consertos no motor_v2 que vieram daqui

Valem para o Contador inteiro, não só para o acervo:

- **aspas curvas** (`“ ”`) não estavam na normalização — todo diálogo colado do
  Word ou da web era lido como narração, em silêncio
- **travessão no início da linha** (`- Fala - disse ele`) invertia fala e
  narração pela paridade do split
- **tag embutida na fala** (`— Estou cansado, disse o burro.`) fazia o beat
  inteiro virar fala: em Bremen o narrador sumia de 63 dos 64 beats
- **`disse: —`** não era reconhecido como anúncio de fala (o travessão protegia
  os dois-pontos do `strip`)
- **verbo negado** virava atribuição: "A Lila não disse nada" criava um
  personagem chamado `nada`
- **`_formantes()`**: desloca formantes sem mexer no pitch (item 7 do ROADMAP)

## Fontes

- Contos: [Wikisource pt](https://pt.wikisource.org/wiki/Contos_de_Grimm) —
  domínio público, origem Project Gutenberg
- Vozes: [MLS Portuguese](https://www.openslr.org/94/) (CC BY 4.0),
  `mls_portuguese_opus.tar.gz`, 2,4 GB — não versionado, baixar de novo se
  precisar
- Kokoro v1.0 local, em `laboratorios/voices_kokoro`
