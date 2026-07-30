# Projeto IA — Estúdio de Voz da Pandora

> Documento de detalhamento geral do projeto: o que existe, como surgiu, decisões
> técnicas importantes e o estado atual de cada parte. Para instruções de uso
> específicas, veja os READMEs de cada módulo (linkados abaixo).

## Visão geral

Este repositório reúne um conjunto de ferramentas de **síntese e clonagem de voz
100% locais**, construídas em torno de uma voz de referência chamada **Pandora**
(a persona/voz central do projeto), rodando em uma GPU modesta (RTX 2060, 6 GB de
VRAM) sem depender de serviços pagos.

O projeto começou como um podcast de IAs conversando (**Três Vozes**, usando Claude
API + Google Cloud TTS) e evoluiu para um **Estúdio de Voz** completo: clonagem de
voz, narração de histórias multi-personagem com emoção, um game show educativo,
uma máquina de paródias musicais e um assistente de voz conversacional (**Éris/Pandora**).

## Stack técnica

- **Python 3.14** (ambiente principal) e **Python 3.11** (`.venv_seedvc`, isolado só
  para o seed-vc, que exige versão mais antiga)
- **OmniVoice** — motor de TTS/clonagem de voz local (substituiu Higgs Audio v3 após
  avaliação comparativa; venceu por clonar localmente e suportar PT-BR bem)
- **Gemma 3 4B via Ollama** — o "cérebro" que interpreta texto, decide emoções e
  gera roteiros/quizzes/paródias
- **Demucs** — separação de fontes de áudio (extrai vocal de faixas musicais)
- **seed-vc** — voice conversion zero-shot (faz a Pandora "cantar" músicas existentes)
- **Whisper (GPU)** — transcrição de fala para o assistente de voz
- **FastAPI** (estúdio web, porta 5008) e **Gradio** (estúdio clássico, portas 5006/5007)
- **Google Cloud TTS** + **Claude API** — usados apenas no protótipo original (Três Vozes),
  hoje substituído pela stack 100% local

Restrição estrutural que molda quase todo o código: **a GPU de 6 GB não comporta a
Gemma e o OmniVoice/Demucs/seed-vc ao mesmo tempo**. Por isso praticamente todo
pipeline segue o padrão *carrega modelo → usa → descarrega → limpa VRAM → carrega o
próximo*.

## Linha do tempo / evolução

### 1. Três Vozes (protótipo inicial)
Podcast com 3 IAs (ÉRIS, LYRA, NOVA) conversando entre si e com o usuário, usando
Claude API para texto e Google Cloud TTS para voz (3 vozes `pt-BR-Standard`), com
memória persistente em JSON por personagem. Arquivos: `app/tres_vozes*.py`,
`podcast_tres_vozes/`. Descontinuado como direção principal — a stack paga (Google
TTS) foi abandonada em favor de síntese local.

### 2. Avaliação do motor de voz
Comparação entre candidatos (incluindo Higgs Audio v3) para escolher o motor de TTS
local definitivo. **OmniVoice venceu**: clonagem local funcional, suporte a PT-BR,
e viabilidade na RTX 2060. Voz de referência escolhida: `pandora_007` (sem chiado
perceptível). Lição de infraestrutura: o ciclo de troca de VRAM entre Gemma e
OmniVoice precisa ser explícito e cuidadoso (ver `motor.py`/`motor_v2.py`).

### 3. Estúdio de Voz (reescrita, Gradio)
Primeira versão "de produto" do estúdio, em `app/estudio/estudio.py` +
`app/estudio/motor.py`, com 3 abas:
- **Clone de Voz** — clona qualquer voz de referência (≥3s de áudio)
- **Design de Voz** — gera voz sintética por características (gênero/idade/tom)
- **Contador de Histórias** — narra histórias dando voz própria a cada personagem,
  com emoção por trecho (a Gemma decide quem fala e com que emoção)

Depois expandida para 5 abas com **Comédia (auditório)** (sonoplastia tipo
programa de auditório) e **Game Show Educativo (PDF)** (lê um PDF e gera quiz).
Documentação completa em `app/estudio/DOCUMENTACAO.md`.

Decisões técnicas notáveis (detalhadas em `DOCUMENTACAO.md` §4):
- `load_asr=False` no OmniVoice — o transcritor embutido (Whisper) dependia de
  DLLs do FFmpeg/torchcodec ausentes no Windows; a transcrição da voz de referência
  é fornecida manualmente via `.txt` ao lado do `.wav`
- Síntese em geração única (não frase-a-frase), para evitar que o OmniVoice
  "comesse" a primeira sílaba

### 4. Estúdio Web (v2, FastAPI)
Reescrita da camada de servidor: `app/estudio/estudio_web.py` (FastAPI, porta 5008)
+ `app/estudio/motor_v2.py` + frontend puro em `app/estudio/static/index.html`
(HTML/CSS/JS sem framework). Fila de tarefas com uma única thread worker
persistente, serializando todo uso de GPU. Suporta múltiplos personagens
(`app/estudio/personagens/*.json`) e histórias multi-voz. Deve rodar sempre com
`.venv_omni`. Documentação de engenharia em `app/estudio/MANUAL_MANUTENCAO.md` e
dicionário de funções em `app/estudio/FUNCOES_REFERENCIA.md`.

### 5. Pandora — assistente de voz conversacional
`app/eris_pandora.py`: assistente que ouve o microfone (detecção de atividade de
voz/VAD), transcreve com Whisper na GPU, e responde com a personalidade própria da
Pandora (definida em `pandora_personalidade.md`), sintetizando a resposta com
OmniVoice residente em memória. Otimizado para latência: manter o OmniVoice
carregado e um pipeline "quente" reduz o primeiro som a ~4,5s.

### 6. Battle — debate por persona
Sistema de debate onde cada personagem tem um "dossiê" próprio e uma chamada de
LLM independente (uma persona por chamada, não uma única geração compartilhada).
Resolveu o problema da voz "travada"/robótica no fim das falas com a técnica
**FIXP2**: velocidade 0.80 + curva de entonação específica da Pandora aplicada ao
final da fala — nunca usando time-stretch (que soa artificial).

### 7. Canto — a Pandora cantando músicas existentes
`app/estudio/canto_musica.py` / `app/estudio/canto_lote.py` (+ protótipo em
`app/laboratorios/canto_lab.py`). Pipeline validado:
1. **Demucs** separa a faixa vocal do instrumental
2. **seed-vc** (voice conversion zero-shot, em `.venv_seedvc`/Python 3.11) converte
   o vocal separado para a voz da Pandora, preservando afinação e ritmo da música
   original

Uma tentativa anterior de pitch-shift diretamente no TTS foi abandonada — o
resultado soava robótico. A causa raiz da desafinação em geral está na qualidade
da separação de fonte (Demucs), não na conversão de voz em si. O modo lote e um
player com waveform foram adicionados depois de validado o pipeline single-track.

### 8. Meditação Guiada (laboratório)
Experimento de análise acústica de uma referência de narração para meditação
guiada. O clone direto da referência foi descartado (Demucs não separava bem o
áudio de fundo/música ambiente da voz). O maior problema identificado foi o
"pitch rising" (a entonação subindo ao longo da fala) — não totalmente resolvido.

### 9. Máquina de Paródias
`app/estudio/parodia.py`: Fase 1 implementada — gera letra de paródia
respeitando métrica e rima da música original, usando a Gemma. Próximo passo
identificado: uma etapa de estruturação poética (a Gemma reorganiza a
transcrição original em versos bem definidos) antes da análise de rima, para
melhorar a qualidade da paródia gerada.

## Estrutura de diretórios (resumo)

```
app/
  eris_pandora.py          # assistente de voz conversacional (Pandora)
  fundo_bar.py              # utilitário de áudio de fundo
  pokemon_ai.py             # experimento à parte
  tres_vozes*.py             # protótipo original (Claude + Google TTS)
  estudio/
    estudio.py, motor.py           # Estúdio de Voz v1 (Gradio, 5 abas)
    estudio_v2.py, motor_v2.py     # Estúdio de Voz v2 (experimental)
    estudio_web.py                 # Estúdio Web (FastAPI, porta 5008) — versão atual
    canto_musica.py, canto_lote.py # Pandora cantando músicas (Demucs + seed-vc)
    parodia.py                     # Máquina de Paródias
    static/index.html              # frontend do Estúdio Web
    personagens/*.json             # dossiês de personagens (Battle, histórias)
    vozes/                         # referências de voz (Pandora.wav + .txt)
    DOCUMENTACAO.md                 # visão de produto
    MANUAL_MANUTENCAO.md            # visão de engenharia
    FUNCOES_REFERENCIA.md           # dicionário de funções
  laboratorios/
    canto_lab.py, demucs_saida/    # experimentos de canto e separação de fonte
    .venv_seedvc/                  # venv isolado (Python 3.11) para seed-vc
documentacao/                       # guias, relatórios e material de apoio
```

## Como rodar (resumo — veja cada README para detalhes)

- **Estúdio Web (recomendado, versão atual):**
  `.venv_omni\Scripts\python.exe app\estudio\estudio_web.py` → http://127.0.0.1:5008
- **Estúdio de Voz clássico (Gradio):**
  `app\estudio\INICIAR_ESTUDIO.bat` → http://127.0.0.1:5006
- **Pandora (assistente de voz):** `.venv_omni\Scripts\python.exe app\eris_pandora.py`

Pré-requisitos comuns: Ollama rodando com `gemma3:4b` (`ollama pull gemma3:4b`), e
o ambiente `.venv_omni` com `omnivoice`, `gradio`/`fastapi`, `librosa`,
`soundfile`, `torch`. O canto usa adicionalmente `.venv_seedvc` (Python 3.11) e
Demucs.

## Estado atual / próximos passos conhecidos

- Estúdio Web (FastAPI) é a versão em uso ativo; v1 (Gradio) e v2 permanecem no
  repositório como histórico/fallback.
- Máquina de Paródias: falta a etapa de estruturação poética antes da análise de
  rima (ver seção 9).
- Meditação Guiada: pitch rising na narração longa ainda não resolvido.
- Três Vozes (Claude + Google TTS) é considerado obsoleto frente à stack local,
  mantido no repositório por histórico.
