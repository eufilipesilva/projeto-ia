# Referência de Funções — Estúdio de Voz

> Todas as funções dos módulos do estúdio: o que fazem, assinatura essencial e quem as usa.
> Companheiro do `MANUAL_MANUTENCAO.md` (arquitetura) — este aqui é o "dicionário".
> Atualizado em jul/2026 (inclui Game Show 2.0 duelo e histórias multi-voz).

---

## 1. `motor_v2.py` — o motor central (OmniVoice + Gemma)

### 1.1 Infra de modelos
| Função | O que faz |
|---|---|
| `carregar_omni()` | Carrega o OmniVoice na GPU (singleton `_MODEL`); espera VRAM livre antes |
| `descarregar_omni()` | Descarrega o OmniVoice e limpa a VRAM (chamar antes de usar Gemma/Demucs) |
| `_esperar_vram_livre(min_gb, timeout)` | Bloqueia até a GPU ter espaço (evita OOM no ciclo gemma↔omni) |
| `_gemma(prompt, num_predict, num_ctx, temperature)` | Chamada crua ao Ollama/gemma3:4b; retorna o texto. **Toda** geração de roteiro passa por aqui |
| `descarregar_gemma()` | keep_alive=0 + `ollama stop` — libera a VRAM da Gemma |
| `_cfg(num_step, guidance_scale)` | GenerationConfig do OmniVoice (32 passos padrão) |

### 1.2 Perfis de voz (a "identidade" de uma voz)
| Função | O que faz |
|---|---|
| `perfil_voz(ref_path, ref_text, base_speed)` | Constrói perfil de CLONE a partir de um wav: transcreve (se preciso), mede ritmo. Retorna dict {ref_path, ref_text, base_speed, dur} |
| `perfil_de_design(instruct, seed_text)` | Gera uma voz-semente a partir de instrução de design e a transforma em perfil clonável (timbre travado — usado no Battle) |
| `_criar_prompt_voz(m, perfil)` | Perfil → prompt de clonagem do OmniVoice (áudio+texto de referência) |
| `_carregar_prompts_emocao(m, perfil)` | Prompts alternativos por emoção pro narrador |
| `estimar_ritmo(wav, sr)` | Estima a velocidade natural de fala do clipe (sílabas/s → base_speed) |
| `interpretar_descricao_voz(descricao, progresso)` | Descrição em PT ("mulher rouca...") → instrução válida do OmniVoice via Gemma + validação (`_OMNI_VALID_SET`, `_dedup_instruct`) |

### 1.3 Síntese (texto → áudio)
| Função | O que faz / quem usa |
|---|---|
| `sintetizar_clone(perfil, texto, language, steps, guidance, velocidade, progresso)` | Síntese básica com voz clonada. Abas: Clone, Trailer, Rádio |
| `sintetizar_design(instruct, texto, ...)` | Síntese com voz descrita (sem referência). Abas: Design, Personagem, Trailer (fallback) |
| `sintetizar_clone_lote(perfil, textos, language, instruct, num_step, guidance_scale, speed_mult, progresso)` | Vários textos com UMA carga do modelo. Usado pela Meditação (segmentos) |
| `sintetizar_clone_pandora(perfil, texto, speed=0.80, num_step=64)` | Clone com caimento natural no fim das falas (curva da Pandora — NUNCA time-stretch). Usado no Battle |
| `sintetizar_historia(perfil, texto, ritmo, sussurro, musica_path, vol_fundo, cauda_fundo, progresso, vozes_map=None)` | História completa: detecta beats/falantes/emoções (Gemma) e dá voz a cada personagem. **`vozes_map` {NOME: perfil} = personagem fala com voz SALVA (multi-voz)**; sem mapa, usa PALETA (variações da voz base) |
| `sintetizar_comedia(perfil, texto, ritmo, vol_sfx, vol_plateia, intensidade, abertura_path, vol_abertura, progresso, vozes_map=None)` | Auditório com sonoplastia automática (SFX + plateia). Abas: Comédia, Game Show (duelo usa `vozes_map` pros competidores), Rádio (entrevista) |
| `_gerar_um(m, cfg, prompt, txt, speed, tom, vol, language)` | A geração unitária de um segmento (todas as sínteses passam aqui) |

### 1.4 Geração de roteiros (Gemma)
| Função | O que faz |
|---|---|
| `gerar_roteiro_comedia()` | Roteiro aleatório de auditório (convidados malucos de `_LOUCURA_CONVIDADOS`) |
| `ler_pdf_completo(path)` 🆕 | PDF → texto INTEIRO, sem truncar. Retorna (texto, n_páginas) |
| `destilar_conteudo(texto, progresso, bloco_chars=7000)` 🆕 | **Map-reduce**: divide material longo em blocos, extrai FATOS de cada um via Gemma e junta — o quiz cobre o material inteiro (antes truncava em 8k chars) |
| `gerar_gameshow_duelo(conteudo, faixa, n_perguntas, nome1, nome2, progresso)` 🆕 | Roteiro do DUELO: Pandora apresenta, 2 competidores respondem alternado, placar anunciado por rodada, vencedor no fim |
| `gerar_gameshow_educativo(...)` | Formato antigo (convidados avulsos, sem placar) — mantido para compatibilidade |
| `_ler_pdf(path)` | Leitor antigo (trunca em `MAX_PDF_CHARS=8000`). Ainda usado pelos dossiês do Battle |
| `gerar_roteiro_trailer(genero, logline)` | Narração épica de trailer |
| `gerar_meditacao(tema, duracao_min, intensidade_sussurro, idioma)` | Script de meditação com marcadores `[pausa Xs]` |
| `gerar_radio(tema)` | Episódio de rádio → dict {abertura, noticias, entrevista, quadro, encerramento} |
| `gerar_batalha(nome1, desc1, nome2, desc2, tema, modo)` | Debate simples (um prompt só) |
| `gerar_batalha_persona(nome1, persona1, nome2, persona2, tema, modo, n_turnos)` | Debate turno-a-turno com dossiê por personagem (cada lado é um agente) |
| `responder_personagem(personagem_json, historico, fala_usuario)` | Resposta do Personagem Infinito (com memória de 10 trocas) |
| `gerar_livro_capitulos(texto, perfil)` / `gerar_temporada(perfil, n_eps, tema_base)` | Extras não expostos na UI (audiolivro por capítulos / temporada de episódios) — prontos pra virar abas |
| `_limpar_roteiro(txt)` | Remove lixo de formatação que a Gemma gruda nos roteiros |

### 1.5 Classificadores (história/comédia)
| Função | O que faz |
|---|---|
| `_beats_historia(texto)` / `_beats_comedia(texto)` | Quebram o texto em "beats" (narração/fala) e detectam o falante pelos rótulos `NOME:` e travessões |
| `_classificar_beats(beats)` | Gemma decide quem fala + emoção de cada beat (lotes de 12) |
| `_emocao_lote(beats)` | Só a emoção (comédia) |
| `_classificar_sfx(beats, disponiveis, intensidade)` | Escolhe o efeito sonoro de cada beat (aplauso, risada...) |
| `_quem_fala_gemma` / `_falante_da_tag` / `_primeiro_nome` | Heurísticas + Gemma pra atribuir falas a personagens |
| `_norm_nome(quem)` | Normaliza nome de falante (minúsculo, sem acento, 1ª palavra). **Chaves do `vozes_map` passam por aqui** |
| `_achar_emocao(txt)` / `_split_frases(t)` | Emoção por palavra-chave / divisão em frases |

### 1.6 DSP / pós-processamento de áudio
| Função | O que faz |
|---|---|
| `finalizar(x)` | Normalização/limpeza final de um segmento |
| `_montar(segs, quem)` | Concatena segmentos com gaps naturais |
| `_montar_comedia(segs, quem_seg, sfx_seq, catalogo, ...)` | Montagem com SFX + plateia intercalados |
| `_carregar_fundo(path, volume)` / `_misturar_fundo(voz, fundo, cauda)` | Música de fundo com cauda |
| `_catalogo_sfx()` / `_carregar_sfx(path, ganho, max_seg)` | Catálogo de efeitos da pasta de SFX |
| `_sussurro(x)` | Converte voz em sussurro (ASMR) |
| `_brilho(x, fator)` / `_tremolo(x)` / `_eco(x)` | Efeitos de cor da voz (usados pelas emoções) |
| `_caimento_pandora(w, ms)` | Decaimento natural no fim da fala (curva medida da Pandora) |
| `_binaural_widen(y, sr)` | Pseudo-estéreo binaural (Haas) — export da Meditação |
| `_fade_in_cos` / `_fade_exp` / `_rms` / `_envelope` / `_zcr` / `_pitch` / `_roomtone` | Utilitários DSP básicos |
| `salvar(audio, nome)` | Grava wav em disco (uso manual/testes) |

---

## 2. `estudio_web.py` — servidor FastAPI (porta 5008)

### Helpers (detalhes no MANUAL_MANUTENCAO.md §2)
`_save_audio` · `_perfil_de_voz` · `_avaliar_meditacao` · `_parse_bool` · `_audio_response` · `_prog_fn` · `_executar_tarefa` · `_worker_loop` · `_podar_tasks` · `_varrer_tmp_antigos` · `_run_task` · `_new_task` · `_salvar_upload` · `_resolver_voz_ref` · `_ler_texto_upload`

### Rotas (o mapa rota → função do motor está no MANUAL, §2)
Novidades jul/2026:
- `/api/gameshow/pdf` agora é **task** (PDF inteiro via `ler_pdf_completo` + `destilar_conteudo` + `gerar_gameshow_duelo`); params novos `nome1`/`nome2`
- `/api/gameshow` agora tem corpo próprio com `nome1/voz1/nome2/voz2` → `vozes_map`
- `/api/story` aceita `personagens_vozes` (JSON {"Nome": "Voz.wav"}) → `vozes_map`

---

## 3. `canto_musica.py` — Cantar Música (single)
| Função | O que faz |
|---|---|
| `gerar_canto(caminho_musica, voz_ref, diffusion_steps, vol_instrumental, cfg_rate, auto_f0, semi_tone_shift, ajuste_fino, progresso)` | Pipeline completo: descarrega OmniVoice → separa → shift auto (limitado!) → teto de belting → converte → mixa → limpa temporários |
| `separar_vocal_instrumental(caminho, progresso)` | Demucs (htdemucs, cache na GPU). Retorna (vocal_path, inst_path, vocal_em_memória, sr) |
| `calcular_semi_tone_shift(vocal_y, sr, voz_ref)` | Diferença de registro cantor↔voz-alvo (pyin rápido: frame 2048/hop 1024) |
| `_limitar_shift(shift)` | **Prende o shift automático em [0, +8]** — nunca abaixa (abaixar engrossa a voz; o teto cuida dos agudos) |
| `calcular_teto_pitch(voz_ref)` | Teto de belting = mediana da voz-alvo + 12 semitons (**se molda à voz escolhida**) |
| `converter_voz(vocal, voz_ref, ..., teto_midi, suavizar_janela)` | Subprocess do seed-vc com os args de tratamento |
| `mixar(voz_convertida, instrumental, vol)` | Mix final na taxa da voz |
| `_pitch_mediano_midi(y, sr)` / `_limpar(*paths)` | Mediana de pitch / remoção de temporários |
| Constantes | `_TETO_OFFSET_SEMITONS=12` · `_SUAVIZAR_JANELA=9` · `_SHIFT_MIN_AUTO=0` · `_SHIFT_MAX_AUTO=8` |

## 4. `canto_lote.py` + `seed-vc/converter_lote.py` — Cantar em lote
| Função | O que faz |
|---|---|
| `gerar_canto_lote(musicas, voz_ref, pasta_saida, ...)` | Separa TODAS → 1 subprocess seed-vc (modelos carregam 1x, economiza ~60s/música) → mixa todas. Faixa que falha não derruba o lote. Caminhos absolutizados! |
| `converter_lote.py main()` | Lado seed-vc: lê JSON de trabalhos, `load_models` 1x, converte todos, imprime `PROGRESSO i/n` |

## 5. `seed-vc/inference.py` — funções que ADICIONAMOS ao pacote
| Função | O que faz |
|---|---|
| `load_models(args)` / `convert_one(models, source, target, ...)` | Separação carga/conversão (extraído do main pra permitir lote) |
| `corrigir_saltos_oitava(f0, janela=41, passadas=6)` | Filtro de mediana iterativo no F0 do RMVPE (131→~34 saltos na Chora Peito). Sempre ativo |
| `aplicar_teto_pitch(f0, teto_midi, ratio)` | Comprime notas acima do teto (belting) — ativado via `--teto-midi` |
| `suavizar_f0(f0, janela)` | Mediana global no F0 — ativado via `--suavizar-janela` (9 = receita) |
| `preencher_buracos_f0(f0, max_gap)` | Interpola gaps curtos de pitch (desligado por padrão) |
| `suavizar_f0_adaptativo(f0, janela, limiar, alt_min_midi)` | Suaviza só trechos instáveis/agudos (desligado — a receita simples venceu) |
| CLI novos | `--teto-midi` e `--suavizar-janela` |

## 6. `parodia.py` — Máquina de Paródias (fase 1, em evolução)
| Função | O que faz |
|---|---|
| `transcrever_letra(vocal_path, idioma, progresso)` | faster-whisper (CPU int8) com word_timestamps → versos curtos por pausa. ⚠️ Próximo passo: estruturação poética via Gemma ANTES da análise |
| `contar_silabas(linha)` | Sílabas gramaticais via pyphen pt-BR |
| `_chave_rima(palavra)` / `rimam(a, b)` | Terminação rímica (da vogal tônica ao fim) — 10/10 nos testes |
| `gerar_parodia(versos, tema, tentativas, progresso)` | Gemma escreve com métrica+rima; verificador reconta e pede correção só dos versos fora. Relatório `[SR]` por verso |

---

## 7. Blocos reutilizáveis pra features novas (o "kit de peças")
- **Nova voz falando qualquer coisa** → `perfil_voz`/`_perfil_de_voz` + `sintetizar_clone`
- **Multi-voz num roteiro rotulado** (`NOME: fala`) → `sintetizar_comedia(..., vozes_map={...})`
- **Roteiro gerado por LLM** → prompt + `motor._gemma` (sempre `descarregar_omni()` antes e `descarregar_gemma()` depois)
- **Material longo pro LLM** → `ler_pdf_completo` + `destilar_conteudo`
- **Voz cantando** → `canto_musica.gerar_canto` (ou lote)
- **Trabalho demorado com barra de progresso na web** → `_run_task` + `pollTask` no front
- **Upload em rota** → `await _salvar_upload(up, ".ext")` + limpar no `finally`
- **Player bonito no front** → `montarWavePlayer(container, url, nomeDownload)`
- **Corte de áudio no front** → `criarTrimWidget(prefixo)` + HTML do widget
