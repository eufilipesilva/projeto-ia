# Oração a São Alex (projeto anterior à esteira)

Primeira produção do estúdio (26–28/09/2026), horizontal 1920×1080, 45 s. Foi feita com scripts próprios,
antes da esteira genérica (`ferramentas\animacao\produzir.py`); ficou como está para não mexer no que foi
aprovado.

- `cenas\gerar_oracao.py` — gera as 7 cenas (FLUX.2 klein no Kaggle; `--motor klein`), com o fiscal.
- `cenas\montar_oracao.py` — monta o vídeo (parallax, boca falando nas cenas 1, 4 e 6, legenda karaokê).
- `cenas\falando\` — vídeos de boca falando (`ferramentas\visemas\falar.py`).
- `exemplos\03_oracao_cenas.mp4` — vídeo aprovado; `03_oracao_cenas_joyvasa.mp4` é a versão antiga.
- `cenas\versao_qwen\` — as cenas antigas (Qwen + LoRA anime), antes do klein.
- A cena 4 foi trocada por `tentativas\o04_luz_s401071962.png` (a anterior tinha dois braços esquerdos).

O áudio original está em `C:\Users\Filipe Pereira\Downloads\oracao.wav` e a foto do São Alex em
`C:\Users\Filipe Pereira\Downloads\saoalex.jpeg` (os scripts apontam para lá).

Para uma nova versão desta oração, o caminho recomendado é recriá-la com a esteira (`produzir.py novo`).
