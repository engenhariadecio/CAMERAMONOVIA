# Monovia · Visão

Contagem da monovia por câmera de celular, rodando no Railway.

- **Peças por dia**, contadas pelo espaçamento entre as peças. Não identifica a peça.
- **Empilhamento**: quantas peças há em cada gancho, decidido pela IA.
- **Velocidade da monovia em m/s**, a partir do tempo entre troles.
- **Tempo funcionando e tempo parada.**

```
 Celular (navegador)                          Railway (este serviço)                 PostgreSQL
 ┌──────────────────────┐   WebSocket   ┌─────────────────────────────┐        ┌──────────────────┐
 │ /camera              │ ────────────▶ │ contador.py (troles, ganchos│ ─────▶ │ monovia_eventos  │
 │ filma e manda só a   │  ~15 linhas/s │ paradas) + IA empilhamento  │        │ monovia_ganchos  │
 │ LINHA DE PIXELS      │ ◀──────────── │ app.py (painel + API)       │        │ monovia_config   │
 └──────────────────────┘   números     └─────────────────────────────┘        └──────────────────┘
                                                        ▲  /api/resumo?dia=…
                                                        └── Banho e Monovia (lê os números do dia)
```

O vídeo não sai do celular. Ele manda só uma coluna de pixels por quadro, cerca de 1 KB. O servidor guarda uma miniatura de 128x32 de cada gancho para conferência, e essas miniaturas são apagadas depois de 30 dias.

---

## 1. Subir no GitHub e no Railway

1. **Crie um repositório no GitHub** (ex.: `monovia-visao`) e suba todo o conteúdo desta pasta.
2. **No Railway, abra o projeto do Banho e Monovia** e clique em **New → GitHub Repo → monovia-visao**. Isso cria um serviço separado, no mesmo projeto e no mesmo banco.
3. **Na aba Variables do serviço novo**, crie:
   | Variável | Valor |
   |---|---|
   | `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (referência ao Postgres que já existe; use o nome do seu serviço de banco) |
   | `MONOVIA_USUARIO` | usuário do administrador (ex.: `gustavo`) |
   | `MONOVIA_SENHA` | senha do administrador (forte) |
   | `MONOVIA_CHAVE_API` | (opcional) chave para o Banho e Monovia ler `/api/resumo` sem login |
   | `DIAS_IMAGENS` | `30` (opcional: por quantos dias guardar as miniaturas) |
4. **Em Settings → Networking → Generate Domain**, gere o domínio.
5. **Confira se está no ar** abrindo `https://SEU-DOMINIO/saude`. Deve aparecer `{"ok":true}`.

As tabelas `monovia_*` são criadas sozinhas e não mexem nas tabelas do Banho e Monovia.

## 2. Ligar o celular na monovia

1. **Prenda o celular num suporte fixo**, de frente para a monovia e ligado no carregador. Ele precisa enxergar o trilho com os troles e a altura toda do gancho. Um fundo liso atrás das peças (chapa ou lona) melhora muito a contagem.
2. **Abra o endereço da câmera** no Chrome (Android) ou no Safari (iPhone): `https://SEU-DOMINIO/camera`. Ele pede usuário e senha uma vez; depois o celular fica logado por 90 dias.
3. **Toque em Iniciar** e permita o uso da câmera.
4. **Toque em Calibrar e faça 3 toques na tela:**
   1. topo da peça mais alta, logo **abaixo da gancheira**, onde a linha deve passar;
   2. base da peça mais baixa;
   3. trilho, onde o trole passa.
5. **Espere um gancho vazio parar na linha vermelha** e toque em **Gravar fundo**. Leva 3 segundos.
6. **Deixe a página aberta, com a tela ligada.** Ela tenta manter a tela acesa sozinha. Se a página for fechada ou a tela apagar, a contagem para, e esse tempo aparece no painel como "câmera desligada", sem contar como parada.

Consumo de internet: cerca de 60 MB por hora. Prefira Wi-Fi.

## 2b. Usar a câmera do PC (webcam USB) em vez do celular

1. **Instale a webcam presa num suporte fixo**, de frente para a monovia, e ligue no PC.
2. **No PC, abra `https://SEU-DOMINIO/camera` no Chrome ou no Edge** e faça o login.
3. **Clique em Iniciar.** Em **Câmera → Qual câmera**, escolha a webcam da monovia; o PC lembra a escolha. Deixe a resolução em **1280 × 720**.
4. **Se aparecer "Travar foco e exposição", marque.** Assim a imagem não muda de brilho sozinha.
5. **Clique em Calibrar** e faça os 3 cliques na imagem (topo da peça mais alta, base da peça mais baixa, trilho). Uma lupa mostra o ponto aumentado 3×.
6. **Faça o ajuste fino, se precisar**, em **Ajuste fino da calibração**:
   - arraste as bolinhas e a linha na imagem;
   - ou use as setas do teclado com o mouse sobre a imagem (1 px; com Shift, 10 px);
   - ou digite os números.
   
   Depois clique em **Salvar calibração**.
7. **Com um gancho vazio na linha, clique em Gravar fundo.**
8. **Confira a linha de pixels.** O quadro **Linha de pixels** mostra o que a contagem enxerga: cada gancho vira um bloco, e o espaço entre as peças vira uma faixa.

No Chrome e no Edge a contagem **continua com a janela minimizada**. Para não parar:
- no Windows, desligue a suspensão do PC (**Configurações → Energia → Suspender: Nunca**);
- no navegador, adicione o site em **Configurações → Desempenho → Sempre manter estes sites ativos**.

Na próxima vez que abrir a página, a câmera liga sozinha.

## 3. Painel

Endereço: `https://SEU-DOMINIO/`, com o mesmo login.

- **Usuários:** o administrador cadastra e apaga usuários no fim do painel. Para trocar a senha de alguém, salve o mesmo usuário com a senha nova.

- Mostra peças, velocidade, tempo funcionando e parado, peças por hora, distribuição do empilhamento e lista de paradas.
- **Configuração:** informe a **distância entre troles (m)**, medida com trena de centro a centro. É com ela que a velocidade é calculada: velocidade = distância ÷ tempo entre troles.
- **Conferência dos ganchos:** cada quadro mostra o que a linha viu na passagem de um gancho. Se a contagem estiver errada, toque no número certo. Isso corrige o total do dia e vira exemplo para treinar a IA de novo. Os quadros com borda amarela são os duvidosos: a IA ficou insegura ou discordou da regra simples.

## 4. Ligar no Banho e Monovia

As duas opções abaixo funcionam.

**Pela API:**
```
GET https://SEU-DOMINIO/api/resumo?dia=2026-10-30      (cabeçalho  X-Chave: <MONOVIA_CHAVE_API>)
→ {"pecas": 2480, "ganchos": 1240, "velocidade_media_m_s": 0.0264, "tempo_funcionando_s": 30120,
   "tempo_parado_s": 2410, "paradas": [...], "por_hora": [...], "empilhamento": [...]}
```

**Direto no banco** (mesmo Postgres). As datas estão em texto, no horário de Brasília:
```sql
-- peças do dia (já com as correções feitas no painel)
SELECT SUM(COALESCE(rotulo, empilhamento)) FROM monovia_ganchos WHERE datahora LIKE '2026-10-30%';
-- tempo parado do dia (s)
SELECT SUM(valor) FROM monovia_eventos WHERE tipo = 'PARADA' AND datahora LIKE '2026-10-30%';
```

## 5. A IA (modelo de empilhamento)

- **O que é:** `modelo_empilhamento.onnx`, uma rede neural pequena (110 mil parâmetros, 440 KB) que roda no processador do Railway em milissegundos.
- **Como decide:** olha o bloco de pixels do gancho (altura × tempo) mais o fundo gravado e marca, linha a linha da altura, se é **peça** ou **espaço**. As peças são contadas pelos espaços. Ela não reconhece o tipo de peça.
- **Treino (v1):**
  - 63 mil exemplos sintéticos com peças de qualquer cor e tamanho, peças vazadas e perfuradas, barras finas, de 0 a 8 por gancho, peças girando e balançando, fundos reais e lisos;
  - 15 mil exemplos de "camuflagem": peça cinza sobre fundo cinza, com espaço estreito;
  - 223 ganchos reais do vídeo da monovia;
  - um ajuste fino em que a câmera mexe até 3 px depois de gravar o fundo.
- **Ao lado da IA** roda uma regra simples. Quando as duas discordam, o gancho vai para os "duvidosos" do painel.

### Resultados medidos (vídeo de teste de 4 min)

| O quê | Resultado |
|---|---|
| Ganchos detectados (quantidade) | 6 de 6 |
| Troles (velocidade) | 20 de 20; intervalo 11,4 s ± 0,1 s |
| Parada simulada de 60 s | medida 59–60 s |
| Empilhamento com a câmera parada | 7 de 7 ganchos certos (simulador + navegador) |
| Empilhamento depois que a câmera escorregou 4–5 px | 1 de 3 certos pelo simulador. O painel e o celular avisam "câmera mexeu" |
| Empilhamento em colunas que não entraram no treino | 46 de 54 (85%) |
| Empilhamento em peças sintéticas variadas (validação) | 96% |

**Isto ainda não é 100%.** O que leva para perto disso:

1. **Celular bem preso.** Se ele mexer, grave o fundo de novo.
2. **Fundo liso atrás da monovia** (chapa ou lona). Tira a camuflagem e os objetos que passam ao fundo, e permite baixar a sensibilidade para pegar peças pequenas.
3. **Conferir os duvidosos no painel e treinar de novo** com os ganchos da sua linha (passo a passo abaixo). Cada lote conferido deixa a IA mais acostumada com as suas peças.

**Sensibilidade (painel):** é a porcentagem da altura que precisa mudar para abrir um gancho. O padrão é 20%. Menor pega peças pequenas, mas também pega coisas passando ao fundo; com o fundo liso dá para usar 5 a 10%.

### Treinar de novo com os ganchos conferidos (no PC)

```
pip install torch numpy opencv-python onnx
cd treino
python extrair.py video.mp4                        # fundos e texturas reais (use o vídeo de 4 min da monovia que gerou o modelo)
python gerar.py 20000 sint_a.npz                  # exemplos sintéticos
python gerar.py 20000 sint_b.npz
# no painel: "Baixar ganchos conferidos" -> rotulados_real_AAAAMMDD.npz (deixe "real" no nome)
CAMUF=1 python gerar.py 15000 sint_c.npz            # casos de camuflagem
python treinar.py sint_a.npz sint_b.npz sint_c.npz rotulados_real_AAAAMMDD.npz --peso-real 10 --saida ../modelo_empilhamento.onnx
# ou ajuste fino rápido em cima do modelo atual (precisa do .pt):
# python treinar.py ... --inicio modelo_empilhamento.pt --lr 8e-4 --epocas 2 --saida ../modelo_empilhamento.onnx
```

Depois faça commit e push do novo `modelo_empilhamento.onnx`. O Railway publica sozinho.

## 6. Testar sem ir à linha

```
pip install -r requirements.txt websockets opencv-python
MONOVIA_USUARIO=admin MONOVIA_SENHA=teste123 uvicorn app:app --port 8000   # usa SQLite local se não houver DATABASE_URL
python teste/simular_celular.py video.mp4 http://localhost:8000 --usuario admin --senha teste123 \
       --x 380 --y0 280 --y1 600 --ry 100 --passo 0.30 --fundo-em 10.5
```

## Segurança (para o TI)

- **Acesso:** usuário e senha. As senhas são guardadas com hash PBKDF2 (200 mil iterações), e a sessão fica num cookie assinado com HttpOnly e Secure. Depois de 8 senhas erradas em 10 minutos, o login trava por IP. Tudo passa por HTTPS ou WSS, que o Railway fornece.
- **Usuário apagado** perde o acesso na hora.
- **O que trafega:** uma coluna de pixels por quadro. Nenhum vídeo é gravado.
- **O que fica no banco:** contagens, eventos e miniaturas de 128x32 dos ganchos, apagadas depois de `DIAS_IMAGENS` dias.
- **Banco:** o mesmo PostgreSQL do Banho e Monovia, em tabelas próprias (`monovia_*`).
