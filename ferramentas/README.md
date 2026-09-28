# Ferramentas do Estúdio de Animação (o motor)

Tudo gratuito; roda local, exceto a geração de imagens (GPU grátis do Kaggle). **Como usar para fazer uma
história: `F:\Projeto IA\animacao\README.md`.** As histórias, o elenco reutilizável, estilos e músicas ficam em
`F:\Projeto IA\animacao\`.

| pasta | o que faz | peças |
|---|---|---|
| `animacao\` | **a esteira**: de roteiro + áudio ao vídeo | `produzir.py` (comando único, por etapas), `projeto.py` (carrega/confere o projeto.json e as bibliotecas), `alinhar.py` (áudio × roteiro), `montar.py` (vídeo, legendas, música, créditos), `conferencia.py` (folhas e recortes para o revisor), `sobrepor.py` (recorta e cola personagem), `fontes\` |
| `cenas\` | geração de imagens e fiscal | `kaggle_cenas.py` (piloto local) + `kaggle\gerador.py` (roda no Kaggle, 2× T4) + `kaggle\preparar.py` (guarda o modelo na conta, uma vez); `fiscal.py` (opcional: rosto/estilo); `maos.py` (teste de mãos, descartado) |
| `visemas\` | **boca falando** sincronizada, no traço da imagem | `falar.py`, `boca.py`, `fonemas.py` |
| `revisor\` | métricas de vídeo com rosto falando | `analisar_animacao.py`, `syncnet_lse.py` |
| `terceiros\` | reinstalar JoyVASA/syncnet/MuseTalk (fora do git) e as nossas alterações neles | `README.md`, patches |

Agentes do Claude Code (`.claude\agents\`):
- `revisor-cenas`: escolhe a melhor versão de cada imagem e confere **anatomia** e continuidade (o fiscal não vê).
- `revisor-animacao`: dá nota a desenho, movimento da boca e sincronia de um vídeo de rosto falando.

Ambientes Python:
- `.venv_omni` — esteira, Kaggle, alinhamento, montagem;
- `ferramentas\JoyVASA\.venv` — LivePortrait (boca falando, fiscal, recorte de rosto);
- `ferramentas\cenas\.venv_maos` — rembg (recorte de personagem em `sobrepor.py`) e MediaPipe.

Segredos nunca vão para o git: token do Kaggle em `%USERPROFILE%\.kaggle\access_token`, chave do Gemini na
variável de usuário `GEMINI_API_KEY`.
