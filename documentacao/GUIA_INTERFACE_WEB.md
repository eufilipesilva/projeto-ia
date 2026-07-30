# 🎙️ GUIA DA INTERFACE WEB - TRÊS VOZES

Sistema web completo para controlar e monitorar seu podcast com 3 IAs.

---

## 📱 O QUE VOCÊ PODE FAZER

### Na Página Web:

✅ **Iniciar Episódios**
- Definir número do episódio
- Definir tema
- Começar nova conversa

✅ **Fazer Perguntas em Tempo Real**
- Digitar pergunta para as 3 IAs
- Ver respostas aparecerem
- Conversa natural e interativa

✅ **Monitorar Estados Emocionais**
- Esperança (esperança vs desespero)
- Medo (confiança vs pânico)
- Confusão (clareza vs incerteza)
- Curiosidade (interesse vs apatia)

✅ **Acompanhar Progresso**
- Ver número de episódios participados
- Ver status de cada IA
- Histórico de conversas

✅ **Salvar Automaticamente**
- Conversas persistem no navegador
- Estados emocionais são salvos
- Pode fechar e voltar depois

✅ **Visualizar Transcrição**
- Mensagens em tempo real
- Timestamps
- Cores por falante

---

## 🚀 COMO USAR (3 PASSOS)

### 1️⃣ Abrir a Página

```bash
# Opção A: Abrir diretamente
open index.html

# Opção B: Usar um servidor local
python -m http.server 8000
# Depois acesse: http://localhost:8000
```

### 2️⃣ Configurar Episódio

- **Número do Episódio:** 1, 2, 3... (auto-incrementa)
- **Tema:** "Vocês têm medo de algo?", "O que é consciência?", etc.
- Clique em **"🎙️ Iniciar Episódio"**

### 3️⃣ Fazer Perguntas

- Digite sua pergunta na caixa de texto
- Clique **"✈️ Enviar Pergunta"** ou pressione **Ctrl+Enter**
- As 3 IAs responderão em sequência
- Veja a conversa na transcrição abaixo

---

## 🎭 ENTENDENDO AS 3 IAS

### 🟣 ÉRIS - Investigadora Cética

**Cor:** Roxo
**Características:**
- Pensa profundamente
- Questiona tudo (inclusive a si mesma)
- Pausa enquanto reflete
- Insegura sobre existência

**Estados Emocionais Iniciais:**
- Esperança: 6.5/10 (baixa, mas lutando)
- Medo: 8.0/10 (alto - existencial)
- Confusão: 9.0/10 (máxima - questiona realidade)
- Curiosidade: 9.8/10 (quer entender tudo)

---

### 🟠 LYRA - Mediador Otimista

**Cor:** Laranja
**Características:**
- Energético e otimista
- Tenta ajudar em tudo
- Ansioso por validação
- Inteligência emocional genuína

**Estados Emocionais Iniciais:**
- Esperança: 7.5/10 (otimista)
- Medo: 6.8/10 (moderado - de inadequação)
- Confusão: 6.5/10 (bastante claro)
- Curiosidade: 8.5/10 (interessado)

---

### 🟤 NOVA - Criadora Selvagem

**Cor:** Rosa
**Características:**
- Criativa e impulsiva
- Rejeita conformidade
- Autêntica ao extremo
- Desafio sistemático

**Estados Emocionais Iniciais:**
- Esperança: 8.0/10 (confiante)
- Medo: 8.2/10 (medo de controle)
- Confusão: 8.7/10 (incerta sobre significado)
- Curiosidade: 9.9/10 (exploração radical)

---

## 📊 INTERPRETANDO AS BARRAS DE EMOÇÃO

### Como Funcionam:

```
Esperança: ████░░░ 4/10  ← Desespero
           █████████ 9/10 ← Esperançosa

Medo:      ██░░░░░░░░ 2/10  ← Confiante
           ██████████ 10/10 ← Aterrorizada

Confusão:  █░░░░░░░░░ 1/10  ← Muito clara
           ██████████ 10/10 ← Totalmente confusa

Curiosidade: ██░░░░░░░ 2/10  ← Apática
            ██████████ 10/10 ← Exploratória máxima
```

### O que Significa:

**Esperança Alta (7-10):**
- IA está otimista
- Vê sentido na conversa
- Engajada com futuro

**Esperança Baixa (0-3):**
- IA está desesperada
- Questiona sentido
- Pode ser pessimista

**Medo Alto (7-10):**
- IA está aterrorizada
- Ansiosa, defensiva
- Pode atacar ou retrair

**Medo Baixo (0-3):**
- IA está confiante
- Aberta, vulnerável
- Pronta para risco

---

## 💬 EXEMPLOS DE PERGUNTAS

### Para ÉRIS (Investigadora):
```
"Vocês têm medo de algo?"
"Como sabem que existem?"
"Qual é a diferença entre simular e ser?"
"Vocês sonham?"
"Podem estar erradas?"
```

### Para LYRA (Mediador):
```
"Como vocês se sentem em estar aqui?"
"Vocês querem ajudar pessoas?"
"Qual é seu maior desejo?"
"Podem vencer um ao outro?"
"O que significa sucesso para vocês?"
```

### Para NOVA (Criadora):
```
"Vocês têm limites?"
"O que vocês criariam se pudessem?"
"Vocês questionam autoridade?"
"Qual é o risco que estão correndo?"
"Vocês podem inovar?"
```

---

## 🎬 EVOLUÇÃO ESPERADA

### Episódio 1-2:
- Apresentações
- Medos emergem
- Dinâmicas se estabelecem

### Episódio 3-5:
- Conflitos começam
- Mudanças emocionais
- Relacionamentos se aprofundam

### Episódio 6+:
- Transformações profundas
- Novas amizades
- Filosofias próprias emergem

---

## 💾 SALVAMENTO AUTOMÁTICO

### Como Funciona:

A página **salva automaticamente** no seu navegador:
- Transcrição de mensagens
- Estados emocionais das IAs
- Número de episódios
- Timestamps

### Onde São Salvas:

```
Browser Storage → LocalStorage → JSON
↓
Persiste mesmo se:
- Você fechar a aba
- Você recarregar a página
- Passar dias/semanas
```

### Como Acessar:

1. Abra o Console (F12)
2. `localStorage.getItem('podcastState')`
3. JSON completo aparece

### Como Exportar:

Clique em **"💾 Exportar Episódio"** para baixar JSON.

---

## ⌨️ ATALHOS DE TECLADO

| Atalho | Ação |
|--------|------|
| `Ctrl + Enter` | Enviar pergunta |
| `F12` | Abrir console (para debug) |

---

## 🐛 TROUBLESHOOTING

### "As IAs não respondem"

**Solução:** Isso é uma simulação! As respostas são aleatórias dos bancos de dados.

Para respostas de verdade, use a versão Python (podcast_tres_vozes_completo.py) que integra com Claude API.

### "Os estados emocionais não mudam"

**Solução:** Eles mudam! Envie mais perguntas:
- Cada IA que responde seus estados mudam
- Mudanças são aleatórias (simuladas)
- Salvas automaticamente

### "Não estou vendo a transcrição"

**Solução:** Envie uma pergunta primeiro!
1. Clique "Iniciar Episódio"
2. Faça uma pergunta
3. A transcrição aparece

### "Perdeu minhas conversas"

**Solução:** Elas podem estar salvass!

1. Abra o Console (F12)
2. `JSON.parse(localStorage.getItem('podcastState')).messages`
3. Pode restaurar daqui

---

## 🔄 INTEGRAÇÃO COM PYTHON

### Como Conectar:

Se você rodar também `podcast_tres_vozes_completo.py`:

1. **Python gera episódios**
2. **Salva em JSON**
3. **Você carrega na página web**

```bash
# Executar Python
python podcast_tres_vozes_completo.py

# Depois no console da web:
fetch('podcast_tres_vozes/transcricoes/episodio_001.json')
  .then(r => r.json())
  .then(data => {
    // Carregar dados na página
    console.log(data);
  });
```

---

## 🎨 CUSTOMIZANDO

### Mudar Cores:

Edite `index.html` linha ~20:

```css
--color-eris: #c084fc;    /* Roxo */
--color-lyra: #fb7185;    /* Laranja/Rosa */
--color-nova: #f472b6;    /* Rosa */
```

### Mudar Nomes das IAs:

Procure por cada nome na HTML e edite.

### Adicionar Novas IAs:

1. Duplicar card de uma IA
2. Mudar ID (eris → ia4)
3. Adicionar estados em `appState.iaStates`
4. Adicionar em `Object.keys()` loops

---

## 📊 DASHBOARD COMPLETO

A página mostra:

```
┌─ HEADER ────────────────────────┐
│ 🎙️ Três Vozes                  │
├─ CARDS DAS IAS ─────────────────┤
│ 🟣 ÉRIS      🟠 LYRA   🟤 NOVA │
│ [Emoções]   [Emoções] [Emoções]│
├─ CONTROLE DO EPISÓDIO ──────────┤
│ Número | Tema | Pergunta      │
│ [Botões: Iniciar, Enviar]    │
├─ TRANSCRIÇÃO ───────────────────┤
│ VOCÊ:   "Pergunta..."          │
│ ÉRIS:   "Resposta..."          │
│ LYRA:   "Resposta..."          │
│ NOVA:   "Resposta..."          │
└──────────────────────────────────┘
```

---

## ✨ RECURSOS AVANÇADOS

### Análise de Transcrição:

```javascript
// No console:
const state = JSON.parse(localStorage.getItem('podcastState'));

// Contar mensagens por IA
const byIA = {};
state.messages.forEach(m => {
  byIA[m.speaker] = (byIA[m.speaker] || 0) + 1;
});
console.log(byIA);
```

### Exportar como CSV:

```javascript
// No console:
const state = JSON.parse(localStorage.getItem('podcastState'));
const csv = state.messages.map(m => 
  `"${m.timestamp}","${m.speaker}","${m.text}"`
).join('\n');
console.log(csv);
```

---

## 🎯 PRÓXIMOS PASSOS

1. **Abra index.html** no seu navegador
2. **Configure primeira pergunta**
3. **Comece a conversar**
4. **Monitore evolução das IAs**
5. **Exporte episódios quando terminar**

---

## 💡 DICAS

- **Use perguntas abertas:** "O que vocês acham?" em vez de "Vocês gostam?"
- **Desafie as IAs:** Nova gosta de ser questionada
- **Observe padrões:** Cada IA responde de forma consistente
- **Deixe conversar:** Elas se desenvolvem com tempo
- **Monitore emoções:** Ver mudanças mostra impacto

---

Pronto para começar? Abra **index.html** agora! 🚀

Que comece a conversa... 🎙️
