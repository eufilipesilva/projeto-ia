# -*- coding: utf-8 -*-
"""
TESTE 3: Impacto do num_ctx no tempo de resposta da Gemma
Roda com: python app/estudio/tools/teste_gemma_ctx.py
(Ollama precisa estar rodando com gemma3:4b carregado)

Testa se reduzir o num_ctx em chamadas curtas realmente acelera,
sem perder qualidade de output.
"""
import time, json, urllib.request

OLLAMA = "http://127.0.0.1:11434"
MODELO = "gemma3:4b"

def gemma(prompt, num_predict=60, num_ctx=2048, temperature=0):
    body = json.dumps({
        "model": MODELO, "prompt": prompt, "stream": False,
        "options": {"temperature": temperature, "num_predict": num_predict, "num_ctx": num_ctx}
    }).encode()
    req = urllib.request.Request(
        OLLAMA + "/api/generate", data=body,
        headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=120) as r:
        resp = json.loads(r.read())
    return resp["response"].strip(), round(time.time() - t0, 2)

def testar(nome, prompt, num_predict, ctxs, temperature=0):
    print(f"\n{'='*55}")
    print(f"CASO: {nome}")
    print(f"num_predict={num_predict}")
    print(f"{'='*55}")
    resultados = {}
    for ctx in ctxs:
        resp, t = gemma(prompt, num_predict, ctx, temperature)
        resultados[ctx] = (resp, t)
        print(f"  ctx={ctx:>5}: {t:.2f}s  =>  '{resp[:80]}'")
    # Compara com o maior ctx como referência
    ctx_ref = max(ctxs)
    ref_t = resultados[ctx_ref][1]
    print(f"\n  Ganho vs ctx={ctx_ref}:")
    for ctx in ctxs:
        if ctx != ctx_ref:
            ganho = ref_t / resultados[ctx][1]
            print(f"    ctx={ctx}: {ganho:.1f}x mais rápido")
    return resultados

# ── CASO 1: interpretar_descricao_voz (atualmente ctx=2048, output curto ~60 tokens) ──
PROMPT_VOZ = (
    "Translate this voice description into OmniVoice instruct attributes.\n"
    "You MUST use ONLY items from this exact list (copy them verbatim, comma-separated):\n"
    "female, male, child, teenager, young adult, middle-aged, elderly, "
    "low pitch, moderate pitch, high pitch, very high pitch, very low pitch, whisper, "
    "american accent, australian accent, british accent, canadian accent, "
    "chinese accent, indian accent, japanese accent, korean accent, "
    "portuguese accent, russian accent\n\n"
    "Do NOT invent new items. Choose the closest matching items from the list only.\n\n"
    "Voice description: mulher de meia idade, voz grave e tranquila\n\n"
    "Instruct (valid items only, comma-separated, no explanation):"
)
testar("interpretar_descricao_voz", PROMPT_VOZ, num_predict=60, ctxs=[512, 1024, 2048])

# ── CASO 2: classificação de emoção (ctx=2048, output 1 palavra ~20 tokens) ──
EMO_LISTA = ("alegria,tristeza,raiva,medo,surpresa,nojo,empolgacao,ternura,"
             "serenidade,confianca,ansiedade,frustracao,sarcasmo,curiosidade,"
             "melancolia,arrogancia,timidez,urgencia,neutra,suspenso,misterio")
PROMPT_EMO = (
    f"Qual a emoção de quem diz isso? (escolha uma):\n{EMO_LISTA}\n"
    "Frase: Obrigado por tudo que você fez por mim, nunca vou esquecer.\n\n"
    "Emoção (uma palavra):"
)
testar("responder_personagem — classificação de emoção", PROMPT_EMO, num_predict=20, ctxs=[512, 1024, 2048])

# ── CASO 3: _quem_fala_gemma (ctx=2048, output 1 nome ~12 tokens) ──
PROMPT_QUEM = (
    "Leia o trecho de uma história e diga QUEM pronuncia a fala marcada com '>>>'.\n"
    "Personagens já conhecidos: lobo, chapeuzinho, vovo, cacador.\n"
    "Responda só o nome curto do personagem, em uma palavra.\n\n"
    "narracao: Era uma tarde fria quando Chapeuzinho entrou na floresta.\n"
    "narracao: O lobo a observava de longe, sorrindo maliciosamente.\n"
    ">>> FALA: Que dentes grandes você tem, vovó!\n"
    "fala: Para te ver melhor, minha querida!\n\n"
    "Quem fala a linha marcada com >>>? Nome:"
)
testar("_quem_fala_gemma", PROMPT_QUEM, num_predict=12, ctxs=[512, 1024, 2048])

# ── CASO 4: gerar_meditacao — verifica se ctx=2048 trunca a saída ──
print(f"\n{'='*55}")
print("CASO: gerar_meditacao — num_ctx=2048 vs 4096")
print("(verifica truncamento — NÃO mede velocidade, mede tamanho da saída)")
print(f"{'='*55}")
PROMPT_MED = (
    "Escreva um script LONGO e COMPLETO de MEDITAÇÃO GUIADA sobre 'Floresta' "
    "para 5 minutos de duração.\n\n"
    "REGRAS: Frases MUITO CURTAS. NO MÍNIMO 20 frases. "
    "Após cada frase: [pausa 3s], [pausa 5s] ou [pausa 8s].\n\n"
    "Script:"
)
for ctx in [2048, 4096]:
    resp, t = gemma(PROMPT_MED, num_predict=1200, num_ctx=ctx, temperature=0.45)
    n_frases = resp.count("[pausa")
    n_chars = len(resp)
    print(f"  ctx={ctx}: {t:.1f}s | {n_chars} chars | {n_frases} pausas detectadas")
    if ctx == 2048 and n_frases < 15:
        print(f"  ! TRUNCADO! Só {n_frases} pausas — meditação incompleta com ctx=2048")
    elif n_frases >= 15:
        print(f"  OK OK — {n_frases} pausas, roteiro completo")

print("\nTeste concluído.")
