# 🎙️ Estúdio de Voz

Plataforma **100% local** de síntese de voz (TTS): clona uma voz a partir de uma
amostra, projeta vozes por características e narra histórias dando voz e emoção
próprias a cada personagem. Roda inteiramente na sua máquina, sem nuvem.

Usa **[OmniVoice](https://github.com/k2-fsa/OmniVoice)** (k2-fsa/OmniVoice) para a
síntese e **Gemma 3 4B** via **[Ollama](https://ollama.com)** como o "cérebro" que
interpreta o texto (quem fala e com qual emoção).

---

## As três abas

| Aba | O que faz |
|-----|-----------|
| 🎤 **Clone de Voz** | Analisa uma amostra de voz (≥ 3 s) e lê o texto que você digitar com aquela voz. |
| 🎨 **Design de Voz** | Cria uma voz nova a partir de características (gênero, idade, tom, estilo), sem precisar de uma referência. |
| 📖 **Contador de Histórias** | Lê uma história inteira, dando uma voz própria a cada personagem + emoção, com controle de ritmo, modo sussurro (ASMR) e música de fundo. (Esta aba usa a Gemma.) |

---

## Pré-requisitos

- **Python 3.10+** (testado no Windows).
- **GPU NVIDIA com CUDA** — veja o aviso abaixo.
- **[Ollama](https://ollama.com)** instalado e rodando, com o modelo Gemma 3 4B:
  ```bat
  ollama pull gemma3:4b
  ```

### Instalação

1. Crie um ambiente virtual e ative-o:
   ```bat
   python -m venv .venv_omni
   .venv_omni\Scripts\activate
   ```
2. Instale as dependências:
   ```bat
   pip install -r requirements.txt
   ```
   > **torch:** o `requirements.txt` fixa `torch==2.11.0`, mas para usar a GPU é
   > preciso o build com CUDA. Instale a partir do índice oficial, por exemplo:
   > ```bat
   > pip install torch==2.11.0 --index-url https://download.pytorch.org/whl/cu128
   > ```

---

## Como rodar

No Windows, basta executar o lançador:

```bat
INICIAR_ESTUDIO.bat
```

Ou rodar direto pelo Python:

```bat
.venv_omni\Scripts\python.exe app\estudio\estudio.py
```

A interface abre no navegador em **http://127.0.0.1:5006**.

> A primeira geração baixa/carrega o modelo — pode demorar um pouco na primeira vez.

---

## ⚠️ Requisitos de hardware

Este projeto roda **100% local** e precisa de uma **GPU NVIDIA**. Foi desenvolvido e
testado numa **RTX 2060 (6 GB)**. Como nessa VRAM a Gemma e o OmniVoice não cabem
juntos, o motor faz um ciclo de carga/descarga entre os dois modelos — funciona, mas
a aba Contador de Histórias é mais lenta por isso. GPUs com mais VRAM tendem a ser
mais rápidas.

---

## Voz de referência e trilha de fundo

O projeto **não inclui nenhum áudio** — vozes (especialmente de dubladores) e músicas
têm direitos de terceiros e não podem ser redistribuídas. **Você fornece os seus
próprios arquivos**, de preferência a sua própria voz ou algo que você tenha permissão
de usar.

Para começar, coloque na pasta [`vozes/`](vozes/) um `.wav` de **pelo menos 3 segundos**
de fala limpa (e, opcionalmente, um `.txt` de mesmo nome com a transcrição, que melhora o
clone). As instruções completas estão em [`vozes/README.md`](vozes/README.md). A música de
fundo do Contador de Histórias pode ser enviada direto pela interface.

Áudios não são versionados (o `.gitignore` cuida disso).

---

## Documentação técnica

Para os detalhes de implementação — o ciclo de memória da GPU, o tratamento de
finais de frase, a whisperização do modo sussurro, a atribuição de "quem fala", e
todas as decisões e desafios do projeto — veja **[DOCUMENTACAO.md](DOCUMENTACAO.md)**.
