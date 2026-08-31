# Formato das histórias adaptadas

Regras descobertas rodando "A bela adormecida" pelo pipeline real (`_beats_historia`
→ `roteirizar_historia` → `elenco_do_roteiro`). Não são preferências de estilo: cada
uma corrige um erro concreto que apareceu na verificação.

Valem para as adaptações escritas à mão **e** para o prompt da Gemma.

---

## 1. Diálogo: travessão no início da linha, uma fala por linha

```
— Não fique triste — disse o sapo. — Antes de um ano, você vai ter uma filha.
```

O segmentador alterna fala/narração pelos travessões, então a linha acima vira
`FALA` / `narração` / `FALA` corretamente. Aspas também funcionam (retas, curvas,
`«»`, `„`), mas o travessão é o formato mais previsível.

Nunca misture aspas e travessão na mesma linha: se houver aspas, o segmentador usa
o ramo das aspas e ignora os travessões daquela linha.

## 2. Toda troca de falante precisa de tag de atribuição

A atribuição tem três camadas; a última é "herda o falante anterior". Uma fala sem
tag, logo depois da fala de outro personagem, **herda o falante errado**.

```
✗  — Estou fiando — respondeu a velhinha.
   — E o que é isso que roda tão depressa?          ← vira fala da velhinha

✓  — Estou fiando — respondeu a velhinha.
   — E o que é isso que roda tão depressa? — perguntou a princesa.
```

Falas seguidas do **mesmo** personagem podem dispensar a tag.

## 3. O rótulo do falante é a PRIMEIRA palavra depois do artigo

`_norm_nome` tira artigo (`o, a, os, as, um, uma, seu, sua, meu, minha`) e fica com
a primeira palavra restante, cortada em 16 caracteres. Consequências:

| tag escrita | nome do personagem | veredito |
|---|---|---|
| `disse a primeira` | `primeira` | ✗ ordinal vira personagem |
| `disse a última fada` | `ultima` | ✗ adjetivo antes do substantivo |
| `disse a madrinha mais velha` | `madrinha` | ✓ |
| `gritou a fada zangada` | `fada` | ✓ |

**Ponha o substantivo primeiro.** Ordinais e adjetivos na frente criam personagens
fantasmas — três fadas viraram `primeira`, `segunda` e `terceira`, com três vozes
diferentes.

## 4. Personagens do mesmo papel devem compartilhar o rótulo

Três fadas que só dão presentes são um coro, não três papéis. Escrevendo
`a madrinha mais velha`, `a madrinha do meio`, `a madrinha do vestido azul`, todas
viram `madrinha` e falam com uma voz só — que é o desejável.

Para diferenciar de propósito, use **substantivos-cabeça diferentes**:
`madrinha` (as boas) vs `fada` (a não convidada).

## 5. No máximo 6 personagens com fala

`PALETA` tem 6 variações de voz e o índice dá a volta
(`PALETA[len(vozes) % len(PALETA)]`): o 7º personagem recebe a mesma voz do 1º.

Se passar de 6, transforme o papel menos importante em narração. Em "A bela
adormecida" o pastor perdeu as falas (viraram narração) e o elenco fechou em 6.

## 6. Evite nomes que colidem nos primeiros caracteres

`velhinho` e `velhinha` são personagens diferentes com nomes quase idênticos —
confunde a atribuição e o leitor. Trocado por `pastor` e `velhinha`.

---

## Alvos numéricos (para 6 anos)

Medidos com `acervo.metricas`. Referência: a versão aprovada de "A bela adormecida".

| medida | alvo | conseguido |
|---|---|---|
| palavras | ~650 | 725 |
| duração | ~5 min | 5,6 min |
| palavras por frase | 12–15 no máximo | 8,6 |
| ILF | > 70 | 77,5 |
| personagens com fala | ≤ 6 | 6 |

## Conteúdo

- Enredo e personagens preservados; final tranquilo.
- Repetição é **estrutural**, não verbal. O refrão certo é a lista do castelo
  adormecendo e a mesma lista acordando na mesma ordem — não "muito, muito".
- Sem morte em cena. Quem tentava atravessar a cerca desiste e volta para casa,
  em vez de morrer nos espinhos.
- Detalhes plantados no começo devem voltar: os três presentes das madrinhas
  reaparecem em "cresceu boa, alegre e cantando como um passarinho".
- Sem título, sem moral no fim, sem "Era uma vez" obrigatório.
