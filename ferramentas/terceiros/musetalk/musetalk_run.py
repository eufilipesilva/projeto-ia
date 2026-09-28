"""MuseTalk 1.5 sem mmpose: recebe a caixa do rosto pronta (bbox_musetalk.py) e grava o vídeo direto.
Adaptado de scripts/inference.py. Rodar a partir desta pasta, com o .venv do MuseTalk.

    python musetalk_run.py --src IMAGEM_OU_VIDEO --audio AUDIO.wav --bbox CAIXAS.pkl --out SAIDA.mp4
        [--fps 25] [--float16] [--extra-margin 10] [--parsing-mode jaw]
"""
import argparse, copy, os, pickle, subprocess, sys
from pathlib import Path

AQUI = Path(__file__).parent
os.chdir(AQUI); sys.path.insert(0, str(AQUI))

import cv2
import numpy as np
import torch
from tqdm import tqdm
from transformers import WhisperModel

from musetalk.utils.blending import get_image
from musetalk.utils.face_parsing import FaceParsing
from musetalk.utils.audio_processor import AudioProcessor
from musetalk.utils.utils import datagen


def ler_quadros_bgr(src):
    p = Path(src)
    if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
        return [cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)], None
    cap = cv2.VideoCapture(str(p)); fps = cap.get(cv2.CAP_PROP_FPS); fr = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        fr.append(f)
    return fr, fps


def carregar_modelos(dev):
    """Carrega o MuseTalk cabendo em 16 GB de RAM e 6 GB de VRAM: UNet montada vazia (meta), pesos
    mapeados do disco (mmap) e convertidos para fp16 direto na GPU, camada a camada."""
    import json
    from types import SimpleNamespace
    from diffusers import UNet2DConditionModel
    from musetalk.models.unet import PositionalEncoding
    from musetalk.models.vae import VAE
    with torch.device("meta"):
        m = UNet2DConditionModel(**json.load(open("models/musetalkV15/musetalk.json")))
    m.load_state_dict(torch.load("models/musetalkV15/unet.pth", map_location="cpu", mmap=True), assign=True)
    for mod in m.modules():
        for k, v in list(mod._parameters.items()):
            if v is not None:
                mod._parameters[k] = torch.nn.Parameter(v.data.to(dev, torch.float16), requires_grad=False)
        for k, v in list(mod._buffers.items()):
            if v is not None:
                mod._buffers[k] = v.to(dev, torch.float16 if v.is_floating_point() else v.dtype)
    vae = VAE(model_path="models/sd-vae")
    vae.vae = vae.vae.half().to(dev)
    return SimpleNamespace(model=m.eval()), vae, PositionalEncoding(d_model=384).half().to(dev)


@torch.no_grad()
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True); ap.add_argument("--audio", required=True)
    ap.add_argument("--bbox", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--fps", type=float, default=25); ap.add_argument("--float16", action="store_true")
    ap.add_argument("--extra-margin", type=int, default=10); ap.add_argument("--parsing-mode", default="jaw")
    ap.add_argument("--batch", type=int, default=8)
    a = ap.parse_args()
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    unet, vae, pe = carregar_modelos(dev)
    ap_ = AudioProcessor(feature_extractor_path="models/whisper")
    dtype = unet.model.dtype
    whisper = WhisperModel.from_pretrained("models/whisper").to(device=dev, dtype=dtype).eval()
    fp = FaceParsing(left_cheek_width=90, right_cheek_width=90)

    frames, fps_v = ler_quadros_bgr(a.src)
    frames = [f[: f.shape[0] // 2 * 2, : f.shape[1] // 2 * 2] for f in frames]  # yuv420p exige lados pares
    fps = fps_v or a.fps
    coords = pickle.load(open(a.bbox, "rb"))
    assert len(coords) == len(frames), f"{len(coords)} caixas para {len(frames)} quadros"

    feats, n_audio = ap_.get_audio_feature(a.audio)
    chunks = ap_.get_whisper_chunk(feats, dev, dtype, whisper, n_audio, fps=fps,
                                   audio_padding_length_left=2, audio_padding_length_right=2)

    latentes = []
    for (x1, y1, x2, y2), f in zip(coords, frames):
        y2 = min(y2 + a.extra_margin, f.shape[0])
        crop = cv2.resize(f[y1:y2, x1:x2], (256, 256), interpolation=cv2.INTER_LANCZOS4)
        latentes.append(vae.get_latents_for_unet(crop))
    fr_ciclo, co_ciclo, la_ciclo = frames + frames[::-1], coords + coords[::-1], latentes + latentes[::-1]

    h, w = frames[0].shape[:2]
    tmp = str(Path(a.out).with_suffix(".sem_audio.mp4"))
    ff = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}",
                           "-r", str(fps), "-i", "-", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", tmp],
                          stdin=subprocess.PIPE)
    gen = datagen(whisper_chunks=chunks, vae_encode_latents=la_ciclo, batch_size=a.batch, delay_frame=0, device=dev)
    i = 0
    for wb, lb in tqdm(gen, total=int(np.ceil(len(chunks) / a.batch))):
        pred = unet.model(lb.to(dtype=dtype), torch.tensor([0], device=dev),
                          encoder_hidden_states=pe(wb)).sample
        for res in vae.decode_latents(pred):
            x1, y1, x2, y2 = co_ciclo[i % len(co_ciclo)]
            ori = copy.deepcopy(fr_ciclo[i % len(fr_ciclo)])
            y2 = min(y2 + a.extra_margin, ori.shape[0])
            res = cv2.resize(res.astype(np.uint8), (x2 - x1, y2 - y1))
            ff.stdin.write(get_image(ori, res, [x1, y1, x2, y2], mode=a.parsing_mode, fp=fp).tobytes())
            i += 1
    ff.stdin.close(); ff.wait()
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", tmp, "-i", a.audio, "-c:v", "copy", "-c:a", "aac",
                    "-shortest", a.out], check=True)
    os.remove(tmp)
    print("pronto:", a.out, f"({i} quadros)")


if __name__ == "__main__":
    main()
