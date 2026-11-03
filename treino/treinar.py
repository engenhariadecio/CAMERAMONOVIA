"""
Treina o modelo de empilhamento.
  python treinar.py sint_a.npz sint_b.npz [rotulados_reais.npz ...] --saida modelo_empilhamento.onnx
Os .npz reais vêm do botão "Exportar rótulos" do painel (mesmo formato: B, G, Y, K).
"""
import argparse, numpy as np, torch, torch.nn as nn, time
from modelo import Rede, entrada, contar

ap = argparse.ArgumentParser()
ap.add_argument('dados', nargs='+')
ap.add_argument('--epocas', type=int, default=10)
ap.add_argument('--saida', default='modelo_empilhamento.onnx')
ap.add_argument('--peso-real', type=int, default=20, help='repete as amostras reais N vezes')
ap.add_argument('--inicio', default=None, help='continua de um modelo .pt (ajuste fino)')
ap.add_argument('--lr', type=float, default=3e-3)
ap.add_argument('--desloc-fundo', type=int, default=3, help='desloca o fundo até N linhas (câmera que mexe)')
a = ap.parse_args()
torch.manual_seed(0); np.random.seed(0)

B, G, Y, K = [], [], [], []
for f in a.dados:
    d = np.load(f); rep = a.peso_real if 'Y' in d and 'real' in f else 1
    for _ in range(rep):
        B.append(d['B']); G.append(d['G']); Y.append(d['Y']); K.append(d['K'])
B, G, Y, K = map(np.concatenate, (B, G, Y, K))
idx = np.random.permutation(len(B)); nv = min(2000, len(B) // 10)
va, tr = idx[:nv], idx[nv:]
print('amostras treino', len(tr), 'validação', len(va), flush=True)

net = Rede()
if a.inicio: net.load_state_dict(torch.load(a.inicio))
opt = torch.optim.AdamW(net.parameters(), 2e-3, weight_decay=1e-4)
sched = torch.optim.lr_scheduler.OneCycleLR(opt, a.lr, total_steps=a.epocas * (len(tr) // 128 + 1))
lossf = nn.BCEWithLogitsLoss()

def avaliar(ids):
    net.eval(); ok = 0; acc = 0
    with torch.no_grad():
        for i in range(0, len(ids), 512):
            j = ids[i:i + 512]
            p = torch.sigmoid(net(torch.from_numpy(entrada(B[j], G[j])))).numpy()
            acc += ((p > 0.5) == (Y[j] > 0)).mean() * len(j)
            ok += sum(contar(pp) == k for pp, k in zip(p, K[j]))
    net.train(); return acc / len(ids), ok / len(ids)

for ep in range(a.epocas):
    t0 = time.time(); np.random.shuffle(tr); L = 0
    for i in range(0, len(tr), 128):
        j = tr[i:i + 128]
        bb, gg = B[j].copy(), G[j]
        if np.random.rand() < 0.5: bb = bb[:, :, ::-1]                       # sentido da monovia
        if a.desloc_fundo and np.random.rand() < 0.5:                         # câmera mexeu um pouco depois de gravar o fundo
            gg = np.roll(gg, np.random.randint(-a.desloc_fundo, a.desloc_fundo + 1), axis=1)
        x = torch.from_numpy(entrada(bb, gg)); y = torch.from_numpy(Y[j].astype(np.float32))
        loss = lossf(net(x), y); opt.zero_grad(); loss.backward(); opt.step(); sched.step(); L += loss.item() * len(j)
    acc, cnt = avaliar(va)
    txt = ''
    for f in ('teste_real2.npz', 'teste_real_sb_sep.npz'):               # ganchos reais de colunas que NÃO entram no treino
        try:
            d = np.load(f); net.eval()
            with torch.no_grad(): p = torch.sigmoid(net(torch.from_numpy(entrada(d['B'], d['G'])))).numpy()
            net.train(); txt += f'  real[{f[:-4]}] {sum(contar(pp) == k for pp, k in zip(p, d["K"]))}/{len(p)}'
        except FileNotFoundError: pass
    torch.save(net.state_dict(), a.saida.replace('.onnx', f'_ep{ep + 1}.pt'))
    print(f'época {ep + 1}: perda {L / len(tr):.4f}  acerto por linha {acc:.4f}  acerto da contagem {cnt:.4f}{txt}  ({time.time() - t0:.0f}s)', flush=True)

torch.save(net.state_dict(), a.saida.replace('.onnx', '.pt'))
net.eval()
torch.onnx.export(net, torch.zeros(1, 7, 128, 32), a.saida, input_names=['x'], output_names=['logit'],
                  dynamic_axes={'x': {0: 'n'}, 'logit': {0: 'n'}}, opset_version=17, dynamo=False)
print('salvo', a.saida)
