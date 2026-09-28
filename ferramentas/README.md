# Ferramentas do Estúdio de Animação

Tudo gratuito e local (exceto a geração de imagens, na GPU grátis do Kaggle).

| pasta | o que faz | por onde começar |
|---|---|---|
| `animacao\` | **esteira de uma história inteira**: roteiro + áudio → vídeo (vertical ou horizontal) | `produzir.py PASTA etapa` (alinhar, fichas, planos, falas, montar) |
| `cenas\` | gera cenas no Kaggle (FLUX.2 klein) e o **fiscal** que aprova ou reprova cada uma | `cenas\README.md` |
| `visemas\` | **boca falando** sincronizada com a fala, no traço da imagem (LivePortrait) | `visemas\README.md`, `falar.py` |
| `revisor\` | mede qualidade de vídeo com rosto falando (usado pelo agente `revisor-animacao`) | `analisar_animacao.py` |
| `terceiros\` | como reinstalar JoyVASA/syncnet/MuseTalk (fora do git) e as nossas alterações neles | `terceiros\README.md` |

Agentes do Claude Code (em `.claude\agents\`):
- `revisor-cenas`: confere **anatomia** (braços, mãos, caudas) e continuidade das imagens geradas; o fiscal
  automático não enxerga esses erros.
- `revisor-animacao`: dá nota a desenho, movimento da boca e sincronia de um vídeo de rosto falando.

Ambientes Python: `.venv_omni` (esteira, Kaggle, montagem) e `ferramentas\JoyVASA\.venv` (LivePortrait,
fiscal, boca). Os projetos de animação (imagens, áudios, vídeos) ficam em
`C:\Users\Filipe Pereira\Downloads\Animação\`.
