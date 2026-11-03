import numpy as np, torch, sys
from modelo import Rede, entrada
sd = [torch.load(f'modelo_empilhamento_ep{e}.pt') for e in (6, 7, 8)]
med = {k: (sum(s[k].float() for s in sd) / len(sd)).to(sd[0][k].dtype) for k in sd[0]}
net = Rede(); net.load_state_dict(med)
# recalibra a BatchNorm com dados de treino (sintético + real de treino)
for m in net.modules():
    if isinstance(m, torch.nn.BatchNorm2d): m.reset_running_stats(); m.momentum = None
net.train()
X = []
for f in ('sint_a.npz', 'sint_c1.npz', 'real_treino2.npz'):
    d = np.load(f); n = min(3000, len(d['B'])); X.append((d['B'][:n], d['G'][:n]))
with torch.no_grad():
    for B, G in X:
        for i in range(0, len(B), 256): net(torch.from_numpy(entrada(B[i:i+256], G[i:i+256])))
net.eval(); torch.save(net.state_dict(), 'modelo_empilhamento_media.pt')
torch.onnx.export(net, torch.zeros(1, 7, 128, 32), 'modelo_empilhamento_media.onnx', input_names=['x'], output_names=['logit'],
                  dynamic_axes={'x': {0: 'n'}, 'logit': {0: 'n'}}, opset_version=17, dynamo=False)
print('ok')
