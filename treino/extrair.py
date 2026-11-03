# extrai a "linha de pixels" de várias colunas do vídeo (linhas 200-650)
import cv2,numpy as np,sys
cap=cv2.VideoCapture(sys.argv[1]); X=list(range(120,701,20)); out={x:[] for x in X}
while True:
    ok,f=cap.read()
    if not ok: break
    for x in X: out[x].append(f[200:650,x-3:x+3].mean(1).astype(np.uint8))
np.savez_compressed('colunas.npz',**{str(x):np.array(v) for x,v in out.items()})
print('ok',len(out[X[0]]))
