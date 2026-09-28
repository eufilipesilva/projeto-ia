# Estúdio de Animação — histórias ilustradas animadas

Transforma **roteiro + áudio narrado** em vídeo (vertical para TikTok/Shorts, ou horizontal): ilustrações
consistentes, movimento suave, legendas mágicas com cor por personagem, música livre e créditos prontos.
Serve para **qualquer história**; nada específico de uma história fica no código, só no `projeto.json` dela.

## Estrutura

```
animacao\
  historias\<nome>\     uma pasta por história (fonte da verdade: projeto.json)
  elenco\               BIBLIOTECA reutilizável
    personagens\<id>\   ficha.png + ficha.json (descrição, humano, espécie, anatomia, cor da legenda, origem)
    cenarios\<id>\      ficha.png + ficha.json
  estilos\<id>.json     texto de estilo + tamanho de geração + tema de legenda
  musicas\              trilhas LIVRES + catalogo.json (licença e crédito obrigatório de cada uma)
  docs\plano_estudio\   o superplano original (index.html e PDF)
```

O motor fica em `F:\Projeto IA\ferramentas\` (ver `ferramentas\README.md`).

## Fazer uma história nova

```powershell
$py = "F:\Projeto IA\.venv_omni\Scripts\python.exe"
$e  = "F:\Projeto IA\ferramentas\animacao\produzir.py"

& $py $e tres_porquinhos novo --roteiro roteiro.txt --audio narracao.wav --titulo "Os Três Porquinhos" --musica fairytale_waltz
#   -> cria historias\tres_porquinhos\ e já alinha o áudio ao roteiro (linha_do_tempo.json)
#   storyboard: preencha personagens, cenários e planos no projeto.json (ou peça ao Claude)
& $py $e tres_porquinhos fichas          # desenha só o que NÃO vem do elenco (4 opções cada)
#   agente revisor-cenas escolhe; copie para fichas\<nome>.png
& $py $e tres_porquinhos elenco --ids lobo=lobo_mau_2   # guarda as novas fichas na biblioteca
& $py $e tres_porquinhos planos          # imagens dos planos no Kaggle
#   agente revisor-cenas com planos\para_revisao.json -> planos\revisao_N.json
& $py $e tres_porquinhos escolhas        # instala as escolhidas + manifesto + folha dos planos
& $py $e tres_porquinhos planos --refazer-revisao   # só se sobrou reprovado (repita revisor + escolhas)
& $py $e tres_porquinhos compor          # planos por composição, se houver
& $py $e tres_porquinhos montar          # vídeo final + creditos.txt  (--rascunho = prévia rápida)
& $py $e tres_porquinhos status          # a qualquer momento: o que falta
```

Roteiro no formato do Estúdio, uma fala por marcação: `[narra:ternura] Era uma vez...` / `[lobo:neutra] Abra a porta!`.

## projeto.json (o essencial)

```json
{
 "titulo": "...", "formato": [1080, 1920], "audio": "audio.wav", "roteiro": "roteiro.txt",
 "linha_do_tempo": "linha_do_tempo.json", "saida": "video.mp4",
 "estilo": {"biblioteca": "livro_aquarela"},
 "musica": {"biblioteca": "fairytale_waltz", "volume_db": -22},
 "legenda": {"cores": {"narra": "C9A7FF"}},
 "personagens": {"lobo": {"elenco": "lobo_mau"},
                 "porquinho1": {"descricao": "...", "humano": false, "especie": "pig", "anatomia": "2 braços, 2 pernas, 1 rabinho"}},
 "cenarios": {"floresta": {"elenco": "floresta"}},
 "planos": [
  {"id": "p01", "linha": 0, "imagem": "planos/p01.png", "cenario": "floresta", "personagens": ["porquinho1"],
   "prompt": "o que acontece no plano (em inglês)", "checar": "porquinho1"},
  {"id": "p02", "linha": 3, "imagem": "planos/p01.png"},
  {"id": "p09", "linha": 20, "imagem": "planos/p09.png", "base": "p08", "personagens": ["lobo"],
   "prompt": "add the wolf knocking on the door"},
  {"id": "p12", "linha": 26, "imagem": "planos/p12.png",
   "composicao": {"sobre": "planos/tentativas/p12_sem_x.png", "origem": "planos/p11.png",
                  "caixa": [x0, y0, x1, y1], "posicao": [x, y], "escala": 0.6, "espelhar": true}}
 ]
}
```

- `"linha": k` = o plano começa na fala k da linha do tempo (o motor calcula o tempo).
- Plano sem `prompt` e com a `imagem` de outro = **reaproveita** aquela imagem (diálogo alternado).
- `"base"`: **edita um plano já aprovado**, acrescentando quem chega (quem já estava fica igual). Continuidade.
- `"composicao"`: recorta um personagem de um plano aprovado e cola em outro (`sobrepor.py`). Determinístico.
- `"sem_referencia": ["x"]`: o personagem entra só pela descrição (use quando a pose da cena é muito diferente
  da ficha, ex.: ficha em pé e cena deitado).
- `"pose": "poses/y.png"`: imagem com a pose certa, copiada pelo gerador.
- `"fala": [{"linha": k, "rosto": "esquerda"}]` + etapa `falas`: boca falando (opcional).

## Regras de ouro (aprendidas na Chapeuzinho, 27–28/09/2026)

1. **Anatomia é conferida por olho**: o agente `revisor-cenas` vê cada imagem E os recortes ampliados
   (`planos\detalhes\`). Fiscais automáticos grátis (Qwen3-VL 4B/8B, MediaPipe, Gemini 2.5 Flash) não pegam
   braço duplicado, perna a mais ou cauda dupla.
2. **Um personagem acrescentado por vez** no modo `base`; dois de uma vez fazem o modelo misturar personagens.
3. **Descrição de personagem não cita outro personagem** ("vestido como a vovó" fazia a vovó aparecer).
4. **Animal + pessoas na mesma cena**: o motor já avisa "um animal só, só ele tem cauda" (por `especie`).
5. **Continuidade**: quem está em cena continua em cena (use `base` ou `composicao`), o cenário pedido tem que
   aparecer (quarto com cama, porta fazendo parte da casa).
6. **Música só livre** (`musicas\catalogo.json`); as músicas antigas do projeto são comerciais e fazem o vídeo ser
   silenciado/bloqueado. O `creditos.txt` sai pronto para a descrição.
7. **Conteúdo infantil**: cenas pesadas viram versões gentis; no YouTube marque "Feito para crianças"; no
   TikTok, o rótulo de conteúdo gerado por IA.

## Reprodutibilidade

- `projeto.json` + bibliotecas descrevem a história inteira; `status` confere o que falta.
- Cada imagem gerada tem um `.json` ao lado (prompt, semente, referências, tamanho, motor) e cada plano
  aprovado fica no `planos\manifesto.json`.
- Teste de 28/09/2026: a Chapeuzinho convertida para este formato remontou o vídeo com os quadros
  **idênticos** ao aprovado, e a composição do p36 saiu idêntica pixel a pixel.
- Imagens e vídeos ficam fora do git (tamanho); faça cópia da pasta `animacao\` (ex.: OneDrive/Drive).
  As fichas do `elenco\` e todos os textos/JSON vão para o git.
