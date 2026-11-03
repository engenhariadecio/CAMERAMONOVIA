"""
Gera blocos de treino para o modelo de empilhamento.
Cada amostra = o que a "linha de pixels" vê durante a passagem de UM gancho:
  bloco (R linhas x T tempos x 3 cores), fundo calibrado (R x 3), rótulo por linha (1 = peça, 0 = espaço/fundo).
"""
import numpy as np, cv2

R, T = 128, 32
rng = np.random.default_rng()
import os
CAMUF = float(os.environ.get('CAMUF', '0'))   # fração de amostras no modo camuflagem (peça cinza grande sobre fundo cinza)

C = np.load('colunas.npz'); COLS = {int(k): C[k] for k in C.files}   # T x 450 x 3 (linhas 200-650 do quadro)
FPS = 30

# ---- fundos reais: janela de 15 s mais "parada" de cada coluna ----
FUNDOS = []
for x, S in COLS.items():
    g = S.mean(2)
    best = None
    for t0 in range(0, len(S) - 450, 60):
        sd = g[t0:t0 + 450, 60:420].std(0).mean()
        if best is None or sd < best[0]: best = (sd, t0)
    if best[0] < 6:
        FUNDOS.append(np.median(S[best[1]:best[1] + 450], axis=0).astype(np.float32))
# ---- texturas reais de peça (coluna 380 e vizinhas, ganchos conferidos) ----
GANCHOS = [(18.9, 41.9), (52.8, 76.1), (87.3, 110.8), (120.9, 144.1), (188.0, 201.7), (211.1, 224.7)]
TEXT = []
for x in (360, 380, 400):
    S = COLS[x].astype(np.float32)
    for a, b in GANCHOS:
        blk = S[int(a * FPS) + 10:int(b * FPS) - 10]          # tempo x linhas x 3
        TEXT.append(blk[:, 122:214].transpose(1, 0, 2))       # peça de cima (sem bordas)
        TEXT.append(blk[:, 252:380].transpose(1, 0, 2))       # peça de baixo
TEXT = [t for t in TEXT if (t[..., 0] - t[..., 2]).mean() < 8]   # tira recortes com o pilar azul na frente

def fundo_sintetico(n, real=False):
    r = 0.0 if real else rng.random()
    if r < 0.5 and FUNDOS:                        # fundo real de fábrica
        F = FUNDOS[rng.integers(len(FUNDOS))]
        span = rng.integers(160, 440); y = rng.integers(0, 450 - span + 1)
        bg = cv2.resize(F[y:y + span][:, None], (1, n), interpolation=cv2.INTER_LINEAR)[:, 0]
        if rng.random() < 0.5: bg = bg[::-1]
        return bg
    if r < 0.8:                                   # faixas aleatórias (inclui cinza parecido com peça)
        k = rng.integers(3, 14); cuts = np.sort(rng.integers(0, n, k)); bg = np.zeros((n, 3), np.float32)
        prev = 0
        for c in list(cuts) + [n]:
            base = rng.uniform(10, 230); tint = rng.normal(0, 12, 3)
            bg[prev:c] = np.clip(base + tint, 0, 255); prev = c
        return cv2.GaussianBlur(bg[:, None], (1, 5), 0)[:, 0]
    # fundo liso (chapa/lona pintada atrás da monovia)
    cor = [(235, 235, 235), (200, 120, 40), (60, 160, 60), (200, 200, 200), (40, 40, 40)][rng.integers(5)]
    grad = np.linspace(-15, 15, n)[:, None] * rng.uniform(-1, 1)
    return np.clip(np.array(cor, np.float32)[None] + grad, 0, 255)

def cor_qualquer():
    """peça crua (cinza/galvanizada) ou já pintada de qualquer cor"""
    if rng.random() < 0.5: return np.full(3, rng.uniform(40, 220)) + rng.normal(0, 6, 3)
    hsv = np.uint8([[[rng.integers(0, 180), rng.integers(30, 256), rng.integers(30, 250)]]])
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)[0, 0].astype(np.float32)

def textura_peca(h, L, real=False):
    r = 0.0 if real else rng.random()
    if r < 0.3 and TEXT:                                            # textura real (aço do vídeo), às vezes tingida
        P = TEXT[rng.integers(len(TEXT))]
        tx = cv2.resize(P, (L, h), interpolation=cv2.INTER_LINEAR)
        if rng.random() < 0.5: tx = tx[:, ::-1]
        if rng.random() < 0.4 and not real: tx = tx * rng.uniform(0.6, 1.4, 3)
    else:                                                           # qualquer peça: cor lisa, brilho metálico, riscos
        tx = np.zeros((h, L, 3), np.float32) + cor_qualquer()
        if rng.random() < 0.5:                                      # reflexo/gradiente metálico
            tx += (np.linspace(-1, 1, h)[:, None, None] * rng.uniform(-40, 40)
                   + np.sin(np.linspace(0, rng.uniform(1, 12), L))[None, :, None] * rng.uniform(0, 25))
        for _ in range(rng.integers(0, 5)):                         # dobras, frisos, etiquetas
            yy = rng.integers(0, h); tx[yy:yy + rng.integers(1, 4)] += rng.uniform(-60, 60)
        if rng.random() < 0.25:                                     # chapa perfurada (furos pequenos)
            pas = rng.integers(3, 8)
            tx[::pas, ::pas] *= rng.uniform(0.2, 0.7)
        tx += rng.normal(0, rng.uniform(1, 6), tx.shape)
    tx = tx * rng.uniform(0.7, 1.3) + rng.uniform(-25, 25)
    b = max(1, h // rng.integers(10, 40))                           # borda da peça (dobra)
    tx[:b] += rng.uniform(-60, 40); tx[-b:] += rng.uniform(-70, 30)
    return np.clip(tx, 0, 255)

def amostra():
    n = 256; L = int(rng.integers(40, 220))
    camuf = rng.random() < CAMUF
    bg = fundo_sintetico(n, real=camuf)
    bgfull = np.repeat(bg[:, None], L, axis=1)
    blk = bgfull.copy()
    lab = np.zeros((n, L), np.float32)
    k = rng.choice(np.arange(9), p=[0.07, 0.19, 0.25, 0.17, 0.12, 0.08, 0.05, 0.04, 0.03]) if not camuf else rng.choice([1, 2, 3], p=[0.25, 0.5, 0.25])
    tt = np.arange(L, dtype=np.float32)
    if k:
        alt_tot = rng.uniform(0.35, 0.97) * n if not camuf else rng.uniform(0.8, 0.98) * n
        gaps = np.array([rng.choice([rng.uniform(2, 6), rng.uniform(6, 25), rng.uniform(25, 70)], p=[0.3, 0.5, 0.2]) if not camuf else rng.uniform(4, 24) for _ in range(k - 1)])
        hs = rng.dirichlet(np.ones(k) * rng.uniform(0.7, 3)) * max(alt_tot - gaps.sum(), k * 10)
        fina = (rng.random(k) < 0.15) & (not camuf)                                 # barras/perfis finos
        hs = np.where(fina, rng.uniform(8, 18, k), np.maximum(hs, 10))
        esc = min(1.0, (n - 2) / (hs.sum() + gaps.sum()))           # garante que cabe
        hs, gaps = hs * esc, gaps * esc
        y = rng.uniform(0, max(1, n - hs.sum() - gaps.sum()))
        # o gancho inteiro balança/inclina junto (corpo rígido); o deslocamento não passa do menor espaço
        dmax = 0.6 * gaps.min() if k > 1 else 30.0
        bal_a = rng.uniform(0, 0.5 * dmax) if rng.random() < 0.6 else 0.0
        bal_f = rng.uniform(0.5, 3)
        incl = rng.uniform(-1, 1) * (dmax - bal_a) / (L / 2) if rng.random() < 0.6 else 0.0
        for i in range(k):
            h = max(4, int(hs[i])); tx = textura_peca(h, L, camuf)
            if rng.random() < 0.15:                                  # peça estreita (passa pouco tempo na linha)
                larg = rng.uniform(0.2, 0.5); ta = int(rng.uniform(0, 1 - larg) * L); tb = int(ta + larg * L)
            else:
                ta = int(rng.uniform(0, 0.25) * L) if rng.random() < 0.4 else 0
                tb = L - (int(rng.uniform(0, 0.25) * L) if rng.random() < 0.4 else 0)
            y0t = y + incl * (tt - L / 2) + bal_a * np.sin(bal_f * 2 * np.pi * tt / L)
            my = (np.arange(n, dtype=np.float32)[:, None] - y0t[None, :]).astype(np.float32)
            mx = np.repeat(tt[None, :], n, axis=0)
            dentro = (my >= 0) & (my < h - 1) & (mx >= ta) & (mx < tb)
            for _ in range(6):                                      # peça tem que ser visível contra o fundo
                pec = cv2.remap(tx.astype(np.float32), mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
                if not dentro.any() or np.abs(pec[dentro] - bgfull[dentro]).max(-1).mean() >= (12 if camuf else 30): break
                tx = textura_peca(h, L, camuf)
            blk[dentro] = pec[dentro]; lab[dentro] = 1
            if h > 30 and rng.random() < 0.25:                       # peça vazada (quadro/janela): o fundo aparece
                hy0 = rng.uniform(0.12, 0.4) * h; hy1 = h - rng.uniform(0.12, 0.4) * h  # pelo meio, mas continua UMA peça
                w = tb - ta; wa = ta + rng.uniform(0.12, 0.3) * w; wb = tb - rng.uniform(0.12, 0.3) * w
                furo = dentro & (my >= hy0) & (my < hy1) & (mx >= wa) & (mx < wb)
                blk[furo] = bgfull[furo]
            y += h + (gaps[i] if i < k - 1 else 0)
            if i < k - 1 and rng.random() < 0.3:                     # sombra no espaço entre peças
                yy = int(y - gaps[i] / 2); blk[yy:yy + 2] *= 0.5
    for _ in range(rng.integers(0, 3) if rng.random() < 0.4 else 0):  # ganchos/arames finos (não são peça)
        t0 = rng.integers(0, L); w = max(1, int(L * rng.uniform(0.01, 0.04)))
        a0 = rng.integers(0, n - 10); a1 = min(n, a0 + int(n * rng.uniform(0.05, 0.4)))
        blk[a0:a1, t0:t0 + w] = rng.uniform(15, 90)
    if rng.random() < 0.15:                                           # sombra/variação de luz passando
        s0 = rng.integers(0, L); blk[:, s0:s0 + int(L * 0.3)] *= rng.uniform(0.75, 0.95)
    blk = blk * rng.uniform(0.85, 1.15) + rng.uniform(-12, 12) + rng.normal(0, rng.uniform(1, 5), blk.shape)
    bgc = bg + rng.normal(0, 2, bg.shape)
    if rng.random() < 0.3: blk = cv2.GaussianBlur(blk, (1, 3), 0)
    blk = np.clip(blk, 0, 255)
    # rótulo da linha: é peça se a peça ocupa >= 12% do tempo naquela altura (furo da peça vazada conta como peça)
    y_lab = (lab.mean(1) >= 0.12).astype(np.float32)
    return redimensionar(blk, bgc, y_lab), contar(y_lab)

def redimensionar(blk, bg, y_lab=None):
    b = cv2.resize(blk.astype(np.float32), (T, R), interpolation=cv2.INTER_AREA)
    g = cv2.resize(bg.astype(np.float32)[:, None], (1, R), interpolation=cv2.INTER_AREA)[:, 0]
    out = (b.astype(np.uint8), g.astype(np.uint8))
    if y_lab is not None:
        yl = cv2.resize(y_lab[:, None], (1, R), interpolation=cv2.INTER_AREA)[:, 0]
        out = out + ((yl >= 0.5).astype(np.uint8),)
    return out

def contar(y, minimo=4):
    y = np.asarray(y) > 0.5; n, c = 0, 0
    for v in list(y) + [False]:
        if v: c += 1
        else:
            if c >= minimo: n += 1
            c = 0
    return n

if __name__ == '__main__':
    import sys
    N = int(sys.argv[1]); B, G, Y, K = [], [], [], []
    for i in range(N):
        (b, g, y), k = amostra()
        if contar(y) != k: k = contar(y)
        B.append(b); G.append(g); Y.append(y); K.append(k)
    np.savez_compressed(sys.argv[2], B=np.array(B), G=np.array(G), Y=np.array(Y), K=np.array(K))
    print('fundos reais:', len(FUNDOS), 'texturas:', len(TEXT), 'contagens:', np.bincount(K))
