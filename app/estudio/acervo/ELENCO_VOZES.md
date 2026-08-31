# Elenco — como cada voz deve soar

Documento de **direção**, não de engenharia. Descreve o que se quer ouvir; os
alvos numéricos em `casar_vozes.py` são derivados daqui, nunca o contrário.

A primeira tentativa falhou justamente por inverter essa ordem: tirei alvos de
F0 e centroide dos atributos do OmniVoice e saí casando números. Deu 35 de 40
"dentro de 2,5 semitons" e mesmo assim soou errado — porque altura de voz não é
personagem.

## Os cinco eixos

Altura sozinha não distingue ninguém. O que caracteriza uma voz:

| eixo | o que é | o que carrega |
|---|---|---|
| **altura** (F0) | grave ↔ agudo | tamanho aparente, idade |
| **variação** (desvio do F0) | monótono ↔ cantado | **temperamento** — o eixo mais expressivo |
| **corpo** (formantes) | encorpado ↔ miúdo | tamanho físico real |
| **tempo** | arrastado ↔ apressado | energia, urgência, cansaço |
| **textura** (ar/aspereza) | limpa ↔ soprada ↔ áspera | idade, saúde, intenção |

**A variação é o eixo que eu estava ignorando, e é o mais dramático.** Lobo e
rei podem ter a mesma altura: o rei é grave e *plano* porque autoridade não
argumenta; o lobo é grave e *plano* porque calma assusta mais que rosnado. Já o
rato e o galo são agudos e *muito* variados — pequenos não têm controle de
respiração. Foi por não medir isso que tudo soou parecido.

---

## Realeza

**rei** — Autoridade sem esforço. Grave, lento, quase sem variação: quem manda
não precisa convencer. Sai do peito, não da garganta. Pausas longas. Nunca
grita — se gritasse, não seria rei.

**rainha** — Controle. Mais alta que o rei e igualmente firme. Articulação
precisa, beirando o frio. Pouca variação, mas não morta: contida.

**príncipe** — Jovem e franco. Médio, limpo, direto, sem peso nem ironia. Ritmo
ágil. É a voz mais "normal" do elenco, de propósito — ele é o contraponto.

**princesa** — Clara e curiosa. Alta, com variação grande: ainda se encanta com
as coisas. Leve, sem nenhum peso.

## Família

**mãe** — Calor. Média, um pouco grave para mulher, variação suave e constante.
É a voz que acalma. Ritmo tranquilo, jamais apressada.

**madrasta** — Frieza educada. **Mesma altura da mãe, temperatura oposta.** O
truque é a variação: plana, controlada, sem carinho. Ela não grita nem rosna —
soa correta, e é isso que incomoda. Se contrastar com a mãe, está certa.

**pai** — Firme e cansado. Médio-grave, pouca variação, ritmo moderado. Alguém
que trabalhou o dia inteiro.

**madrinha** — Idade e bondade. Levemente trêmula, mais lenta, sorriso audível.

**filho / irmão** — Jovens, médios, com energia. Variação média-alta, ritmo
rápido, sem gravidade.

**menina / lila / clara** — Criança de verdade: aguda, muito variada, rápida,
sem controle de respiração. Frases que começam animadas e desabam no fim.

## Gente do povo

**velhinha** — Fina e um pouco trêmula. Lenta, com ar na voz. Doçura frágil.

**pastor · moleiro · lenhador · camponês · caçador** — Homens do campo: graves,
lentos, econômicos. Falam pouco e sem ornamento. Variação baixa.

**senhor · senhora** — Idade sem fragilidade. Médios, ritmo pausado, variação
moderada.

**alfaiate** — O pequeno esperto. Agudo para homem, **rápido**, muito variado,
confiante demais para o próprio tamanho. A vaidade tem que aparecer.

**criada** — Jovem, prática, ritmo apressado, variação média. Fala trabalhando.

## Vilões

Aqui a regra é contraintuitiva e vale para os três: **ameaça não é volume nem
rosnado, é calma.** Vilão que grita vira palhaço; vilão que fala baixo e devagar
assusta. Nada de textura áspera artificial — já testamos, soa como defeito de
gravação, não como perigo.

**lobo** — Grave, **muito** pouca variação, lento, com peso. Educado até o
momento em que não é. A ameaça mora na paciência.

**bruxa** — Áspera e grave para mulher, ritmo **irregular** — acelera e para sem
aviso. É a imprevisibilidade que assusta, não a rouquidão.

**diabo** — Grave, macio, lento e **cortês**. O mais perigoso dos três porque é
o mais simpático. Nunca se altera.

**gigante** — Muito grave, muito lento, corpo enorme. Não é mau, é grande — a
diferença tem que se ouvir.

## Bichos

O tamanho manda no corpo; o temperamento manda na variação.

**sapo** — Grave, empolado, arrastado. Um quê de cômico na formalidade.

**burro** — Lento, grave, **monótono**. O cansaço é o traço principal; ele já
viu de tudo.

**cachorro** — Entusiasmo puro. Médio-grave, **rápido**, variação alta, sempre
pronto. O oposto exato do burro, e eles contracenam.

**gato** — Macio e insinuante. Variação média, ritmo elástico: acelera, para,
retoma. Nunca ansioso.

**raposa** — Esperteza. Média, articulação limpa, ágil, variação *controlada* —
ela calcula antes de falar.

**galo** — Estridente e explosivo. Agudo, frases curtas, ataques bruscos,
variação altíssima. Cansativo de propósito.

**galinha** — Aguda e agitada, mas mais redonda que o galo. Tagarela.

**rato · pássaro** — Pequenos e nervosos: muito agudos, muito rápidos, variação
enorme, corpo mínimo.

**cavalo** — Grave, sereno, ritmo constante. Nobre sem ser pomposo.

**urso** — Muito grave, lento, mas com calor. Grande e bonachão.

**coelhinho** — Agudo, rápido, doce. Sem a estridência do rato.

## Mágicos

**fada** — Leve e aérea. Aguda, muito variada, com ar na voz. Parece flutuar.

**anão** — Pequeno **mas adulto**. Agudo com corpo — não é criança. Ritmo firme,
variação média. Trabalhador, não fofo.

---

## Contrastes que precisam se sustentar

Personagens que contracenam não podem se confundir. Estes pares são o teste:

| par | o que os separa |
|---|---|
| mãe × madrasta | mesma altura, **variação** oposta |
| rei × lobo | mesma gravidade e planura, **corpo** e tempo distintos |
| burro × cachorro | mesma faixa, **tempo e variação** opostos |
| rato × galo | ambos agudos e agitados, **corpo** distingue |
| princesa × fada | ambas altas e variadas, **textura** distingue (fada tem ar) |
| diabo × rei | ambos graves, lentos e planos; o diabo é **mais macio** |

Se um desses pares soar igual, a escolha está errada — mesmo que os números
digam o contrário.
