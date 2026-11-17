# Controle de Slides por Gestos

Miniprojeto de Processamento Digital de Imagem (Unicap, Prof. Robson Lins).
Tema 7: Reconhecimento de Gestos.

O sistema reconhece gestos corporais pela webcam, em tempo real, e controla
uma apresentacao (PowerPoint, Google Slides ou qualquer app que aceite as
setas do teclado).

| Gesto | Acao | Tecla enviada |
|---|---|---|
| Braco direito esticado para cima | Proximo slide | seta direita |
| Braco esquerdo esticado para cima | Slide anterior | seta esquerda |
| Duas maos na cabeca | Tela preta / voltar | B |

## Como funciona

1. **Captura**: OpenCV le a webcam (640x480).
2. **Deteccao de pose**: MediaPipe Pose Landmarker (rede neural em dois
   estagios: detector de pessoa + regressor de 33 pontos do corpo).
3. **Calibracao**: 30 frames em posicao neutra definem a altura base de
   ombros e quadril.
4. **Classificacao do gesto**: regras geometricas sobre os landmarks
   (punho, cotovelo, ombro e nariz), em `slide_controller.py::detect_gesture`.
5. **Filtro anti falso positivo**: o gesto precisa ser sustentado por
   `--dwell` segundos (padrao 1,0 s) e depois ha um `--cooldown`
   (padrao 1,5 s) antes de aceitar outro comando.
6. **Acao**: `pyautogui` envia a tecla ao aplicativo em foco.

A deteccao roda no frame sem espelhar, para que "braco direito" seja o
braco direito real da pessoa. So a janela de visualizacao e espelhada.

## Reproduzir o experimento

Requisitos: Python 3.9 a 3.12, webcam.

```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/Mac
pip install -r requirements.txt
```

Teste sem enviar teclas (so mostra o reconhecimento na tela):

```bash
python slide_controller.py --dry-run
```

Uso real: abra a apresentacao em modo de exibicao (F5 no PowerPoint),
deixe a janela da apresentacao em foco e rode:

```bash
python slide_controller.py
```

Parametros opcionais: `--dwell 0.8`, `--cooldown 2.0`, `--camera 1`,
`--debug` (mostra na tela os valores dos landmarks usados nas regras).

Teclas na janela do programa: `Q`/`ESC` sai, `R` recalibra, `D` mostra ou
esconde o esqueleto.

Todo comando disparado e registrado em `gestos_log.csv`
(hora, gesto, acao, tecla), usado para montar a tabela de acuracia.

## Protocolo de avaliacao

1. Cada gesto executado 20 vezes por pessoa; conta acertos e erros a partir
   do log.
2. Teste de falso positivo: 2 minutos apresentando e gesticulando
   normalmente, sem fazer os gestos; o esperado e zero comandos no log.

## Estrutura

- `slide_controller.py`: classificacao dos gestos, maquina de estados
  (dwell/cooldown), HUD e envio de teclas.
- `pose_tracker.py`: captura, MediaPipe Pose, calibracao e desenho do
  esqueleto. Base reaproveitada do projeto Body Motion Game.
- `pose_landmarker_lite.task`: modelo do MediaPipe (baixado
  automaticamente se faltar).

## Equipe

(Grazi Gonçalves, Leonardo Chaves, Luiz Eduardo Cajueiro, Marina Durand, Nathan Mansur)
