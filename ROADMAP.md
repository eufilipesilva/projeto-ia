# Roadmap Futuro — Plano Técnico

> Detalhamento de cada item do roadmap do `PROJETO.md`: ferramentas/pacotes candidatos,
> comparação entre alternativas, viabilidade na RTX 2060 (6 GB VRAM), pontos exatos de
> integração no código atual (`motor_v2.py`, `estudio_web.py`) e um plano de passos
> incremental. Pesquisa feita em jul/2026. Tudo priorizando **ferramentas
> gratuitas/open-source**, coerente com o resto do projeto.

Restrição que atravessa quase todos os itens: a GPU tem 6 GB e já não comporta Gemma +
OmniVoice ao mesmo tempo (`_esperar_vram_livre`, `descarregar_gemma`, `descarregar_omni`
em `motor_v2.py`). Qualquer modelo novo (lip-sync, alinhamento forçado) entra no mesmo
ciclo *carrega → usa → descarrega* — nunca em paralelo com Gemma/OmniVoice.

---

## 1. Dub automático de vídeos (exportar vídeo + áudio síncrono)

**Ideia:** pegar um vídeo, transcrever a fala, (opcionalmente) traduzir, sintetizar com a
voz da Pandora (ou uma voz clonada do próprio falante) e remontar o vídeo com o áudio
novo, sincronizado em duração.

### Ferramentas e por quê

| Etapa | Ferramenta | Por quê essa e não outra |
|---|---|---|
| Extrair áudio | `ffmpeg` (CLI, já usado no projeto) | Já é dependência de fato; sem necessidade de `moviepy` (mais pesado, reimplementa o que o ffmpeg já faz) |
| Transcrever c/ timestamps | **Whisper** (já usado em `eris_pandora.py`) | Reaproveita modelo/pipeline já validado no projeto; usar o tamanho `medium` ou `small` para caber em VRAM junto do resto |
| Traduzir (opcional) | **Argos Translate** (offline, MIT) *ou* Gemma via prompt | Argos roda sem GPU e sem limite de caracteres (ao contrário de APIs pagas); Gemma já está no projeto mas some da VRAM o tempo que estiver traduzindo — para textos curtos por segmento isso é barato |
| Sintetizar dublagem | **OmniVoice** (já no projeto) | `sintetizar_clone_lote()` já existe em `motor_v2.py` e já aceita lista de textos + parâmetro `language` |
| Remontar vídeo | `ffmpeg` | Comando único, sem re-encode de vídeo (`-c:v copy`) |
| Lip-sync (opcional, fase 2) | **Wav2Lip** | O único dos modelos de lip-sync que roda confortavelmente em 6 GB. **LatentSync** (ByteDance, diffusion) e **MuseTalk** dão qualidade bem superior mas exigem mais VRAM — testar à parte, fora do ciclo Gemma/OmniVoice, e provavelmente em resolução reduzida |

### Ponto de integração no código

Não existe hoje nenhuma noção de "vídeo" no projeto — é 100% áudio. Este item cria um
módulo novo, por exemplo `app/estudio/dub_video.py`, que:
- importa `motor_v2` para reaproveitar `carregar_omni()`, `descarregar_omni()`,
  `sintetizar_clone_lote()` e o ciclo de VRAM já existente
- não mexe em `estudio_web.py` além de adicionar uma rota nova (`POST /dub`) que recebe
  um upload de vídeo, igual ao padrão de upload de PDF já usado na aba Game Show

### Plano de passos

1. **Extração:** `ffmpeg -i video.mp4 -vn -acodec pcm_s16le audio.wav`
2. **Transcrição com timestamps:** rodar Whisper com `word_timestamps=True` (ou pelo
   menos por segmento) — decidir o tamanho do segmento por pausa natural, não por frase
   gramatical (evita cortar no meio de uma respiração)
3. **Tradução (se aplicável):** cada segmento vira um prompt curto para a Gemma
   (`"Traduza para {idioma}, mantendo o tom: {texto}"`) — reaproveita `_gemma()`
4. **Ajuste de duração antes de sintetizar:** calcular `duração_alvo = fim - início` do
   segmento original; sintetizar uma vez, medir a duração do áudio gerado e recalcular
   `speed = duração_gerada / duração_alvo` numa segunda passada — o `_gerar_um()` já
   aceita `speed` como parâmetro, então isso é reaproveitável direto
5. **Concatenar respeitando timestamps:** preencher os intervalos entre falas com
   silêncio (não colar os segmentos "grudados"), usando `numpy.pad`/`soundfile`
6. **Remuxar:** `ffmpeg -i video.mp4 -i audio_dublado.wav -c:v copy -map 0:v -map 1:a -shortest saida.mp4`
7. **Fase 2 (opcional):** passar `saida.mp4` pelo Wav2Lip — nesse ponto o vídeo já tem o
   áudio final, então o Wav2Lip só precisa ajustar a boca a esse áudio

### Riscos / pegadinhas
- Ajuste de `speed` tem limite de naturalidade — acima de ~1.3x ou abaixo de ~0.75x a voz
  já soa artificial (o projeto já bateu nisso: ver a lição de "nunca time-stretch" no
  `PROJETO.md`, seção Battle) — para segmentos que não cabem nem ajustando o *speed*,
  melhor permitir o vídeo "esticar" (freeze de frame) que forçar uma voz robótica
- Vídeos com múltiplos falantes exigiriam diarização (quem fala quando) — fora de escopo
  da primeira versão; começar com vídeos de um falante só

---

## 2. Podcast generator (episódios em série com hosts salvos)

**Ideia:** reaproveitar o sistema de personagens (`app/estudio/personagens/*.json`) para
manter "hosts" fixos com voz e personalidade, gerar episódios em lote e publicar como
feed RSS de podcast de verdade (assinável em qualquer app de podcast).

### O que já existe e pode ser 100% reaproveitado
- `app/estudio/personagens/*.json` já define um personagem com `nome`, `personalidade`,
  `vozes_desc`, `quirks`, `tom_emocional` (ver `João.json`) — isso já é o "host" pronto
- `gerar_radio(tema)` em `motor_v2.py` já gera um episódio de rádio de 5 segmentos —
  ponto de partida natural em vez de escrever geração do zero
- `gerar_batalha_persona()` já gera diálogo entre duas personas com chamadas de LLM
  separadas por persona (documentado como a técnica certa no `PROJETO.md`, seção Battle)

### Ferramentas novas
| Ferramenta | Uso | Por quê |
|---|---|---|
| **python-feedgen** | Gerar `feed.xml` com tags iTunes (`itunes:author`, `itunes:episode`, `itunes:duration`, `itunes:image`) | Mais completa e mantida; suporta tanto RSS quanto Atom, e a extensão de podcast já vem pronta (não precisa montar XML na mão) |
| **rfeed** | Alternativa de arquivo único, mais simples | Se quiser dependência mínima em vez de instalar mais um pacote — trade-off de simplicidade vs. flexibilidade |
| `mutagen` (opcional) | Ler duração exata do MP3 gerado para preencher `itunes:duration` sem calcular na mão | Já é dependência comum de projetos de áudio Python, leve |

### Ponto de integração no código
- Novo módulo `app/estudio/podcast.py`: função `gerar_episodio(hosts: list[str], tema)`
  que carrega os JSONs de `personagens/`, chama algo equivalente a
  `gerar_batalha_persona`/`gerar_radio` mas para N hosts (não só 2), sintetiza cada fala
  com `sintetizar_clone_lote()` por host e concatena em um `.mp3` único
- Persistir metadados do episódio (`titulo`, `data`, `hosts`, `duracao`, `arquivo`) em
  `app/estudio/podcast/episodios.json` — mesmo padrão de "estado em JSON" que o projeto
  já usa (perfis de voz, transcrições de referência)
- Nova rota em `estudio_web.py`: `GET /podcast/feed.xml` que lê `episodios.json`,
  regenera o feed com `python-feedgen` e retorna `Response(media_type="application/rss+xml")`
- Servir os `.mp3` como arquivos estáticos (`app.mount("/podcast/audio", StaticFiles(...))`,
  seguindo o mesmo padrão de `static/` que já existe)

### Plano de passos
1. Criar `personagens/*.json` para os hosts fixos do podcast (reaproveita o schema atual)
2. Escrever `gerar_episodio()`: N chamadas de Gemma (uma por host, por "rodada" de fala,
   como no Battle) até fechar um roteiro de tamanho-alvo
3. Sintetizar cada fala com a voz do host certo e concatenar com silêncios entre falas
4. Salvar o episódio + metadados
5. Implementar geração do `feed.xml` com python-feedgen a partir de `episodios.json`
6. Expor `/podcast/feed.xml` e `/podcast/audio/*.mp3` no FastAPI
7. Testar assinando o feed local num app de podcast (ex.: apontando para
   `http://<ip-da-máquina>:5008/podcast/feed.xml` na mesma rede)

### Riscos / pegadinhas
- iTunes/Apple Podcasts exige uma imagem de capa (`itunes:image`) com URL pública/https
  para indexação em diretórios reais — para uso pessoal/local isso não importa, mas se a
  meta for publicar de verdade, precisa de hospedagem com HTTPS
- `itunes:duration` errado quebra a barra de progresso em alguns players — vale calcular
  a duração real do arquivo gerado, não estimar

---

## 3. Karaokê com sincronização lip-sync

**Ideia:** dado um áudio cantado (ex.: a Pandora cantando, já produzido pelo pipeline de
Canto: Demucs + seed-vc) + a letra, gerar legendas estilo karaokê (palavra por palavra) e,
opcionalmente, um vídeo com avatar sincronizando a boca.

### Ferramentas e por quê
| Etapa | Ferramenta | Por quê essa e não outra |
|---|---|---|
| Timestamp por palavra | **WhisperX** | Faz Whisper + alinhamento forçado com wav2vec2 — dá timestamp por *palavra*, não só por frase. É mais preciso que Whisper puro para esse caso e mais fácil de integrar em Python que o **aeneas** (que é mais antigo, C+Python, e pensado para audiolivro/fala, não canto) |
| Legendas karaokê | Arquivo **`.ass`** (Advanced SubStation Alpha) | Formato pensado justamente para isso: suporta destacar progressivamente cada palavra dentro de uma linha (efeito `\k` de karaokê), coisa que `.srt` não faz |
| Queimar legenda no vídeo | `ffmpeg` (`-vf "ass=letra.ass"`) | Já é dependência do projeto; não precisa de outra lib de vídeo |
| Lip-sync do avatar (opcional) | **Wav2Lip** | Mesma escolha do item 1 — mais leve para 6 GB. Só faz sentido **se existir um vídeo/rosto de referência da Pandora**, que o projeto hoje não tem |

### Ponto de integração no código
- Reaproveita diretamente a saída de `canto_musica.py`/`canto_lote.py` (vocal já
  convertido para a voz da Pandora) como entrada de áudio
- Novo módulo `app/estudio/karaoke.py`: `gerar_ass(audio_path, letra) -> caminho.ass`
- Se for gerar vídeo (não só o `.ass`), um fundo simples (cor sólida, imagem estática, ou
  waveform renderizada com `matplotlib`/`ffmpeg -f lavfi -i showwaves`) já entrega um
  "vídeo de karaokê" funcional sem precisar de avatar nenhum

### Plano de passos
1. Partir do vocal já isolado/convertido pelo pipeline de Canto + letra em texto puro
2. Rodar WhisperX no vocal (idealmente antes da conversão de voz, no vocal original
   separado pelo Demucs — tende a alinhar melhor que no vocal já convertido) para obter
   timestamp por palavra
3. Gerar o `.ass` com destaque progressivo de cada palavra no tempo certo (formato
   `{\k<duração_em_centissegundos>}palavra`)
4. Gerar um vídeo de fundo simples (cor sólida ou waveform) do tamanho da música
5. Queimar as legendas: `ffmpeg -i fundo.mp4 -i vocal_final.wav -vf "ass=letra.ass" -shortest karaoke.mp4`
6. **Fase 2 (opcional, exige vídeo/rosto de referência que ainda não existe no projeto):**
   gravar um vídeo curto de referência (rosto falando) e aplicar Wav2Lip usando o áudio
   final como guia

### Riscos / pegadinhas
- Alinhamento forçado em **canto** é notoriamente mais difícil que em fala (variação de
  pitch e sustentação de vogais atrapalha o alinhador) — validar com uma música curta
  antes de automatizar em lote; pode precisar de ajuste manual pontual
- Sem um rosto de referência gravado, "lip-sync" nesta feature vira, na prática, só as
  legendas karaokê — ainda assim é um karaokê funcional e é a parte de maior valor/esforço

---

## 4. Voice cloning de 3s para qualquer personagem

**Ideia:** reduzir o requisito de referência de voz da aba Clone (hoje pensada para
clipes de ≥3s da Pandora, ver `DOCUMENTACAO.md`) para funcionar bem com clipes curtos de
**qualquer** voz, não só a de referência atual.

### O que já existe
- `perfil_voz(ref_path, ref_text=None, base_speed=None)` em `motor_v2.py` já é genérico:
  aceita qualquer `.wav` de referência, cacheia a transcrição em um `.txt` ao lado
  (`txt_cache`) e monta o prompt de clone (`_criar_prompt_voz`)
- O clone em si (zero-shot) já é a proposta central do **OmniVoice** — não precisa de
  ferramenta nova para a síntese; o trabalho aqui é de **robustez do pipeline de entrada**

### Ferramentas novas
| Ferramenta | Uso |
|---|---|
| `librosa` (já é dependência do projeto) | `librosa.effects.trim()` para cortar silêncio nas pontas do clipe antes de mandar pro OmniVoice; medir duração de fala útil após o trim |
| **Whisper** (já usado em `eris_pandora.py`) | Gerar automaticamente o `ref_text` do clipe novo, eliminando o passo manual de escrever a transcrição a mão |

### Ponto de integração no código
- `perfil_voz()` já tem o parâmetro `ref_text=None` com fallback para cache em `.txt` —
  hoje, se não existir nem `ref_text` nem cache, o clone quebra silenciosamente ou usa
  string vazia (`ref_text or ""` em `_criar_prompt_voz`). O ajuste é: se `ref_text` vier
  `None` e não houver cache, rodar Whisper **ali mesmo** (fora do OmniVoice, para não
  disparar o bug documentado de `load_asr=True`/FFmpeg) e gravar o `.txt` automaticamente
- Adicionar validação de duração logo após o upload na rota de clone do `estudio_web.py`:
  rejeitar (ou avisar) se a fala útil após `trim()` for menor que ~1.5–2s

### Plano de passos
1. No upload da referência: normalizar volume (peak normalize) + `librosa.effects.trim`
2. Medir duração da fala útil; se < ~2s, avisar o usuário (qualidade do clone degrada
   muito abaixo disso, não é só uma questão de "funciona ou não")
3. Rodar Whisper na referência já cortada para gerar o `ref_text` automaticamente,
   gravando o `.txt` do jeito que `perfil_voz()` já espera encontrar
4. Testar em lote: pegar ~10 vozes variadas (gênero, idade, idioma) com clipes de 3s e
   comparar contra a referência atual da Pandora (10+s) usando os mesmos
   `guidance_scale`/`inference_steps` — calibrar se clipes curtos precisam de valores
   diferentes desses parâmetros para não perder naturalidade

### Riscos / pegadinhas
- Clipes de 3s com ruído de fundo tendem a clonar o ruído junto — vale, no mínimo, um
  filtro simples de ruído (ex.: `noisereduce`, biblioteca leve em Python) antes do trim
- Textos de referência muito curtos (poucas palavras) dão pouca informação fonética pro
  clone — o ideal é 3s de fala **densa** (várias palavras diferentes), não 3s de uma
  palavra só repetida ou de silêncio com uma palavra no meio

---

## 5. TTS com detecção de emoção por análise de imagem

**Ideia:** em vez de (ou além de) a Gemma inferir a emoção pelo texto, detectar a emoção
a partir de uma foto/webcam e usar isso para escolher a curva de prosódia — o dicionário
`EMO` que já existe em `motor_v2.py` (21 emoções: `alegria`, `tristeza`, `raiva`, `medo`,
`surpresa`, `nojo`, `empolgacao`, `ternura`, `serenidade`, `confianca`, `ansiedade`,
`frustracao`, `sarcasmo`, `curiosidade`, `melancolia`, `arrogancia`, `timidez`,
`urgencia`, `neutra`, `suspenso`, `misterio`).

### Ferramentas e por quê
| Ferramenta | Uso | Por quê essa e não outra |
|---|---|---|
| **DeepFace** (MIT) | `DeepFace.analyze(img, actions=["emotion"])` → dicionário de probabilidades por emoção + `dominant_emotion` | Biblioteca mais madura/ativa nessa categoria; usa OpenCV para detecção de rosto e um classificador pré-treinado — não precisa treinar nada |
| **FER (Face Emotion Recognizer)** | Alternativa mais simples, também MIT | Mais indicada se a meta for tempo real via webcam (mais leve); DeepFace é mais completo para imagem única |

DeepFace só reconhece 7 emoções básicas (`angry`, `disgust`, `fear`, `happy`, `sad`,
`surprise`, `neutral`) — bem menos que as 21 do `EMO`. Isso exige uma tabela de mapeamento
(ver abaixo), não um match direto.

### Ponto de integração no código
- Novo módulo `app/estudio/emocao_imagem.py`: `detectar_emocao(imagem) -> str` (retorna
  uma chave de `EMO_LISTA`)
- Tabela de mapeamento DeepFace → `EMO` (primeira versão, ajustável depois de testar):

  | DeepFace | `EMO` |
  |---|---|
  | happy | alegria |
  | sad | tristeza |
  | angry | raiva |
  | fear | medo |
  | surprise | surpresa |
  | disgust | nojo |
  | neutral | neutra |

  (`suspenso`, `misterio`, `sarcasmo`, `arrogancia`, `timidez`, `urgencia` etc. não têm
  correspondência facial óbvia — ficam fora do escopo de detecção por imagem, só
  continuam acessíveis via seleção manual ou inferência por texto da Gemma)
- No fluxo de síntese (`_gerar_um()`, que já recebe `tom` como parâmetro), passar a
  emoção detectada em vez da inferida pela Gemma quando uma imagem for fornecida —
  simples troca do valor de `tom` antes da chamada

### Plano de passos
1. Adicionar campo de upload de imagem (ou captura de webcam via `<input capture>` no
   `static/index.html`, sem lib nova de frontend) na aba onde fizer sentido (Contador de
   Histórias, por trecho, ou uma aba nova "Emoção por Foto")
2. Rodar `DeepFace.analyze()` na imagem recebida
3. Mapear `dominant_emotion` para a chave de `EMO` correspondente pela tabela acima
4. Usar essa emoção como override no ponto onde hoje o `tom` é decidido, mantendo a opção
   de a Gemma decidir quando não houver imagem

### Riscos / pegadinhas
- DeepFace baixa pesos de modelo na primeira execução (de um bucket próprio, não
  Hugging Face) — vale rodar uma vez com internet disponível e cachear, para não
  depender de rede toda vez
- Roda bem em CPU para uma imagem única (não compete por VRAM com Gemma/OmniVoice), o
  que torna esta a feature mais simples de integrar sem mexer no ciclo de memória da GPU

---

## 6. Suporte a 100+ idiomas (com Gemma multilíngue)

**Ideia:** boa parte da base já existe — o trabalho é majoritariamente de **fiação**
(plumbing), não de pesquisa de ferramenta nova.

### O que já existe
- **OmniVoice** suporta **600+ idiomas** nativamente (modelo `k2-fsa/OmniVoice`,
  zero-shot multilíngue por design)
- **Gemma 3 4B**, já usada no projeto via Ollama, suporta **140+ idiomas** — já é apta a
  gerar roteiro/diálogo em qualquer um desses idiomas, bastando pedir no prompt
- `sintetizar_clone()`, `sintetizar_clone_lote()` e `sintetizar_design()` em
  `motor_v2.py` **já têm** o parâmetro `language` (default `"pt"`, e
  `sintetizar_clone_lote` já aceita `language=None` para preservar sotaque natural)

### O que falta (a lacuna real)
As funções **narrativas** — `gerar_radio()`, `gerar_batalha()`, `gerar_batalha_persona()`
e o equivalente do Contador de Histórias/Comédia — **não recebem `language`**: o idioma
hoje é fixo em português porque é fixo dentro do texto do prompt enviado à Gemma. É aqui,
não na síntese, que está o trabalho de verdade.

### Plano de passos
1. Adicionar parâmetro `idioma="pt-BR"` a cada função narrativa em `motor_v2.py`
   (`gerar_radio`, `gerar_batalha*`, e as equivalentes de Contador/Comédia/Game Show)
2. Interpolar esse idioma no prompt da Gemma: prefixar/adicionar instrução explícita
   ("Escreva a resposta inteiramente em {idioma}.") — testar se a Gemma obedece de forma
   consistente, já que modelos menores (4B) às vezes "vazam" de volta pro idioma
   dominante do treino em respostas longas
3. Propagar o mesmo `idioma` para a chamada de síntese (`language=` já existe nas funções
   de síntese, é só passar o valor recebido em vez do default fixo `"pt"`)
4. Adicionar o seletor de idioma no frontend (`static/index.html`) nas abas que hoje não
   têm — Clone/Design já devem ter, segundo `DOCUMENTACAO.md`; Contador, Comédia, Game
   Show e Battle precisam do controle novo
5. Validar manualmente um punhado de idiomas de famílias diferentes (ex.: inglês,
   espanhol, francês, japonês, árabe) — qualidade multilíngue de modelos zero-shot varia
   bastante entre idiomas de alto e baixo recurso; medir antes de anunciar "suporte total"

### Riscos / pegadinhas
- A voz de referência da Pandora foi gravada em PT-BR — clonar sotaque/prosódia dela
  falando outro idioma pode soar estranho (sotaque brasileiro em inglês, por exemplo);
  testar se o resultado é aceitável como está ou se vai precisar de referências de voz
  específicas por idioma
- Idiomas de baixo recurso dentro dos 140+/600+ suportados tendem a ter qualidade bem
  inferior aos "top" (inglês, espanhol, mandarim, etc.) — não tratar a lista como
  qualidade uniforme

---

## 7. Voz paramétrica — variar idade, gênero, rouquidão, fanhice etc. mantendo a identidade da Pandora

**Ideia (pedido do Filipe, jul/2026):** hoje existem dois mecanismos de variação de voz
que não se comunicam: (a) o modo **Design** (`interpretar_descricao_voz`/`perfil_de_design`
em `motor_v2.py`) usa o vocabulário categórico nativo do OmniVoice (`female/male`, 5 faixas
de idade, 5 faixas de pitch, sotaques) mas **gera uma voz nova do zero** — a identidade da
Pandora se perde; (b) o dicionário `EMO` já varia velocidade/pitch/volume/brilho/tremolo/eco
**sobre a voz clonada dela**, mas só para as 21 emoções pré-calibradas. O pedido é um
terceiro mecanismo: sliders contínuos (idade, gênero, rouquidão, fanhice, sentimento,
velocidade, gagueira...) aplicados **sobre a voz clonada real da Pandora**, sem perder o
timbre dela.

### Por que não dá pra usar pitch shift simples (o que já existe)

O `_pitch(x, P)` atual ([motor_v2.py:142](f:\Projeto IA\app\estudio\motor_v2.py#L142)) é
resample puro — muda pitch e formantes juntos (efeito "esquilo"/"monstro"). Um slider de
idade/gênero convincente precisa desacoplar **pitch** (F0, frequência fundamental) de
**formantes** (a "forma" do trato vocal, o que dá a sensação de corpo grande/pequeno,
adulto/criança) — são dois eixos fisicamente independentes na voz humana real.

### Ferramentas avaliadas

| Ferramenta | Resultado |
|---|---|
| **pyworld** (vocoder WORLD, decompõe F0/aperiodicidade/envelope espectral) | **Descartado nesta máquina**: não tem wheel pré-compilado para Python 3.14 (`.venv_omni`) e a compilação exige Microsoft C++ Build Tools, não instalado — instalar o Build Tools é uma mudança pesada de sistema só para esta feature |
| **STFT + liftering cepstral (numpy/scipy/librosa, já são dependências)** | **Escolhido** — dá pitch-shift e formant-shift desacoplados via separação envelope/estrutura fina no domínio cepstral, sem lib nova. Mesma família de técnica já usada em `_sussurro()` (STFT + envelope espectral) |

### Parâmetros mapeados

| Slider | Técnica |
|---|---|
| Idade / gênero | pitch-shift (resample) + formant-shift independente (warp do envelope cepstral) — desloca "tamanho do trato vocal" sem esquilo |
| Rouquidão | mistura de ruído filtrado modulado pela envolvente de amplitude (aspiração), + leve achatamento espectral |
| Fanhice | EQ: reforço ~800–1200 Hz (ressonância nasal) + atenuação ~2–3 kHz (formante oral) |
| Sentimento | já resolvido — reusa o dicionário `EMO` existente |
| Velocidade | já resolvido — parâmetro `speed`/`s` já existe em toda a síntese |
| Gagueira | **fora do escopo de DSP** — precisa repetir sílabas no nível do roteiro/texto antes de sintetizar, não é um efeito de áudio |

### Ponto de integração

Protótipo isolado em `app/laboratorios/voz_parametrica_lab.py` (não mexe no estúdio ainda,
mesmo padrão de `canto_lab.py`: script standalone que importa `motor_v2`, testa sobre
`app/estudio/vozes/Pandora.wav`). Se validado, os efeitos viram entradas novas no mesmo
pipeline de pós-processamento que hoje aplica o dicionário `EMO` (`_gerar_um`/`finalizar`),
e uma aba nova (ou extensão do Clone) expõe os sliders no `estudio_web.py`.

### Riscos / pegadinhas
- Formant-shift por liftering cepstral é uma aproximação (não é um trato vocal físico
  modelado) — soa bem para deslocamentos moderados, degrada em extremos (criança↔idoso
  extremo pode soar "processado")
- Rouquidão/fanhice fortes demais competem com a inteligibilidade — vale limitar a faixa
  do slider depois de ouvir os extremos

---

## 8. Máquina de Paródias — o passo "cantar a letra nova" (ACE-Step 1.5)

**Ideia:** fechar o pipeline da Máquina de Paródias. A Fase 1 (gerar a LETRA da paródia
com métrica+rima) já existe em `app/estudio/parodia.py`. O gargalo sempre foi o passo 4:
**cantar a letra NOVA na melodia da música original** — o seed-vc é *voice conversion*
(troca o timbre de um vocal já cantado), não inventa palavras novas.

### Alternativas pesquisadas e descartadas (jul/2026)

| Ferramenta | Por que não |
|---|---|
| **SoulX-Singer** (fev/2026, zero-shot SVS, <8GB) | Só mandarim/inglês/cantonês. O fonemizador (`g2p_en`+`g2pM`) não tem pt — não é só falta de dataset. Install frágil no Windows (`pyworld`/`webrtcvad` pedem MSVC Build Tools, `torch==2.2.0`) |
| **TCSinger 2** | Repo acadêmico, testado só en/zh, pt não confirmado |
| **OpenUtau + DiffSinger + BRAPA** | Tem vozes pt-BR reais (Umidaji/REO, Team-BRAPA) e **funciona** — mas é app **GUI**. Rejeitado: tudo no projeto precisa ser scriptável em Python |
| **DiffSingerMiniEngine** (openvpi) | Motor Python p/ DiffSinger, mas de 2023 — espera formato antigo (sem `languages`/`spk_embed`/`steps`/`word_div`). Incompatível com os `.onnx` da Umidaji |

Os 5 `.onnx` da Umidaji ficaram salvos em `app/laboratorios/diffsinger_mini/assets/umidaji/`
caso um dia valha reimplementar o pipeline ONNX em Python (exigiria escrever um G2P pt-BR e
encadear os 4 estágios à mão).

### ❌ ACE-Step 1.5 — TESTADO E DESCARTADO (31/07/2026)

**Não serve para paródia: não preserva a melodia.** Testado ponta a ponta com
"Como é Grande o Meu Amor por Você" (trecho de 25s), medido com librosa:

| | BPM | Correlação harmônica vs original | Similaridade quadro-a-quadro |
|---|---|---|---|
| Original (Roberto Carlos) | 89 | — | — |
| cover `audio_cover_strength=0.85` | 152 | **−0,41** | 0,45 |
| cover `audio_cover_strength=1.00` | 162 | **−0,31** | 0,48 |

O andamento quase dobrou e a correlação harmônica é **negativa** (acordes opostos aos do
original). Subir a força para 1.0 não resolveu — melhorou a harmonia marginalmente e piorou
o tempo. A música gerada não é reconhecível como a original.

**Causa raiz (arquitetural, não de ajuste):** o ACE-Step **não tem condicionamento por
melodia/F0** — não existe parâmetro para dar a melodia como entrada. Ele reconstrói a música
a partir de texto + códigos de áudio. A task `cover` é *style transfer* ("transform existing
audio... changing style/timbre"), ou seja, "reimaginar a música em outro estilo", não
"mesma música com letra nova". O sinal estava na própria descrição da task desde o início.

O que **funcionou** (registrado caso o ACE-Step sirva para outra coisa — ex.: gerar trilha/
música original do zero, onde não há melodia a preservar): a letra nova É cantada de fato
(Whisper transcreveu "comigo essa nova canção", igual ao pedido) e em português.

Instalação inteira REMOVIDA em 31/07/2026 (~20 GB: repo + checkpoints + venv + wheels).
Se for reinstalar algum dia, a receita da RTX 2060 está na memória `maquina-parodias`.

### (histórico) Por que o ACE-Step tinha sido escolhido

`github.com/ace-step/ACE-Step-1.5`, Apache-2.0. Instalado em `app/laboratorios/acestep/`
com venv próprio `app/laboratorios/.venv_acestep` (**Python 3.11** — o projeto exige 3.11/3.12;
o `.venv_omni` é 3.14 e não serve).

| Requisito | Como atende |
|---|---|
| Cantar letra nova sobre música existente | `task_type="cover"`: `src_audio` (original) + `lyrics` (letra nova) + `audio_cover_strength` (1.0 = cola na estrutura) |
| Português | `vocal_language="pt"` suportado de verdade (`'português': 'pt'` em `cli.py`) |
| RTX 2060 (6 GB) | `docs/en/GPU_COMPATIBILITY.md` tem tiers 4-6GB e 6-8GB com INT8 + CPU offload |
| Python, sem GUI | API Python (`acestep.inference.generate_music`) + REST API |
| Grátis | Apache-2.0 |

Detalhe de VRAM: no `cover` a LM é **pulada automaticamente**, então dá pra passar
`llm_handler=None` (`inference.py:634` checa `llm_handler is not None`) e poupar memória.

⚠️ A voz que sai do ACE-Step é **genérica, não é a Pandora** — por isso o pipeline final encadeia
o que já está validado: Demucs separa o vocal gerado → seed-vc troca o timbre pela voz da Pandora
→ mixa (`canto_musica.py`).

### Pipeline completo (todo em Python)
1. `parodia.py` (existe): Whisper transcreve + Gemma escreve a letra com métrica/rima
2. **ACE-Step cover** (novo): gera a música com a letra nova a partir da original
3. **Demucs + seed-vc** (existem): vocal gerado → voz da Pandora
4. Mixagem final (existe)

### Riscos / pegadinhas
- Instalar `-r requirements.txt` estoura com `SSLError DECRYPTION_FAILED_OR_BAD_RECORD_MAC`
  (torch tem 3,27 GB). Receita do projeto: baixar os wheels com
  `curl -L --retry 20 --retry-all-errors -C -` e instalar do disco
- Na 2060 vai ser lento (o benchmark de "<10s por música" é numa RTX 3090)
- `audio_cover_strength` alto demais pode engessar a troca de letra; baixo demais foge da música
  que dá a graça da paródia — calibrar de ouvido (partida: 0.85)

Laboratório: `app/laboratorios/parodia_acestep_lab.py`.

---

## Resumo de prioridade sugerida

Do mais simples/barato ao mais custoso em VRAM/engenharia:

1. **Idiomas** (item 6) — a síntese já suporta; falta só fiar o `language` até as funções
   narrativas e adicionar o seletor no frontend
2. **Emoção por imagem** (item 5) — não compete por VRAM (DeepFace roda em CPU), só
   precisa de uma tabela de mapeamento de 7 para as 21 emoções do `EMO`
3. **Voice cloning 3s** (item 4) — ajuste de robustez do pipeline existente (`perfil_voz`,
   `_criar_prompt_voz`), sem modelo novo
4. **Podcast generator** (item 2) — reaproveita quase tudo (`personagens/`, `gerar_radio`,
   padrão do Battle); o único componente 100% novo é o feed RSS (`python-feedgen`)
5. **Karaokê** (item 3) — precisa de um modelo novo (WhisperX) mas reaproveita a saída do
   pipeline de Canto (Demucs + seed-vc) já validado
6. **Dub automático de vídeo** (item 1) — o mais completo: envolve transcrição, tradução,
   ajuste de duração por segmento e remontagem de vídeo — várias etapas novas encadeadas
7. **Lip-sync** (partes opcionais de 1 e 3) — o mais pesado em VRAM e o único que exige um
   vídeo/rosto de referência da Pandora que o projeto hoje não tem
8. **Voz paramétrica** (item 7) — sem lib nova, mas o mais experimental em qualidade (não
   há receita pronta na comunidade tão validada quanto as anteriores; precisa de laboratório
   de escuta antes de virar feature)
