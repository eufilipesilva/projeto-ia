"""Roda NO KAGGLE, uma vez só (sem GPU): baixa o FLUX.2 klein 4B para a saída deste notebook, que fica
guardada na conta. O gerador monta essa saída (kernel_sources) e não precisa baixar nada a cada rodada."""
from huggingface_hub import snapshot_download
p = snapshot_download("black-forest-labs/FLUX.2-klein-4B", local_dir="/kaggle/working/klein",
                      allow_patterns=["model_index.json", "scheduler/*", "text_encoder/*", "tokenizer/*",
                                      "transformer/*", "vae/*"])
import os
total = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(p) for f in fs)
print(f"klein guardado em {p}: {total / 1e9:.1f} GB")
