# Visemas — personagem desenhado falando

Faz a Pandora (ou qualquer personagem desenhado) falar a partir de **uma imagem parada + um áudio**:
boca sincronizada com a fala, no traço da própria imagem, e um balanço de cabeça lento e sutil.
Aprovado pelo Filipe em 27/09/2026 ("a boca contínua ficou muito boa").

## Uso

```powershell
$py = "F:\Projeto IA\ferramentas\JoyVASA\.venv\Scripts\python.exe"
& $py "F:\Projeto IA\ferramentas\visemas\falar.py" CENA.png FALA.wav SAIDA.mp4
```

Opções (os padrões são os aprovados):

| Opção | Padrão | O que faz |
|---|---|---|
| `--cabeca GRAUS` | 1.5 | balanço lento da cabeça (senoides de 3 a 9 s, não reage à voz). `0` = cabeça parada, só a boca é colada |
| `--suavizar-ms` | 15 | quanto a boca desliza entre fonemas (mais = mais mole) |
| `--adiantar-ms` | 40 | mostra a boca 1 quadro antes do som, como os animadores fazem |
| `--fps` | 25 | quadros por segundo |
| `--folha` | — | grava também `SAIDA_bocas.png` com os 9 formatos de boca, para conferir o desenho |

De outro script (no mesmo venv): `from falar import falar; falar(imagem, audio, saida)`.

Tempo: ~1,5 min para 7 s de vídeo na RTX 2060 (cada quadro é redesenhado). Com `--cabeca 0` é bem
mais rápido, porque quadros com a mesma boca se repetem.

## Como funciona

```
áudio ──► fonemas.py ──► marcas de boca (A..H, X) ──► curva suave de abertura/arredondamento
                                                                  │
imagem ─► boca.py (LivePortrait: calibra o rosto) ──► redesenha cada quadro ──► ffmpeg + áudio ──► vídeo
```

| Arquivo | Papel |
|---|---|
| `falar.py` | comando único; monta a curva da boca e o balanço da cabeça e grava o vídeo |
| `fonemas.py` | reconhece os fonemas (IPA, a cada 20 ms) com o wav2vec2 multilíngue e converte em formatos de boca, no formato JSON do Rhubarb. Sozinho: `fonemas.py FALA.wav` |
| `boca.py` | motor: usa o `retarget_lip` do LivePortrait (abertura), o ponto de expressão 14/y (arredondar para Ó/U) e a pose da cabeça; mede a abertura real para calibrar cada rosto |
| `modelos/wav2vec2-fonemas` | `facebook/wav2vec2-lv-60-espeak-cv-ft` (1,2 GB) |

Formatos de boca (nomes do Rhubarb), em `boca.py > FORMATOS`:
X repouso · A M/B/P fechada · B consoantes/I · C É · D Á · E Ó · F U · G F/V · H L.

Dependências: o venv do JoyVASA (`ferramentas\JoyVASA\.venv`, Python 3.11, torch 2.2.2 cu121), que já
traz o LivePortrait, e o ffmpeg no PATH.

## O que foi testado e descartado (27/09/2026)

Medições com o revisor (`ferramentas\revisor\analisar_animacao.py`; SyncNet LSE-C, maior = melhor).

| Tentativa | Resultado |
|---|---|
| **JoyVASA** (movimento gerado por IA) | LSE-C 3,7 a 4,2, mas lábios borrados e cabeça que às vezes erra |
| **MuseTalk 1.5** | só funciona em rosto real (4,9); na Pandora desenhada a boca vira mancha (0,1 a 2,5) |
| **Rhubarb Lip Sync** (reconhecedor de inglês) | erra em português: abre a boca antes da voz, trava em trechos (1,2) |
| **fonemas + bocas prontas trocadas** | 3,1 a 3,3; troca seca é pior que com transição |
| **fonemas + boca contínua** (atual) | 3,1 na o01z, 2,6 na o06; bocas nítidas, sincronia boa no olho |
| abrir mais pelo volume da voz / abrir menos | pioram o SyncNet (a abertura atual é o ponto ótimo) |

O SyncNet subestima este método: as bocas nítidas pontuam menos que os lábios borrados do JoyVASA.
Para julgar, use o `bocas.png` do revisor e o controle `--deslocar-audio 1.0`.

## Limites conhecidos

- Rosto muito pequeno na cena (boca < 30 px) funciona, mas o detalhe da boca some; cenas de fala
  ficam melhores com o rosto maior.
- Defeitos do desenho de origem (ex.: o traço fantasma no nariz da `o01_invocacao`) continuam no vídeo.
- Olhos não piscam (as cenas atuais têm olhos fechados).
