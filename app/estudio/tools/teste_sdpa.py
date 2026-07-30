# -*- coding: utf-8 -*-
"""
TESTE 2: OmniVoice com attn_implementation="sdpa" vs padrão
Roda com: python app/estudio/tools/teste_sdpa.py
(dentro do venv_omni, com servidor PARADO)

SDPA = Scaled Dot-Product Attention do PyTorch 2.x
É embutido no PyTorch, sem instalar nada extra.
Potencial de 15-30% de ganho na atenção do transformer interno.
"""
import sys, os, time, gc
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import torch
import motor_v2 as motor

VOZ_REF = os.path.join(os.path.dirname(__file__), "..", "vozes", "Dora (PT-F).wav")
TEXTO_TESTE = "Respire fundo, relaxe os ombros, e sinta a calma se espalhando pelo seu corpo."

def medir(label, attn_impl=None):
    from omnivoice import OmniVoice, OmniVoiceGenerationConfig
    kwargs = dict(
        device_map="auto",
        dtype=torch.float16,
        load_asr=False,
        token=False,
    )
    if attn_impl:
        kwargs["attn_implementation"] = attn_impl

    print(f"\n{'='*50}")
    print(f"  {label}")
    print(f"{'='*50}")
    t_load = time.time()
    try:
        model = OmniVoice.from_pretrained("k2-fsa/OmniVoice", **kwargs)
        print(f"  Carregado em {time.time()-t_load:.1f}s")
    except Exception as e:
        print(f"  ERRO ao carregar: {e}")
        return None

    perfil = motor.perfil_voz(VOZ_REF)
    prompt = motor._criar_prompt_voz(model, perfil)
    cfg = OmniVoiceGenerationConfig(num_step=32, guidance_scale=3.0,
                                     class_temperature=0.0, postprocess_output=False)

    # Warmup (1 frase — descartada)
    _ = model.generate(motor._com_ponto("Teste."), language="pt",
                        voice_clone_prompt=prompt, generation_config=cfg)

    # Medição real (3 gerações — média)
    tempos = []
    for i in range(3):
        torch.cuda.synchronize()
        t0 = time.time()
        wav = model.generate(motor._com_ponto(TEXTO_TESTE), language="pt",
                              voice_clone_prompt=prompt, generation_config=cfg)[0]
        torch.cuda.synchronize()
        tempos.append(time.time() - t0)
        print(f"  Run {i+1}: {tempos[-1]:.2f}s")

    media = sum(tempos) / len(tempos)
    print(f"  Média: {media:.2f}s")

    del model; gc.collect(); torch.cuda.empty_cache()
    return media

print("PyTorch:", torch.__version__)
print("CUDA disponível:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("GPU:", torch.cuda.get_device_name(0))
    print("VRAM total:", round(torch.cuda.get_device_properties(0).total_memory / 1e9, 1), "GB")

t_padrao = medir("PADRÃO (attn automático — modo atual)")
t_sdpa   = medir("SDPA (scaled dot-product attention)", attn_impl="sdpa")

if t_padrao and t_sdpa:
    ganho = t_padrao / t_sdpa
    print(f"\n{'='*50}")
    print(f"RESULTADO FINAL:")
    print(f"  Padrão: {t_padrao:.2f}s por frase")
    print(f"  SDPA:   {t_sdpa:.2f}s por frase")
    if ganho > 1.05:
        print(f"  ✓ SDPA é {ganho:.2f}x mais rápido — vale implementar!")
    elif ganho < 0.95:
        print(f"  ✗ SDPA ficou mais lento ({ganho:.2f}x) — NÃO implementar.")
    else:
        print(f"  = Sem diferença significativa ({ganho:.2f}x) — opcional.")
