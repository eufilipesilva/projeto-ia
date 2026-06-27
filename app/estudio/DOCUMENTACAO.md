# 🎙️ Estúdio de Voz — Documentação

Plataforma **100% local** de síntese de voz: clona uma voz, projeta vozes por
características e narra histórias com vozes de personagem e emoção. Roda numa
RTX 2060 (6 GB) usando **OmniVoice** (TTS) + **Gemma 3 4B** via **Ollama** (o "cérebro"
que interpreta o texto).

---

## 1. Como rodar

```bat
INICIAR_ESTUDIO.bat
```
ou direto:
```bat
.venv_omni\Scripts\python.exe app\estudio\estudio.py
```
Abre em **http://127.0.0.1:5006**.

**Pré-requisitos:** Ollama rodando com o modelo `gemma3:4b` (`ollama pull gemma3:4b`),
e o ambiente `.venv_omni` com `omnivoice`, `gradio`, `librosa`, `soundfile`, `torch`.

---

## 2. As três abas

| Aba | O que faz | Usa Gemma? |
|-----|-----------|------------|
| **🎤 Clone de Voz** | Analisa uma voz (≥ 3 s) e lê o texto com ela | Não |
| **🎨 Design de Voz** | Cria uma voz por características (gênero/idade/tom/estilo), sem referência | Não |
| **📖 Contador de Histórias** | Lê uma história dando voz própria a cada personagem + emoção; ritmo, modo sussurro e música de fundo | Sim |
| **🎪 Comédia (auditório)** | Como o Contador, mas insere **sonoplastia** (aplauso/risada/rufar/buzina...) nos momentos certos + plateia de fundo — estilo Ratinho | Sim |
| **🎓 Game Show Educativo (PDF)** | Lê um **PDF** e a Pandora cria um **quiz educativo** sobre o assunto (para crianças aprenderem); reusa o motor da Comédia | Sim |

Nas abas Clone e Design há controles de **idioma, inference steps, guidance scale e
velocidade**. No Contador de Histórias há **ritmo da narração** e **modo sussurro (ASMR)**.

---

## 3. Arquitetura

```
estudio.py   → interface Gradio (as 3 abas, sliders, botões)
motor.py     → toda a lógica: modelos, áudio, classificação de história
vozes/       → vozes salvas (Pandora.wav + Pandora.txt = transcrição da referência)
saidas/      → áudios gerados por scripts antigos (histórico)
```

### O ciclo de memória (a restrição que molda tudo)
Numa GPU de **6 GB**, a Gemma e o OmniVoice **não cabem juntos**. Então o motor segue
sempre o ciclo:

```
gemma infere (quem fala + emoção)  →  descarrega gemma  →  carrega OmniVoice
→  sintetiza todos os beats  →  descarrega OmniVoice
```

`descarregar_gemma()` usa a API do Ollama **e** o `ollama stop` por CLI (a API sozinha
nem sempre libera a VRAM), depois espera e limpa o cache do CUDA.

---

## 4. Decisões técnicas e desafios

Esta é a parte importante: **o que deu errado, por quê, e como foi resolvido.** Cada
item abaixo foi um problema real que apareceu testando.

### 4.1. `load_asr=False` — o crash do FFmpeg
O OmniVoice tem um transcritor (Whisper) embutido que, no modo de clone, transcreveria
o áudio de referência automaticamente. **Problema:** esse caminho depende de `torchcodec`,
que precisa das DLLs do FFmpeg — **não disponíveis nesta máquina Windows** → crash.

**Solução:** carregamos com `load_asr=False` e fornecemos a transcrição da referência
nós mesmos: um arquivo `.txt` ao lado do `.wav` (ex.: `Pandora.txt`). O
`_criar_prompt_voz` nunca passa `None` como `ref_text` — sempre o texto do cache, evitando
disparar o transcritor.

### 4.2. Geração única, não frase-a-frase — o caso do "Bem"
**Desafio:** o OmniVoice "comia" a primeira sílaba de cada síntese. A primeira tentativa
foi um *primer*: colocar a palavra `"Bem."` no começo e recortá-la depois. Isso era frágil
— o recorte (fixo ou por detecção de silêncio) ora deixava o "Bem" audível, ora comia
áudio real, porque o tamanho do primer varia com a velocidade e a voz.

**Solução:** copiamos o comportamento do notebook de referência — **gerar o texto inteiro
numa única chamada** ao modelo. O "comer a primeira palavra" só acontecia *porque*
estávamos fatiando em frases e re-priming cada uma. Gerando de uma vez, o problema some,
e o código fica muito mais simples (`sintetizar_clone`/`sintetizar_design` fazem 1
`generate()`). O Contador de Histórias ainda gera beat-a-beat — porque cada personagem
precisa de um timbre diferente — mas sem primer.

### 4.3. `postprocess_output=False` + `finalizar()` — finais que não cortam
**Desafio:** os finais de frase saíam secos, com a última palavra cortada antes do tempo.
Descobrimos que o **pós-processamento do próprio OmniVoice apara a cauda** do áudio.

**Solução (4 peças):**
1. `postprocess_output=False` — desligamos o aparador do modelo e controlamos o fim nós.
2. `_com_ponto()` — garante pontuação final; sem `. ! ? …` o modelo corta a última palavra.
3. `finalizar()` — corta o silêncio morto das pontas com limiar generoso de **−35 dB**
   (preserva até fricativas suaves como o "s") mas mantém **90 ms de cauda** da última palavra.
4. **Fade-out exponencial adaptativo** — mais longo quando o fim é abrupto
   (260 ms → ~480 ms), com curva exponencial (como a voz decai de verdade).

### 4.4. Ajuste especial para vogais (ZCR)
**Desafio:** mesmo com o fade, finais **em vogal** caíam secos — vogais sustentam energia
e precisam de mais tempo para morrer do que consoantes (que já decaem sozinhas).

**Solução:** `_zcr()` mede a *taxa de cruzamento por zero* da cauda. ZCR baixo = som
vozeado/vogal → o fade fica **25% mais longo**. ZCR alto = consoante/fricativa → fade normal.

### 4.5. Emenda entre beats — a vogal não pode ser atropelada
**Desafio:** ao juntar beats do mesmo personagem, um crossfade sobrepunha o fim do beat
anterior com o início do próximo — **atropelando a cauda da vogal** (ficava seca de novo).

**Solução:** juntamos os beats **sem sobreposição**. A vogal decai inteira no fade-out e
só então entra o próximo beat, com uma **respiração curta** (90 ms se for o mesmo locutor,
soa contínuo) ou uma **pausa maior** (240 ms na troca de locutor). O `_montar` recebe a
lista de quem fala cada beat para decidir isso.

### 4.6. Normalização de diálogo (travessões)
**Desafio:** o OmniVoice não vocaliza o travessão (`–`/`—`) e "comia" o texto ao redor dele.

**Solução:** `_normalizar_fala()` converte travessões de diálogo em vírgula (pausa que o
modelo lê bem), remove o travessão no início da fala, e **preserva hífen de palavra
composta** (`guarda-chuva`, que não tem espaços ao redor).

### 4.7. Segmentação por locutor — aspas E travessões
**Desafio (Contador de Histórias):** a fala de um personagem e a *tag de narração* ("perguntou
o lobo") vinham na mesma frase e recebiam a mesma voz. Pior: nem todo texto usa travessão —
a Chapeuzinho Vermelho usa **aspas** (`" "`).

**Solução:** `_beats_historia()` reconhece **aspas (curvas e retas) e travessões**. O que
está dentro das aspas / entre travessões é **fala de personagem**; o resto (narração + tags
de atribuição) é **narração**, quebrada em frases. Preserva as quebras de linha, que separam
locutores.

### 4.8. Classificação em lotes — o limite da Gemma 3 4B
**Desafio:** pedir para a Gemma classificar ~85 itens de uma vez **estourava o contexto**
(`num_ctx`) e tudo caía no fallback "narrador / neutra".

**Solução:** `_classificar_beats()` processa em **lotes de 12** com `num_ctx=4096`. Em lotes
pequenos a Gemma acerta emoção e personagem com folga.

### 4.9. "Quem fala" — três camadas, da mais confiável para a menos
A atribuição do personagem a cada fala usa, **nesta ordem**:
1. **Tag determinística** (`_falante_da_tag`) — extrai o nome por regex de verbos de fala:
   "perguntou o **lobo**", "respondeu **Chapeuzinho**", "sua **mãe** disse:". É o mais confiável.
2. **Gemma focada** (`_quem_fala_gemma`) — só quando a tag não resolve (sujeito pronominal,
   imitação, disfarce). Uma pergunta curta com o contexto ao redor, instruindo a apontar o
   **impostor** em casos de disfarce ("o lobo fingindo ser a vovó" → lobo).
3. **Personagem ativo em cena** — último fallback: o pronome ("ele disse") herda o último
   personagem do elenco que estava agindo.

Resultado no teste da Chapeuzinho Vermelho: **19 de 20 falas corretas**, incluindo o lobo
imitando a Chapeuzinho e o caçador (que aparecia só como "ele disse").

### 4.10. Ritmo e teatralidade
- **Slider de ritmo** (padrão 0,90, mais devagar): história pede um tempo mais pausado.
- **Abertura lúdica**: a 1ª frase sai a × 0,82 — aquele "Era uma vez..." arrastado que fisga.
- **Fechamento**: a última frase também desacelera (× 0,85), fechando no mesmo tom.

### 4.12. Áudio de fundo (música/ambiente)
Opcional: sobe-se um MP3/WAV que entra **por baixo** da narração. `_carregar_fundo` usa
`librosa` (suporta MP3 no Windows), normaliza para o volume escolhido, e `_misturar_fundo`
**loopa** a faixa até cobrir toda a história, com **fade-in/out** nas pontas.
- **Volume do fundo** (slider, 0–0,40; 0 = sem fundo): controla a presença do fundo.
- **Cauda do fundo** (slider, 0–20 s): segundos em que o fundo **continua tocando sozinho
  depois que a voz acaba**. `_misturar_fundo(voz, fundo, cauda_seg)` estende o áudio com
  `cauda_seg` de silêncio na voz e deixa o fundo preencher; o **fade-out cabe na cauda**
  (fundo cheio durante a fala, desvanecendo só depois). Com cauda 0, mantém o fade de 4 s no fim.

### 4.11. Modo sussurro (ASMR) — whisperização
**Desafio:** a primeira versão (ruído modulado pela amplitude) soava como **chiado**, porque
jogava fora os formantes — os ressonadores que tornam o sussurro inteligível.

**Solução:** `_sussurro()` faz **whisperização** de verdade via STFT:
- **mantém a envoltória espectral** (formantes, suavizando a magnitude para apagar os
  harmônicos = o pitch);
- **excita com ruído aspirado + fase aleatória** (remove o tom, vira sopro).

Assim o sussurro fica inteligível (formantes preservados, correlação ~0,97) e sem pitch.

---

### 4.13. Modalidade Comédia (sonoplastia / auditório)
A aba **🎪 Comédia** é um programa de auditório (Ratinho): narra com vozes + emoção e acrescenta
efeitos sonoros. Mesmo ciclo de VRAM (Gemma → descarrega → OmniVoice → monta).

- **Formato de roteiro com RÓTULO de falante (`_beats_comedia`):** linha SEM rótulo = o
  **apresentador** (voz base da aba Clone); linha `NOME: fala` = **convidado**, que ganha uma
  voz própria e **consistente** (da `PALETA`). Isso elimina a adivinhação de quem fala — o
  formato travessão+tag dava vozes inconsistentes e atribuições erradas para personagens
  nomeados. Como o falante já vem do rótulo, a Gemma só precisa dar a **emoção** (`_emocao_lote`).
  Nomes-base que viram apresentador: `apresentador`, `narrador`, `plateia`...

- **De onde vêm os sons:** o usuário coloca os arquivos em `app/estudio/sonoplastia/`
  (`.wav`/`.mp3`/...). O **nome do arquivo** é a chave (ex.: `risada.wav`, `rufar.wav`,
  `plateia.wav`). `_catalogo_sfx()` escaneia a pasta e normaliza os nomes (`_norm_sfx`).
  Usa só o que existir; sem arquivos, sai só a narração.
- **O "sonoplasta" (`_classificar_sfx`):** 2ª passada da Gemma (lotes de 12, como
  `_classificar_beats`), feita ANTES de descarregar. Recebe a lista de efeitos disponíveis
  (+ dicas de `DESCR_SFX` para os nomes comuns) e marca por beat `(efeito, posição)` —
  `antes` (suspense antes de revelar), `depois` (reação), `sob` (durante). Valida contra os
  disponíveis (descarta o que a Gemma inventar). Um **pós-filtro de densidade** evita efeitos
  colados, regulado pelo slider **Intensidade**.
- **Apresentadora = PANDORA:** a voz-base (aba Clone) é a apresentadora — secretária de Hades,
  fúnebre/maligna mas debochada e sarcástica. Linhas sem rótulo (ou `PANDORA:`) são dela; ela é
  **expressiva** (emoção varia velocidade e volume, sem pitch p/ o timbre ficar fixo). O exemplo
  e o gerador a fazem se apresentar no início e mandar um recado no fim, sem atrações musicais.
- **Posição dos efeitos é DETERMINÍSTICA** (`POSICAO_SFX`): reação (aplauso/risada/buzina/
  trombone) vem `depois`; suspense (rufar/tambor/suspense/apito) vem `antes` — corrige o
  "palmas tocando antes da fala". Há ainda **gatilhos por palavra** (palmas/aplauso→aplauso,
  segura/suspense→rufar, gargalhada→risada) que forçam o efeito mesmo se a Gemma falhar.
- **Efeitos pontuais curtos:** `DUR_SFX_MAX=2.5s` (corte com fade); a plateia (fundo) não é cortada.
- **Música de abertura (opcional):** upload na aba; toca antes do programa com fade-out
  (`abertura_path`/`vol_abertura` em `sintetizar_comedia`).
- **Plateia de fundo:** se houver um arquivo `plateia` (ou `auditorio`/`audiencia`), ele toca
  em loop por baixo de tudo via `_misturar_fundo`, no volume do slider **Volume da plateia**.
- **Montagem (`_montar_comedia`):** como `_montar` (roomtone + pausas), mas insere os efeitos
  pontuais (antes/depois como segmentos próprios; `sob` somado ao início do beat) e mistura a
  plateia. Volume dos pontuais no slider **Volume dos efeitos**.
- **Botão "🤪 Hora da loucura":** `gerar_roteiro_comedia()` faz a Gemma INVENTAR um programa
  inteiro (temperatura 1.0 + 3 convidados sorteados de `_LOUCURA_CONVIDADOS` → varia a cada
  clique), já no formato de rótulos. `_limpar_roteiro` tira markdown (`**`), rubricas de ação
  entre parênteses (o TTS as leria) e preâmbulos da IA. Preenche o campo de texto.
- **Função:** `sintetizar_comedia(perfil, texto, ritmo, vol_sfx, vol_plateia, intensidade)`
  → `(audio, roteiro)`, roteiro = `[(quem, emoção, texto, efeito)]`.
- Já vêm 2 efeitos **sintéticos** de exemplo (`rufar.wav`, `buzina.wav`, gerados por DSP) para
  funcionar de imediato; o usuário substitui pelos sons reais. Ver `sonoplastia/LEIAME.txt`.

### 4.14. Game Show Educativo (PDF) — aprendizado para crianças
Aba separada (a Comédia fica intacta) que reaproveita TODO o motor da Comédia para um fim
educativo: o **objetivo final** do projeto. Sobe-se um PDF, a Pandora monta um quiz e ensina.

- **`_ler_pdf(path)`** (pypdf): extrai o texto de todas as páginas, colapsa espaços, trunca em
  `MAX_PDF_CHARS=8000` (a Gemma 4B tem contexto limitado). PDF escaneado/imagem (sem texto) não
  funciona (sem OCR).
- **`gerar_gameshow_educativo(conteudo, faixa, n_perguntas)`** (Gemma, temp 0.7): cria o roteiro
  no formato de rótulos (Pandora sem rótulo + convidados `NOME:`). Prompt manda usar SÓ os fatos
  do material, ENSINAR certo para a faixa etária, e montar um quiz com N perguntas — a Pandora
  mantém o tom sarcástico/macabro com os convidados, mas confirma e explica a resposta CERTA
  (a criança aprende). Reusa `_limpar_roteiro`.
- **UI (2 passos):** (1) sobe o PDF + faixa etária + nº de perguntas → "Ler PDF e criar roteiro"
  preenche um campo de texto editável; (2) revisa/edita e "Gerar o game show" → chama o MESMO
  handler `gerar_comedia` (→ `sintetizar_comedia`): vozes + sonoplastia + plateia + abertura.
- Dependências: `pypdf` (leitura). `fpdf2` foi instalado só para gerar PDFs de teste.

## 5. Onde calibrar (resumo dos números)

| Quero ajustar... | Arquivo / função | Parâmetro |
|---|---|---|
| Suavidade do fim (geral) | `motor.py` › `finalizar` | `fade_ms = 260 + 220*abr` |
| Cauda preservada | `motor.py` › `finalizar` | `+ int(0.09 * SR)` (90 ms) |
| Extra para vogais | `motor.py` › `finalizar` | `fade_ms *= 1.25` / limiar ZCR `0.12` |
| Emenda entre beats | `motor.py` › `_montar` | `p_mesmo` (90 ms) / `p_troca` (240 ms) |
| Abertura / fechamento | `motor.py` › `sintetizar_historia` | `*= 0.82` / `*= 0.85` |
| Tamanho do lote da Gemma | `motor.py` | `_LOTE_CLASSIF = 12` |
| Caráter do sussurro | `motor.py` › `_sussurro` | `size=25` (suavização) / mix de ruído |
| Volume/fade do fundo | `motor.py` › `_carregar_fundo` / `_misturar_fundo` | `volume` / `fade = SR*4` |
| Padrão do ritmo | `estudio.py` › Contador de Histórias | `gr.Slider(... value=0.90)` |

---

## 6. Limitações conhecidas

- **Disfarce/imitação ambíguos**: o lobo *disfarçado de vovó* dizendo "Entre, minha criança"
  sai com voz de vovó — coerente com a cena (ele finge ser ela), mas não é o lobo.
- **Gemma 3 4B**: modelo pequeno e local; pode escorregar na emoção ou em um nome raro. A
  atribuição é robusta porque a tag determinística resolve a maioria antes da Gemma.
- **Pasta `saidas/`**: contém áudios de scripts antigos (modo debate, removido). É histórico,
  pode apagar.

---

## 7. Mapa rápido do `motor.py`

- **Modelos**: `carregar_omni` / `descarregar_omni` / `_cfg` / `_gemma` / `descarregar_gemma`
- **Áudio**: `_pitch` `_rms` `_fade_in_cos` `_fade_exp` `_zcr` `finalizar` `_roomtone`
  `_sussurro` `_montar` `_saida`
- **Texto**: `_split_frases` `_normalizar_fala` `_com_ponto` `_beats_historia`
- **Voz de referência**: `estimar_ritmo` `perfil_voz` `_criar_prompt_voz`
- **Síntese**: `_gerar_um` `sintetizar_clone` `sintetizar_design` `sintetizar_historia` `salvar`
- **Classificação (história)**: `_ascii1` `_norm_nome` `_falante_da_tag` `_quem_fala_gemma`
  `_achar_emocao` `_classificar_beats`
