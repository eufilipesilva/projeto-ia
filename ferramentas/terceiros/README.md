# Ferramentas de terceiros (fora do git)

Estas pastas em `ferramentas\` são clones de outros repositórios, com ambientes Python e pesos de modelo
de dezenas de GB. Por isso ficam fora do git; aqui está o necessário para reinstalar e reaplicar as
nossas alterações.

| pasta | repositório | commit usado | para quê |
|---|---|---|---|
| `JoyVASA\` | https://github.com/jdh-algo/JoyVASA | `916a90f8` | traz o LivePortrait: boca falando (`visemas\boca.py`), recorte de rosto do fiscal e do revisor |
| `syncnet\` | https://github.com/joonson/syncnet_python | `907c0b57` | nota de sincronia boca↔áudio (`revisor\syncnet_lse.py`) |
| `MuseTalk\` | https://github.com/TMElyralab/MuseTalk | `0a89dec4` | **descartado** em 27/09/2026 (não funciona em rosto desenhado); guardado só como referência |

## JoyVASA (o mais importante)

```powershell
cd "F:\Projeto IA\ferramentas"
git clone https://github.com/jdh-algo/JoyVASA.git
cd JoyVASA
git checkout 916a90f8de490e8648fee460c1200bd5d9a795af
git apply ..\terceiros\joyvasa.patch
& "C:\Users\Filipe Pereira\AppData\Local\Programs\Python\Python311\python.exe" -m venv .venv
.venv\Scripts\python.exe -m pip install torch==2.2.2 torchvision --index-url https://download.pytorch.org/whl/cu121
.venv\Scripts\python.exe -m pip install -r requirements.txt
# pesos: siga o README do JoyVASA (pretrained_weights\: liveportrait, JoyVASA, chinese-hubert-base)
```

`joyvasa.patch` grava os quadros em streaming em `src\live_portrait_wmg_pipeline.py`: sem isso, áudios longos
estouram os 16 GB de RAM. Atenção: o OpenCV do JoyVASA não abre caminhos com acento.

## Outros componentes grandes (fora do git)

| o quê | onde | como recuperar |
|---|---|---|
| reconhecedor de fonemas (1,2 GB) | `visemas\modelos\wav2vec2-fonemas\` | `huggingface_hub.snapshot_download("facebook/wav2vec2-lv-60-espeak-cv-ft", local_dir=...)` |
| MediaPipe (teste de mãos, não usado) | `cenas\.venv_maos\` | `python -m venv` + `pip install mediapipe==0.10.14 opencv-python-headless` |
| juiz do fiscal | Ollama | `ollama pull qwen3-vl:4b` |
| klein no Kaggle | notebook `pandora-modelos` da conta | `cenas\kaggle\preparar.py` (roda uma vez) |

Segredos **nunca** vão para o git: token do Kaggle em `%USERPROFILE%\.kaggle\access_token`, chave do Gemini na
variável de usuário `GEMINI_API_KEY`, token do Hugging Face no cache do `huggingface_hub`.
