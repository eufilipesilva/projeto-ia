# Manual de Manutenção — Estúdio de Voz (estudio_web)

> Atualizado em jul/2026, após a revisão e otimização geral.
> Complementa a `DOCUMENTACAO.md` (visão de produto). Este arquivo é a visão de **engenharia**:
> como o servidor funciona por dentro, onde mexer, e as pegadinhas de cada área.

---

## 1. Mapa geral do sistema

```
NAVEGADOR (static/index.html — HTML+CSS+JS puro, sem framework)
    │  fetch POST multipart → recebe {task_id} → pollTask() a cada 800ms
    ▼
ESTUDIO_WEB.PY (FastAPI, porta 5008, roda no .venv_omni / Python 3.14)
    │  rota valida entrada → salva uploads em saidas/tmp_web → _run_task(fn)
    ▼
FILA DE TAREFAS (_task_queue + UMA thread worker persistente)
    │  serializa TODO uso de GPU (6 GB não comportam 2 modelos juntos)
    ▼
┌─────────────────────┬──────────────────────────────────────────┐
│ MOTOR_V2.PY         │ CANTO_MUSICA.PY / CANTO_LOTE.PY          │
│ OmniVoice (TTS,     │ Demucs (separa) → subprocess seed-vc     │
│ clone, design) +    │ (.venv_seedvc, Python 3.11) → mixagem    │
│ Gemma via Ollama    │ inference.py / converter_lote.py         │
│ (roteiros/LLM)      │ (app/laboratorios/seed-vc/)              │
└─────────────────────┴──────────────────────────────────────────┘
```

**Regra de ouro nº 1 — os dois Pythons:** o estúdio roda no `.venv_omni` (3.14);
o seed-vc SÓ roda no `.venv_seedvc` (3.11, em `app/laboratorios/`). Nunca importe
seed-vc no estúdio — a comunicação é por **subprocess** (caminhos absolutos!, o
cwd do subprocess é `SEEDVC_DIR`).

**Regra de ouro nº 2 — uma coisa na GPU por vez:** RTX 2060 6GB. A thread worker
única serializa as tasks; o `gerar_canto` descarrega o OmniVoice
(`motor.descarregar_omni()`) antes do Demucs/seed-vc. Se criar rota nova que usa
GPU, **sempre** passe por `_run_task` — nunca rode direto na rota.

**Regra de ouro nº 3 — rotas `async def` não podem bloquear:** chamada demorada
(Gemma, síntese) dentro de `async def` congela o servidor INTEIRO. Ou enfileira
na worker (`_run_task`), ou declara a rota como `def` (síncrona — o FastAPI roda
num threadpool). Exemplo: `/api/gameshow/pdf` é `def` de propósito.

---

## 2. Organograma das funções (estudio_web.py)

### Infraestrutura (linhas ~20–230)
| Função | Papel | Mexer quando... |
|---|---|---|
| `_save_audio(audio, sr)` | grava o resultado de uma task em `tmp_web/uuid.wav` | mudar formato de saída |
| `_perfil_de_voz(nome)` | nome de voz salva → perfil de clone (`motor.perfil_voz`) | — |
| `_avaliar_meditacao(...)` | métricas de qualidade da meditação (silêncio, pitch...) | recalibrar metas de qualidade |
| `_parse_bool(val)` | FormData manda "true"/"false" como string (bug clássico) | nunca — use sempre em bools de forms |
| `_audio_response(path)` | FileResponse wav com no-cache | — |
| `_prog_fn(task_id)` | cria callback `progresso(frac, desc)` que atualiza a task | — |
| `_executar_tarefa` | interpreta o retorno da fn: `(sr,audio)`, `((sr,audio),texto)` ou `{"batch": [...]}` | criar novo TIPO de retorno |
| `_worker_loop` | consome a fila; captura exceções → `status="error"` | — |
| `_podar_tasks()` | mantém só as últimas 30 tasks; apaga áudios das velhas do disco | mudar retenção |
| `_varrer_tmp_antigos()` | no startup, apaga da tmp_web o que tem >24h | mudar janela de limpeza |
| `_run_task(tid, fn)` | poda + registra task + enfileira | — |
| `_salvar_upload(up, suffix)` | UploadFile → arquivo temporário (padrão único p/ uploads) | SEMPRE que criar rota com upload |
| `listar_vozes` | lista `vozes/*.wav` (cache invalida por mtime da pasta) | — |
| `task_status` / `task_audio` / `task_audio_lote` | polling e entrega de áudio (single e lote) | — |

### Estado em memória (zera ao reiniciar o servidor)
- `_sessions` — session_id → perfil de voz analisado (aba Clone)
- `_tasks` — task_id → status/progresso/áudio (podado em 30)
- `_historicos` — session_id → histórico do Personagem Infinito (máx. 10 trocas)

### Rotas por aba
```
CLONE      /api/voice/analyze  → perfil_voz (corte opcional do clipe)
           /api/voice/clone    → sintetizar_clone
DESIGN     /api/voice/design   → interpretar_descricao_voz + sintetizar_design
HISTÓRIAS  /api/story          → sintetizar_historia (+fundo)
COMÉDIA    /api/comedy         → sintetizar_comedia | /api/comedy/random (roteiro Gemma)
GAME SHOW  /api/gameshow/pdf   → _ler_pdf + gerar_gameshow_educativo (rota def/threadpool!)
           /api/gameshow       → delega para gerar_comedia
TRAILER    /api/trailer        → gerar_roteiro_trailer + clone OU design + fundo
MEDITAÇÃO  /api/meditation     → gerar_meditacao (script Gemma) + sintetizar_clone_lote
                                 + parser de pausas + EQ/ducking/binaural (TUDO inline na rota)
RÁDIO      /api/radio          → gerar_radio (segmentos) + clone/comedia por segmento
BATALHA    /api/battle         → gerar_batalha[_persona] + vozes por lado + montagem
PERSONAGEM /api/character/create|list|chat|reset  (fichas em personagens/*.json)
CANTAR     /api/sing           → canto_musica.gerar_canto (single)
           /api/sing_batch     → canto_lote.gerar_canto_lote (modelos seed-vc 1x)
           (_resolver_voz_ref: voz da galeria OU upload com corte)
```

### O pipeline do canto (o mais complexo)
```
gerar_canto (canto_musica.py)
 ├─ motor.descarregar_omni()                  # libera VRAM
 ├─ separar_vocal_instrumental()              # Demucs (cache GPU), 44.1kHz
 ├─ calcular_semi_tone_shift()                # pyin rápido; LIMITADO a [0,+8]
 │    └─ _limitar_shift: NUNCA abaixa (decisão do Filipe: abaixar engrossa)
 ├─ calcular_teto_pitch(voz_ref)              # mediana da REF + 12 → teto belting
 ├─ converter_voz()                           # subprocess inference.py com
 │    --teto-midi X --suavizar-janela 9       # tratamento automático de belting
 ├─ mixar()                                   # voz 1.0 + instrumental vol
 └─ finally: _limpar(temporários)
```
No `inference.py` (seed-vc), a ordem de tratamento do F0 é:
`auto_f0 → pitch_shift → preencher_buracos → suavizar → teto`.
Mecanismos extras (`preencher_buracos_f0`, `suavizar_f0_adaptativo`, gate de
altura) existem mas ficam **desligados por padrão** — a receita simples venceu.

---

## 3. Guia de manutenção — receitas prontas

### Adicionar uma nova aba/feature
1. **Backend**: criar rota POST em `estudio_web.py` seguindo o padrão:
   uploads via `await _salvar_upload(...)`, validação com `HTTPException(400,...)`,
   trabalho pesado dentro de `def _fn(progresso): ...` + `_run_task`.
   Retorno da `_fn`: `(sr, np.array)` ou `((sr, array), "texto")`.
2. **Frontend**: copiar um `<section class="section" id="sec-X">` no index.html,
   adicionar `nav-item` com `data-section`, função JS com `FormData` + `pollTask`.
3. Lembrar: bool no FormData → mandar string e ler com `_parse_bool`.

### Mexer nos parâmetros do canto
- Defaults da UI: sliders no `sec-sing` do index.html (steps=50, cfg=0.7).
- Defaults do backend: assinaturas de `/api/sing[_batch]`.
- Receita de belting: constantes em `canto_musica.py`
  (`_TETO_OFFSET_SEMITONS=12`, `_SUAVIZAR_JANELA=9`, `_SHIFT_MIN_AUTO=0`, `_SHIFT_MAX_AUTO=8`).

### Diagnosticar "música saiu ruim"
1. É **ao vivo/paredão/rap/gritada**? → limitação da fonte (ver memória: preditor =
   registro perto da voz-alvo + fonte de estúdio limpa).
2. Voz de referência de upload é limpa? Rua/multidão NÃO clona (caso Bolsonaro).
3. Voz "grossa"? → conferir se `_limitar_shift` está ativo (piso 0).
4. Picos quebrando? → teto automático deveria agir; conferir se a rota passa
   `--teto-midi` (log do subprocess mostra o comando).

### Diagnosticar servidor travado / lento
- `nvidia-smi` → VRAM cheia? Processos `python` órfãos de inference.py? Matar os
  órfãos (NUNCA o PID que escuta a porta 5008 — `netstat -ano | findstr 5008`).
- Task presa em "Na fila..." → outra task na frente na worker (é serial). O botão
  da aba Cantar agora bloqueia duplo-clique, mas outras abas ainda permitem.
- Console com `UnicodeEncodeError` → é só print de emoji no cp1252, inofensivo.
  Em scripts de teste, usar `sys.stdout.reconfigure(encoding='utf-8')`.

### Limpeza de disco
- `saidas/tmp_web` — limpa sozinha: resultados de tasks são podados (30 últimos)
  e o startup varre >24h. Uploads das rotas de canto são apagados no `finally`.
- `saidas/canto_lote` — resultados FINAIS do lote: **não** são apagados (de
  propósito — é o que o usuário baixa). Limpar manualmente quando acumular.
- `app/laboratorios/teste_*` — pastas de experimentos; podar quando quiser.

---

## 4. Manual de cada aba (visão do usuário)

### 🎤 Clone de Voz (Essencial)
Suba um áudio OU escolha voz salva → **corte o trecho** na waveform (alças) →
"Analisar" cria a sessão → digite texto → "Gerar". A sessão vale pra outras abas
(Histórias, Comédia, Rádio...). Dica: clipe de 5–15s, voz limpa, sem música.

### ✦ Design de Voz (Essencial)
Descreva a voz em português ("mulher rouca, madura") → Gemma traduz pra instrução
do sintetizador → gera. Não precisa de áudio de referência.

### 📖 Contador de Histórias (Produção)
Texto longo narrado com a voz da sessão. Opções: ritmo, sussurro, música de fundo
(upload) com volume e cauda. Saída mostra o roteiro interpretado (emoções).

### 🎪 Comédia / 🎓 Game Show (Produção)
Programa de auditório com sonoplastia automática (efeitos + plateia). Linhas
normais = apresentador. Game Show: suba um PDF → passo 1 gera o quiz (Gemma),
passo 2 sintetiza com a mesma engine da comédia. "Roteiro aleatório" disponível.

### 🎬 Gerador de Trailer (Produção)
Logline + gênero → roteiro épico (Gemma) → narração com voz da galeria (ou voz
grave de design) + música de fundo opcional.

### 🧘 Meditação Guiada (Imersão)
Tema + duração → script com pausas reais (~65% de silêncio), EQ de calor, ducking
da música de fundo, export binaural 44.1kHz estéreo. Modo ASMR (EN/PT) usa vozes
especiais (`_asmr_*.wav`). Gera relatório de qualidade automático.

### 📻 Rádio Pandora (Imersão)
Tema → episódio completo (abertura, notícias, entrevista com 2 vozes, quadro
filosófico, encerramento) com vinheta opcional.

### ⚔️ Batalha de Vozes (Avançado)
2 personagens debatem um tema. Voz de cada um: galeria OU descrição (design com
timbre travado). **Dossiês** (.txt/.pdf) transformam em debate por persona (cada
lado é um agente com sua identidade). Caimento natural das falas (speed 0.80).

### 🎭 Personagem Infinito (Avançado)
Crie fichas (nome, personalidade, voz, cacoetes) → converse por texto e ouça a
resposta na voz do personagem. Histórico de 10 trocas por sessão.

### 🎶 Cantar Música (Experimental)
Suba 1 música (ou VÁRIAS → modo lote automático) + voz da galeria OU trecho de
voz por upload (com corte na waveform). O pipeline separa o vocal (Demucs),
converte o timbre (seed-vc) e mixa. **Automático por baixo**: shift de registro
(só sobe, nunca abaixa), teto de belting moldado à voz escolhida, suavização leve.
Player waveform estilo SoundCloud + botão de download por faixa.
**Escolha músicas de ESTÚDIO** (nunca ao vivo/paredão; rap e rock gritado não
funcionam — ver memória do projeto).

---

## 5. Anti-regressões (o que NÃO mudar sem pensar 2x)

1. `_worker_thread` única — thread nova por task causa segfault CUDA no Windows.
2. Piso do shift automático = 0 (`_SHIFT_MIN_AUTO`) — abaixar engrossa a voz.
3. Demucs salva com `soundfile`, NUNCA `torchaudio.save` (DLL quebrada no Windows).
4. seed-vc: torch 2.11+cu128 (a versão pinada do requirements dá erro de DLL).
5. Caminhos pro subprocess do seed-vc: SEMPRE absolutos (cwd é outro).
6. `sintetizar_clone_pandora` speed 0.80 no Battle — NUNCA time-stretch p/ caimento.
7. Meditação: alvo 60–68% de silêncio; permanência capada em 35s.
8. `tmp_web`: não apagar manualmente COM O SERVIDOR RODANDO tarefa (quebra a
   mixagem em andamento — já aconteceu). A limpeza automática cuida disso.
