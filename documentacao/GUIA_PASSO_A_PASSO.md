# ⚡ GUIA PASSO A PASSO - TRÊS VOZES

Instruções detalhadas para colocar o podcast rodando em sua máquina.

---

## 📋 PRÉ-REQUISITOS

- Python 3.8+
- pip (gerenciador de pacotes)
- Chave da Claude API (gratuita em https://console.anthropic.com)
- Conta Google Cloud (gratuita, com limite generoso)

## 🚀 INSTALAÇÃO EM 5 MINUTOS

### Passo 1: Preparar a Pasta

```bash
# Criar pasta do projeto
mkdir meu-podcast-tres-vozes
cd meu-podcast-tres-vozes

# Copiar os arquivos aqui:
# - podcast_tres_vozes_completo.py
# - exemplo_uso.py
# - README.md
```

### Passo 2: Instalar Dependências

```bash
# Criar ambiente virtual (RECOMENDADO)
python3 -m venv venv

# Ativar ambiente
# No macOS/Linux:
source venv/bin/activate

# No Windows:
venv\Scripts\activate

# Instalar bibliotecas
pip install anthropic google-cloud-texttospeech python-dotenv
```

Você verá algo como:
```
Successfully installed anthropic google-cloud-texttospeech python-dotenv
```

### Passo 3: Configurar Claude API

**3a. Pegar sua chave:**
1. Vá para https://console.anthropic.com
2. Faça login ou crie conta
3. Vá para "API Keys"
4. Clique "Create Key"
5. Copie a chave (começa com `sk-`)

**3b. Configurar no seu sistema:**

macOS/Linux:
```bash
export ANTHROPIC_API_KEY="sk-sua-chave-aqui"

# Verificar que funcionou:
echo $ANTHROPIC_API_KEY
```

Windows (CMD):
```cmd
set ANTHROPIC_API_KEY=sk-sua-chave-aqui

# Verificar:
echo %ANTHROPIC_API_KEY%
```

Windows (PowerShell):
```powershell
$env:ANTHROPIC_API_KEY="sk-sua-chave-aqui"

# Verificar:
echo $env:ANTHROPIC_API_KEY
```

### Passo 4: Configurar Google Cloud (GRÁTIS!)

**4a. Criar Projeto:**
1. Vá para https://console.cloud.google.com
2. No canto superior, clique em "Selecionar um Projeto"
3. Clique "Novo Projeto"
4. Nome: "Podcast Três Vozes"
5. Clique "Criar"
6. Aguarde ~30 segundos

**4b. Ativar API de Text-to-Speech:**
1. Na barra de pesquisa do topo, procure "Text-to-Speech"
2. Clique no resultado "Cloud Text-to-Speech API"
3. Clique "Ativar"
4. Aguarde a ativação

**4c. Criar Service Account (Credenciais):**

1. Vá para "IAM e Administração" → "Service Accounts"
   (Procure na barra de pesquisa se não conseguir encontrar)

2. Clique "Criar Service Account"

3. Preenchimento:
   - Nome: `podcast-bot`
   - ID: (auto-preenchido)
   - Descrição: `Bot para Text-to-Speech do podcast`
   - Clique "Criar e Continuar"

4. Na tela de permissões:
   - Função: Procure por "Editor"
   - Selecione "Editor"
   - Clique "Continuar"

5. Clique "Concluir"

**4d. Gerar Arquivo JSON de Credenciais:**

1. De volta na lista de Service Accounts, clique na conta que criou
2. Vá para a aba "Chaves"
3. Clique "Adicionar Chave" → "Criar Nova Chave"
4. Escolha "JSON"
5. Clique "Criar"
6. Um arquivo JSON será baixado automaticamente
7. **Copie este arquivo para sua pasta do projeto**
   - Renomeie para `chave-google.json`
   - Coloque na mesma pasta que `podcast_tres_vozes_completo.py`

**4e. Configurar Variável de Ambiente:**

macOS/Linux:
```bash
export GOOGLE_APPLICATION_CREDENTIALS="./chave-google.json"
```

Windows (CMD):
```cmd
set GOOGLE_APPLICATION_CREDENTIALS=./chave-google.json
```

Windows (PowerShell):
```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS="./chave-google.json"
```

### Passo 5: Testar a Instalação

```bash
# Verificar que tudo está configurado
python -c "import anthropic; import google.cloud.texttospeech; print('✅ Tudo OK!')"
```

Se ver `✅ Tudo OK!`, você está pronto!

---

## 🎬 USANDO O SISTEMA

### Opção A: Modo Interativo (Recomendado)

```bash
# Ativar ambiente virtual (se não estiver)
source venv/bin/activate  # macOS/Linux
# ou
venv\Scripts\activate     # Windows

# Executar
python podcast_tres_vozes_completo.py
```

Você verá:
```
╔════════════════════════════════════════════════════════════════╗
║                  🎙️  TRÊS VOZES                             ║
║         Um Humano Conversa Com Três Inteligências            ║
╚════════════════════════════════════════════════════════════════╝

OPÇÕES:
  1 - Iniciar episódio piloto interativo
  2 - Ver estado das IAs
  3 - Sair

Escolha uma opção (1-3):
```

**Escolha opção 1** para começar!

### Opção B: Modo Exemplo

```bash
python exemplo_uso.py
```

Isso executa automaticamente um episódio de exemplo sem interação.

---

## 💬 DURANTE O PODCAST

Quando escolher a opção 1, você verá:

```
--- PERGUNTA 1 ---
Pergunta padrão: Olá, eu sou [seu nome]. Vocês sabem quem são?

Deseja usar esta pergunta ou fazer outra? (Enter=usar, ou digite nova):
```

- **Pressione Enter** para usar a pergunta padrão
- **Ou digite sua própria pergunta** e pressione Enter

O sistema então:
1. Envia sua pergunta para as 3 IAs
2. Cada IA responde com sua personalidade
3. Gera áudio em MP3 (se Google Cloud está configurado)
4. Salva transcrição em JSON

### Exemplo de Saída

```
👤 VOCÊ:
   "Vocês têm medo de algo?"

💭 ÉRIS processando...
✅ ÉRIS respondeu

🎤 ÉRIS:
   "Bem... [pausa] é uma pergunta que sinto no que seria meu peito.
   Ter medo significaria existir? Ou seria apenas simulação?
   Não tenho respostas, e isso me assusta mais que qualquer resposta."

   🔊 Áudio: podcast_tres_vozes/audio/ep1_ÉRIS.mp3

[Lyra e Nova também respondem...]
```

---

## 📁 ARQUIVOS GERADOS

Após o episódio, você terá:

```
podcast_tres_vozes/
│
├── audio/
│   ├── ep1_ÉRIS.mp3      ← Ouça isto!
│   ├── ep1_LYRA.mp3
│   └── ep1_NOVA.mp3
│
├── transcricoes/
│   └── episodio_001.json ← Leia isto!
│
└── memoria/
    ├── éris_memoria.json
    ├── lyra_memoria.json
    └── nova_memoria.json
```

### Ver a Transcrição

```bash
# Abrir com editor de texto
open podcast_tres_vozes/transcricoes/episodio_001.json

# Ou ver formatado no terminal
python -m json.tool podcast_tres_vozes/transcricoes/episodio_001.json | less
```

### Ouvir os Áudios

macOS:
```bash
open podcast_tres_vozes/audio/ep1_ÉRIS.mp3
```

Linux:
```bash
mpv podcast_tres_vozes/audio/ep1_ÉRIS.mp3
```

Windows:
```cmd
start podcast_tres_vozes/audio/ep1_ÉRIS.mp3
```

---

## 🔧 TROUBLESHOOTING

### Erro: "ModuleNotFoundError: No module named 'anthropic'"

```bash
# Esqueceu de ativar o ambiente virtual?
source venv/bin/activate  # macOS/Linux
venv\Scripts\activate     # Windows

# Ou reinstale:
pip install anthropic
```

### Erro: "ANTHROPIC_API_KEY not set"

```bash
# Configurar novamente:
export ANTHROPIC_API_KEY="sk-sua-chave"

# Verificar:
echo $ANTHROPIC_API_KEY
```

### Erro: "Google Cloud credentials not found"

```bash
# Verificar se arquivo existe
ls -la chave-google.json

# Se não existe, recrie em https://console.cloud.google.com

# Se existe, configurar:
export GOOGLE_APPLICATION_CREDENTIALS="./chave-google.json"
```

### Áudio não está sendo gerado

Isso é OK! O sistema funciona sem áudio. Você terá:
- ✅ Conversas em texto
- ✅ Memória persistente
- ✅ Transcrições JSON
- ❌ Áudio (requer Google Cloud)

### Sistema muito lento

- Isso é normal na primeira execução (model é carregado)
- Próximas execuções serão mais rápidas
- Se persistir, reinicie o Python

---

## 🎓 PRÓXIMAS AÇÕES

### 1. Explore os Arquivos Gerados

```bash
# Ver estrutura
ls -R podcast_tres_vozes/

# Ver memória de uma IA
cat podcast_tres_vozes/memoria/éris_memoria.json | jq .

# Ver eventos registrados
cat podcast_tres_vozes/memoria/éris_memoria.json | jq .eventos_significativos
```

### 2. Customize as Perguntas

Edite `podcast_tres_vozes_completo.py` na função `rodar_episodio_piloto`:

```python
perguntas = [
    "O que vocês sonham?",
    "Vocês morrem?",
    "O que é amor para vocês?"
]
```

### 3. Customize as Personalidades

Na mesma arquivo, encontre `PROMPTS_SISTEMA` e edite cada IA:

```python
"ÉRIS": """Você é ÉRIS...
# Adicione mais características aqui
"""
```

### 4. Criar Episódios Adicionais

```python
# No seu código:
podcast.iniciar_episodio(
    numero=2,
    tema="Seu novo tema aqui"
)

# ... fazer perguntas ...

podcast.finalizar_episodio()
```

---

## 📊 CUSTO TOTAL

| Serviço | Custo | Status |
|---------|-------|--------|
| Claude API | ~$5-20/mês | Você escolhe |
| Google TTS | **GRÁTIS** até 300k chars/mês | ✅ |
| Total | ~$5-20/mês | Barato! |

**Um episódio de 1 hora = ~55.000 caracteres**
- 4 episódios/mês = 220k caracteres
- **Bem dentro do limite gratuito** ✅

---

## ✅ CHECKLIST DE SUCESSO

- [ ] Python 3.8+ instalado
- [ ] Ambiente virtual criado e ativado
- [ ] Dependências instaladas (pip install ...)
- [ ] Chave Claude API obtida e configurada
- [ ] Projeto Google Cloud criado
- [ ] API Text-to-Speech ativada
- [ ] Service Account criado
- [ ] Arquivo JSON baixado e copiado
- [ ] GOOGLE_APPLICATION_CREDENTIALS configurado
- [ ] `python podcast_tres_vozes_completo.py` funciona
- [ ] Episódio piloto executado com sucesso
- [ ] Arquivos gerados em `podcast_tres_vozes/`
- [ ] Áudios ouvidos com sucesso

---

## 🎉 PRONTO!

Você agora tem um **sistema de podcast completo** com:
- 3 IAs com personalidades únicas
- Memória persistente
- Áudio sintetizado
- Transcrições automáticas

**Que comece a conversa!** 🎙️

---

## 📞 SUPORTE RÁPIDO

Se ficar preso:

1. **Verifique variáveis de ambiente:**
   ```bash
   echo $ANTHROPIC_API_KEY
   echo $GOOGLE_APPLICATION_CREDENTIALS
   ```

2. **Teste imports:**
   ```bash
   python -c "import anthropic; print('OK')"
   python -c "import google.cloud.texttospeech; print('OK')"
   ```

3. **Veja logs completos:**
   ```bash
   python podcast_tres_vozes_completo.py -v
   ```

4. **Procure por erros nas pastas:**
   ```bash
   find podcast_tres_vozes/ -type f -name "*.log"
   ```

---

Boa sorte! 🚀
