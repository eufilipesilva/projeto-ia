# Chapeuzinho Vermelho — prova final do motor de animação

Áudio base: `_chapeuzinho_BR.wav` (22/06/2026), copiado aqui como `audio.wav`.
Destino: TikTok e YouTube Shorts.

## 1. O que o áudio tem

- **2 min 50 s**, 47 falas: a narradora conduz (28 falas) e há 19 falas de personagens, quase
  todas entre 47 s e 150 s. O diálogo mais famoso ("Vovó, por que essas orelhas tão grandes?")
  cai em 98–112 s.
- O alinhamento casou **96 % das palavras** com o roteiro (`linha_do_tempo.json`): cada fala tem
  começo, fim e o tempo de cada palavra.
- **Todos os personagens são a mesma voz (Pandora) com o tom alterado**, e a separação é pequena:

| personagem | tom médio | observação |
|---|---|---|
| Chapeuzinho | 220 Hz | a mais aguda, funciona |
| vovó | 201 Hz | quase igual à narradora (192 Hz) |
| mãe | 197 Hz | praticamente igual à narradora |
| lobo disfarçado | 179 Hz | |
| caçador | 175 Hz | soa feminino |
| lobo | 161 Hz | pouco grave para um lobo |

  No vídeo, a legenda com cor por personagem e o close de quem fala compensam boa parte disso.

## 2. Formato do vídeo

| item | valor | por quê |
|---|---|---|
| tela | 1080 × 1920, 9:16, 30 fps | padrão de TikTok e Shorts |
| duração | 2 min 50 s | cabe no limite de 3 min do Shorts; no TikTok sem problema |
| cortes | a cada ~4 s (44 planos, 39 imagens) | vídeo curto pede troca frequente de imagem |
| legenda | karaokê grande, fonte arredondada, **cor por personagem** | muita gente assiste sem som; a cor diz quem fala |
| posição da legenda | a ~30 % da altura, a partir de baixo, e longe da borda direita | fora da área dos botões e da descrição do app |
| título | "Chapeuzinho Vermelho" no topo, nos primeiros 3 s | identifica a história logo de cara |
| volume | −14 LUFS | nível que as duas plataformas usam; não fica baixo nem estoura |
| movimento | parallax suave e zoom lento | o estilo contido que você aprovou |

## 3. Esteira (um comando por etapa)

```powershell
$py  = "F:\Projeto IA\.venv_omni\Scripts\python.exe"
$esteira = "F:\Projeto IA\ferramentas\animacao\produzir.py"
$proj = "F:\Projeto IA\animacao\historias\chapeuzinho_vermelho"
& $py $esteira $proj alinhar     # feito
& $py $esteira $proj fichas      # em andamento: 4 opções de cada personagem e cenário
#  >>> VOCÊ escolhe as fichas (fichas\opcoes\ -> fichas\<nome>.png)
& $py $esteira $proj planos      # 39 imagens, 2 versões cada, o fiscal escolhe
& $py $esteira $proj montar      # vídeo final (--rascunho para prévia rápida)
```

| etapa | quem faz | tempo estimado |
|---|---|---|
| alinhar | PC | 1 min, feito |
| fichas | Kaggle | ~20 min |
| escolher fichas | **você** | alguns minutos |
| planos | Kaggle + fiscal no PC | ~45 min |
| falas | PC | ~25 min |
| montar | PC | ~8 min |

Depois da escolha das fichas, o resto roda sozinho: cerca de 1 h 20 min de máquina, sem precisar
acompanhar.

**Storyboard:** está em `_montar_storyboard.py` (gera o `projeto.json`). Estilo: livro ilustrado
infantil em aquarela, com 6 personagens (Chapeuzinho, mãe, vovó, lobo, lobo disfarçado de vovó,
caçador) e 5 cenários (casa, bosque, floresta, casa da vovó, quarto da vovó). As partes pesadas do
conto foram suavizadas para o público infantil: o lobo "engolindo" a vovó vira uma piada visual de
barriga redonda, e a barriga aberta vira a vovó sã e salva sendo ajudada pelo caçador.

## Atualização de 28/09/2026

- **Sem boca falando:** a narradora conta a história; as falas dos personagens aparecem na legenda com a cor
  de cada um. A etapa `falas` não é usada.
- **Anatomia:** depois de `fichas` e de `planos`, o agente `revisor-cenas` confere a folha de conferência
  imagem por imagem (braços, mãos, caudas, gente em cenário vazio) e grava `revisao.json`;
  `planos --refazer-revisao` refaz só as reprovadas, com a correção de pose sugerida.
- **Fichas a refazer:** mãe (saiu com cara de criança) e lobo disfarçado (vai partir da ficha do lobo escolhido).

## 4. Decisões suas

1. **Voz (antes de publicar).** Não sei de onde veio a voz de referência `pandora_007`. Se ela saiu
   de dublagem, jogo ou série, publicar um clone dela é arriscado: direito de voz do dublador e
   regras das plataformas sobre imitar pessoas reais. Duas saídas:
   - **manter este áudio** para a prova do motor (sem publicar), ou publicar se a voz for sua ou
     tiver origem livre;
   - **refazer o áudio com o elenco do acervo** (`app\estudio\acervo`), que já tem vozes de lobo,
     mãe, menina e caçador feitas a partir do MLS Portuguese (licença CC BY 4.0: pode publicar
     dando crédito). Isso também resolve a pouca diferença entre os personagens. A esteira de
     imagem não muda: basta alinhar o áudio novo.
2. **Estilo visual.** Pedi livro ilustrado em aquarela. Se preferir o traço de quadrinho da oração,
   troco o texto de estilo antes da etapa `planos`. As fichas vão mostrar como fica.
3. **Gancho.** Vídeo curto se decide nos primeiros 2 s. Opção: abrir com o lobo gritando "É para
   te comer!" (1 s, tirado do próprio áudio) e depois começar a história. Exige editar o áudio;
   faço se você quiser.
4. **Música.** Não há trilha no projeto. No TikTok, o melhor é adicionar um som pelo próprio app,
   e aí o vídeo sai sem música. Para o YouTube, uma faixa da Biblioteca de Áudio do YouTube (grátis
   e liberada para a plataforma) entra pelo campo `musica` do `projeto.json`.

## 5. Publicação

- **YouTube:** conteúdo feito para crianças precisa ser marcado como **"Feito para crianças"**
  (regra COPPA, obrigatória). Com isso, os comentários ficam desativados e não há anúncios
  personalizados.
- **TikTok:** marque o rótulo de **conteúdo gerado por IA**; a plataforma pede isso para esse
  tipo de conteúdo.
- **Título sugerido:** "Chapeuzinho Vermelho 🐺❤️ | Historinha para crianças"
- **Hashtags:** #chapeuzinhovermelho #historinha #historiainfantil #contosdefadas #historiaparadormir
- **Capa:** o close do lobo disfarçado na cama, com "Vovó, que orelhas grandes!".

## 6. Mudanças feitas no motor

| peça | mudança |
|---|---|
| `ferramentas\animacao\alinhar.py` | **novo**: roteiro + áudio → quem fala e quando, palavra a palavra |
| `ferramentas\animacao\produzir.py` | **novo**: a esteira inteira por etapas, guiada pelo `projeto.json` |
| `ferramentas\animacao\montar.py` | **novo**: montagem genérica, vertical ou horizontal; várias falas por plano; legenda com cor por personagem; título; trilha e efeitos; −14 LUFS |
| `ferramentas\animacao\fontes\` | fonte da legenda (Fredoka, licença OFL: pode publicar) |
| `ferramentas\cenas\kaggle\gerador.py` | desenha sem imagem base (fichas), aceita tamanho pedido (vertical), até 4 referências |
| `ferramentas\cenas\fiscal.py` | padrão e modo **por cena**; modo **estilo** (imagem inteira) para cenas sem rosto humano; cai sozinho para esse modo quando não acha rosto (o lobo) |
| `ferramentas\visemas\falar.py` | `--rosto esquerda\|direita\|maior` e `--regiao`: anima **quem** fala quando há mais de um rosto |

## 7. Riscos conhecidos

- **Boca do lobo:** o detector de rostos é treinado em rosto humano e talvez não ache o focinho.
  Nesse caso, os planos do lobo ficam só com o movimento suave, sem boca, e a legenda azul indica
  que é ele falando. Se ficar ruim, há o modelo de animais do LivePortrait para testar.
- **Consistência dos personagens:** cada plano usa as fichas escolhidas como referência, e o
  fiscal cobra o rosto do personagem principal. Mesmo assim, figurino e detalhes podem variar um
  pouco entre planos; o fiscal só pega o que for gritante.
- **Fiscal:** foi calibrado com a Pandora. No estilo livro ilustrado, pode precisar de ajuste de
  régua depois da primeira rodada.
