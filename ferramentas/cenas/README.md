# Fiscal de cenas — gerar de novo até ficar bom

Cenas geradas por IA às vezes saem com defeito no rosto da personagem. O fiscal olha cada cena nova e,
se reprovar, o gerador tenta de novo com outra semente, até passar ou até o limite de tentativas.

Defeitos que ele pega (vistos na oração a São Alex, 27/09/2026):

| Defeito | Exemplo |
|---|---|
| **traço fantasma** — linha solta, mancha ou traço duplicado na pele | `o01_invocacao`: traço na testa, entre os olhos |
| **rabiscado / fora do padrão** — rosto mais rascunhado, sobrancelha rabiscada, traço duplicado | `o05_malware`, `o07_amem` |
| sem rosto detectável | — |

## Uso

Normalmente não se chama o fiscal direto: o gerador da oração já usa (motor klein no Kaggle, 2 versões por cena, até 3 rodadas).

```powershell
cd "F:\Projeto IA\animacao\historias\oracao_sao_alex\cenas"
& "F:\Projeto IA\.venv_omni\Scripts\python.exe" gerar_oracao.py --refazer o01_invocacao o05_malware o07_amem
```

- cada tentativa vai para `cenas\tentativas\<cena>_tN.png`;
- a primeira aprovada vira `<cena>.png` (a versão anterior fica em `tentativas\<cena>_anterior.png`);
- se nenhuma passar, `<cena>.png` não é tocada e o log aponta a melhor tentativa;
- todo veredito vai para `cenas\fiscal_log.jsonl` (nota, defeitos, o que o juiz viu);
- `--tentativas N` (padrão 2 por rodada) e `--rodadas N` (padrão 3); `--motor space` usa o Space do Hugging Face (cota curta).
  Quando a cota acaba, o laço para e avisa.

Fiscal sozinho (venv do JoyVASA):

```powershell
& "F:\Projeto IA\ferramentas\JoyVASA\.venv\Scripts\python.exe" "F:\Projeto IA\ferramentas\cenas\fiscal.py" CENA.png --padrao APROVADA1.png APROVADA2.png
```

Imprime um JSON: `{"aprovada": false, "nota": 7.0, "traco_fantasma": false, "rabiscado": true, ...}`.

## Gerador: FLUX.2 klein no Kaggle (padrão desde 27/09/2026)

As cenas são geradas numa GPU grátis do Kaggle (2× T4, 30 h por semana), conta `filipepereira21`,
token em `C:\Users\Filipe Pereira\.kaggle\access_token`. O Filipe aprovou o traço do klein ("ficou
excelente"): segue a referência original, com traço de quadrinho nítido.

| Arquivo | Papel |
|---|---|
| `kaggle_cenas.py` | piloto local (.venv_omni): envia o trabalho como dataset privado, dispara o notebook, espera, baixa |
| `kaggle/gerador.py` | roda no Kaggle. Motor `klein`: codifica os prompts, depois gera nas **duas T4 em paralelo**, 4 passos, ~25 s por imagem. Motor `qwen` (Rapid-AIO + LoRA anime, traço antigo): lento, ~2 min por imagem |
| `kaggle/preparar.py` | roda **uma vez** (sem GPU): guarda o klein na conta (notebook `pandora-modelos`), e o gerador monta esse cache em vez de baixar |

Otimizações: modelo guardado na conta, duas placas em paralelo, fiscal em lote (um processo por rodada,
compara primeiro com um padrão só) e 2 versões por cena (só as reprovadas voltam na rodada seguinte).

Pontos técnicos: o VAE roda em fp32 (em fp16 sai imagem preta); o Rapid-AIO do Qwen vem em fp8 e é
convertido para fp16 antes de ir para 4 bits.

## Como julga

1. Recorta o rosto da cena (203 pontos do LivePortrait, que funcionam em desenho) — na CPU.
2. Põe lado a lado com o rosto de cada cena **aprovada** (padrão: `o02_quinze_dias` e `o04_luz`,
   em `gerar_oracao.py > PADROES`).
3. Pergunta ao **Qwen3-VL 4B** local (Ollama, grátis): traço fantasma? rabiscado? nota de estilo 0–10?
   A pergunta avisa que expressão, olhos abertos/fechados, mãos e pose podem mudar.
4. Um defeito só conta se **confirmado**: aparece em todas as comparações, ou vem com nota ≤ 7.
   Aprova sem defeito confirmado e com nota média ≥ 7.

Calibração nas 7 cenas da oração: **7/7** (reprovou 1, 5 e 7; aprovou 2, 3, 4 e 6). A regra de
confirmação foi ajustada nessas mesmas cenas, então acompanhe o `fiscal_log.jsonl` nas próximas.
~50 s por cena na RTX 2060.

## GPU

Antes de julgar, o fiscal pede ao Estúdio Web (`POST /api/gpu/liberar`, se estiver aberto) para
descarregar OmniVoice e Gemma, e tira os outros modelos do Ollama da placa. No fim descarrega o
Qwen3-VL, e a placa fica livre para a animação.

## O que foi testado e descartado

| Tentativa | Por que não |
|---|---|
| DINOv2 (semelhança de rosto) | não separa: a cena 5 ficou igual às boas |
| densidade de traços na pele (DoG) | a própria referência pontuou mais "rabiscada" que as ruins |
| `gemma3:4b` como juiz | não viu o traço fantasma, aprovou 5 e 7 e reprovou 2 e 3 |
| Qwen3-VL em Space do Hugging Face | gasta a mesma cota grátis de GPU que o gerador de cenas |
| `qwen3-vl:8b` local | 6,2 GB não cabem nos 6 GB da placa: ~1 min por consulta, metade na CPU |
