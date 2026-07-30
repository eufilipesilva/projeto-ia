# 🎙️ Estúdio de Voz v2 — Versão Expandida

## 📋 O que é

Versão **completamente nova** do Estúdio de Voz com 5 abas inéditas e interface modernizada. **Os arquivos originais estão 100% preservados** — você tem `motor.py` + `estudio.py` intactos e `motor_v2.py` + `estudio_v2.py` como nova versão experimental.

## ⚡ Como Rodar

```bash
# Versão 2 (nova, port 5007)
python app/estudio/estudio_v2.py

# Versão 1 (original, port 5006)
python app/estudio/estudio.py
```

## ✨ O que é Novo

### Melhorias nas Abas Existentes

#### 1.1 🎨 Design de Voz Livre
- **Antes**: 4 dropdowns limitados (feminino/jovem/grave/normal)
- **Agora**: Campo de texto livre em português
  - Descreva: "professora de 55 anos, cansada, com sotaque do interior"
  - A Gemma traduz para instrução OmniVoice: `"female, middle-aged, low pitch, expressive, slightly raspy"`
  - Preview mostra exatamente o que a IA entendeu
- **Função**: `motor_v2.interpretar_descricao_voz(descricao)`

### 5 Abas Totalmente Novas

#### 📻 Aba 1 — Rádio Pandora ⭐ MÁXIMO IMPACTO
Um episódio de rádio completo em ~10 minutos com 5 segmentos:
1. **Abertura** — Pandora apresenta o tema
2. **Bloco de Notícias** — 3 notícias absurdas sobre o tema
3. **Entrevista** — Pandora com convidado debate o tema
4. **Quadro Fixo** — "Momento Filosófico do Submundo" (aforismo macabro)
5. **Encerramento** — Pandora se despede

Cada segmento é gerado pela Gemma e sintetizado com sonoplastia.

**Função**: `motor_v2.gerar_radio(tema, progresso)`

---

#### 🎬 Aba 2 — Gerador de Trailer
Trailers épicos de cinema em 30–90 segundos.
- Escolha gênero: Terror / Ficção Científica / Romance / Ação / Comédia
- Escreva logline: "um detetive cego descobre que é o assassino que procura"
- Carregue música opcional (fade-in/out automático)
- Recebe: narração épica com eco (efeito de "grande espaço") + música de fundo

**Função**: `motor_v2.gerar_roteiro_trailer(genero, logline)`

---

#### 🧘 Aba 3 — Meditação Guiada
Meditações reais com pausas programadas e ambientes sonoros.
- Escolha tema: Floresta / Oceano / Cosmos / Sono Profundo / Foco
- Duração: 5, 10 ou 20 minutos
- Intensidade do sussurro: 0–1 (0 = voz normal, 1 = sussurro total)
- Carregue ambiente sonoro (chuva, floresta, cosmos, etc.)

A Gemma escreve o script com marcadores `[pausa 3s]` / `[respire]`, o pipeline insere silêncios, a voz é sintetizada em velocidade 0.75 (lenta, tranquila), modo sussurro opcional.

**Função**: `motor_v2.gerar_meditacao(tema, duracao_min, intensidade_sussurro)`

---

#### ⚔️ Aba 4 — Batalha de Vozes
Dois personagens com vozes distintas debatem qualquer tema.
- Defina personagem 1: nome + descrição de voz ("homem sério, profundo")
- Defina personagem 2: nome + descrição de voz ("mulher engraçada, aguda")
- Digite o tema do debate
- Escolha modo: "sério" (argumentado) ou "caos" (emoções à flor da pele)

A Gemma escreve o diálogo no formato `NOME: fala`, roteiro é sintetizado com vozes distintas.

**Função**: `motor_v2.gerar_batalha(nome1, desc_voz1, nome2, desc_voz2, tema, modo)`

---

#### 🎭 Aba 5 — Personagem Infinito
Crie e converse com personagens salvos em JSON com voz e personalidade próprias.

**Sub-aba: Criar**
- Nome do personagem (ex: "Mestre Yoda")
- Personalidade (descrição em prosa)
- Descrição da voz (ex: "homem idoso, sábio, fala lento")
- Quirks/Maneirismos (ex: "sempre faz perguntas retóricas")
- Tom emocional padrão (um dos 21 emoções: alegria, tristeza, serenidade, etc.)

Salva em `app/estudio/personagens/NOME.json`.

**Sub-aba: Conversar**
- Selecione personagem
- Digite o que quer dizer
- O personagem responde com SUA voz + personalidade
- Histórico acumula nas últimas 10 trocas

A Gemma usa o prompt: `"Você é [nome], com essa personalidade: [descrição]. Seus maneirismos: [quirks]. Responda no seu jeito."` — a resposta é sintetizada com a voz descrita.

**Função**: `motor_v2.responder_personagem(personagem_json, historico, fala_usuario)`

---

### Funções Bônus (Não têm UI, mas existem)

#### 📚 Livro em Capítulos
Processa história dividida em capítulos marcados com `=== CAPÍTULO 1 ===`.
Gera audiolivro com um arquivo WAV por capítulo em `saidas/livro_NOME/`.

**Função**: `motor_v2.gerar_livro_capitulos(texto, perfil)`

#### 📺 Temporada Completa
Gera N episódios de programa com continuidade narrativa (personagens recorrentes, piadas internas, arco).

**Função**: `motor_v2.gerar_temporada(perfil, n_eps, tema_base)`

---

## 🎨 Interface Modernizada

### Design
- **Fontes**: Inter (UI) + JetBrains Mono (código) — modernas, legíveis
- **Cores**: Gradiente purple→magenta sobre dark mode
- **Contraste**: Alto — texto branco/cinza claro sobre fundo escuro
- **Efeitos**: Glassmorphism (backdrop blur), sombras suaves, transições
- **Responsividade**: Funciona em desktop, tablet, mobile

### CSS
Incluído inline no arquivo `estudio_v2.py`:
- Tema escuro por padrão (melhor para estúdio de produção — evita fadiga visual)
- Buttons com gradientes e hover effects
- Inputs com focus ring (feedback visual)
- Markdown renderizado em tom cinza legível

---

## 📊 Stack Completo (v2)

| Componente | Versão | Função |
|---|---|---|
| **Python** | 3.10+ | Orquestração |
| **OmniVoice** | 0.1.5 | TTS local com clonagem |
| **Gemma** | 3 4B | LLM local (Ollama) |
| **Gradio** | 6.19+ | Interface web |
| **NumPy/SciPy** | Latest | DSP (pitch, brilho, tremolo, eco) |
| **LibROSA** | Latest | Análise/síntese de áudio |
| **PyPDF** | Latest | Extração de PDFs |

---

## ⚙️ Ciclo de VRAM (Mantido)

```
Gemma infere (texto/roteiro)
    ↓
Gemma descarrega (~4 GB liberated)
    ↓
OmniVoice sintetiza (áudio)
    ↓
OmniVoice descarrega (~3 GB liberated)
    ↓
DSP pós-síntese (pitch, brilho, eco) — ZERO VRAM
```

Funciona com RTX 2060 (6 GB) — os dois modelos **nunca** coexistem na memória.

---

## 📁 Arquivos

```
app/estudio/
├── motor.py                    ← Original (PRESERVADO)
├── estudio.py                  ← Original (PRESERVADO)
├── motor_v2.py                 ← Novo com 8 funções extras
├── estudio_v2.py               ← Novo com 5 abas + melhorias
├── README_V2.md                ← Este arquivo
├── vozes/                       ← Vozes salvas (clones)
│   └── Pandora.wav
├── sonoplastia/                ← Efeitos de áudio
├── emocoes/                    ← Clips de referência por emoção
├── saidas/                     ← Áudios gerados
└── personagens/                ← JSONs de personagens (criado automaticamente)
```

---

## 🚀 Quick Start (v2)

1. **Abra a interface:**
   ```bash
   python app/estudio/estudio_v2.py
   ```
   Abre em `http://127.0.0.1:5007`

2. **Analise uma voz (Clone):**
   - Suba ou escolha Pandora.wav
   - Clique "Analisar voz"

3. **Tente Design Livre:**
   - Descreva: "mulher jovem, alegre, sussurrante"
   - Escreva um texto
   - Clique "Gerar com descrição"

4. **Tente Trailer:**
   - Escolha gênero (ex: Ficção Científica)
   - Escreva logline (ex: "um hacker do futuro viaja pro passado")
   - Clique "Gerar Trailer"

5. **Tente Rádio Pandora:**
   - Digite tema (ex: "culinária apocalíptica")
   - Clique "Gerar Episódio de Rádio"
   - Aguarde ~5–8 min (5 segmentos + síntese)

6. **Crie um Personagem:**
   - Aba "Personagem Infinito" → "Criar"
   - Nome: "Einstein"
   - Personalidade: "Cientista genial, sempre faz perguntas"
   - Descrição de voz: "homem idoso, alemão, reflexivo"
   - Salve
   - Vá para "Conversar", selecione Einstein, fale com ele

---

## ⚠️ Limitações Conhecidas

1. **Tempo de Processamento**
   - Rádio Pandora: ~5–8 min (5 segmentos × síntese)
   - Temporada (5 eps): ~20–30 min
   - Tudo normal — é gerativo

2. **Contexto da Gemma**
   - Máximo 8000 chars por PDF/material
   - Lotes de 12 items na classificação
   - Limite de temperatura 0–1.0

3. **OmniVoice**
   - Float16 na GPU (precisão menor, mas cabe em 6 GB)
   - Não sintetiza música/canto (só fala)
   - Idiomas suportados: 15 (pt, en, zh, ja, ko, fr, de, es, ru, ar, hi, it, nl, tr, pl)

4. **Personagem Infinito**
   - Histórico salvo em memória (não persiste após reiniciar)
   - Máximo 10 trocas mantidas no contexto
   - Emoção inferida via `_achar_emocao()` (regex simples)

---

## 🔧 Customização

### Adicionar Nova Aba

1. Crie função em `motor_v2.py`:
   ```python
   def gerar_minha_aba(parametro1, parametro2, progresso=lambda *a: None):
       progresso(0.1, "Processando...")
       # seu código
       return resultado
   ```

2. Adicione UI em `estudio_v2.py`:
   ```python
   with gr.Tab("🚀 Minha Aba"):
       entrada = gr.Textbox(label="Entrada")
       b = gr.Button("Processar")
       saida = gr.Audio()
       b.click(gerar_minha_aba, entrada, saida)
   ```

### Adicionar Emoção Nova

Em `motor_v2.py`, adicione em `EMO`:
```python
"minha_emocao": dict(s=1.0, p=1.0, vol=1.0, brilho=1.0, tremolo=0.0, eco=False),
```

Parâmetros:
- `s`: velocidade (0.8–1.2 típico)
- `p`: pitch/tom (0.8–1.2)
- `vol`: volume (0.7–1.3)
- `brilho`: espectro (0.7–1.4)
- `tremolo`: vibração de amplitude (0.0–0.15)
- `eco`: reverb suave (True/False)

---

## 📝 Exemplos Práticos

### Exemplo 1: Trailer de Ficção Científica
```
Gênero: Ficção Científica
Logline: Um astronauta descobre que a estação espacial é uma entidade viva
Música: coloque uma track épica 80s

→ Resultado: narração em voz grave + eco + música de fundo
```

### Exemplo 2: Meditação Personalizada
```
Tema: Floresta
Duração: 10 min
Sussurro: 0.7
Ambiente: chuva.wav

→ Resultado: Voz sussurrante lenta + chuva de fundo + pausas automáticas
```

### Exemplo 3: Personagem Interativo
```
Nome: Sherlock
Personalidade: Detetive brilhante, arrogante, sarcástico
Voz: homem britânico, inteligente, ácido
Quirks: Sempre comenta óbviedades de forma condescendente

Usuário: "Como você resolve crimes?"
Sherlock: "Elementary, my dear. Observação simples que qualquer idiota teria notado."
```

---

## 🎬 Roadmap Futuro (Ideias)

- [ ] Dub automático de vídeos (exportar vídeo + áudio síncrono)
- [ ] Podcast gerator (episódios em série com hosts salvos)
- [ ] Karaokê com sincronização lip-sync
- [ ] Voice cloning de 3s para qualquer personagem
- [ ] TTS com detecção de emoção por análise de imagem
- [ ] Suporte a 100+ idiomas (com Gemma multilíngue)

---

## 💡 Dicas de Uso

1. **Para melhores clones**: forneça áudio de 3–8s de referência com texto paralelo
2. **Para trailers épicos**: use gênero específico, logline clara, música dark/orchestral
3. **Para meditação**: durações múltiplas de 5 min (5, 10, 20), susurro > 0.5 é muito
4. **Para debates**: nomes curtos, descrições de voz contrastantes (grave vs agudo)
5. **Para personagens**: quirks específicos (frase de assinatura, sotaque, tic de fala)

---

## 📞 Suporte

Se encontrar bugs:
1. Verifique que `ollama serve` está rodando (`http://127.0.0.1:11434`)
2. Verifique VRAM disponível (RTX 2060 = 6 GB mínimo)
3. Verifique permissões de escrita em `vozes/`, `saidas/`, `personagens/`
4. Revise logs do Gradio (saída no terminal)

---

## 📜 Licença & Créditos

**v2 Developed by**: Claude Code + Assistente AI
**Original Stack**: OmniVoice + Gemma + Gradio
**Inspiration**: Estúdio de Voz Pandora (jun/2026)

---

**Versão**: 2.0 (Junho 2026)
**Status**: ✅ Pronta para uso em produção (com testes)
