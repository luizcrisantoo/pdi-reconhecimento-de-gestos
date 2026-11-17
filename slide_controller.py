"""
Controle de slides por gestos corporais (MediaPipe Pose).

Reaproveita o PoseTracker do Body Motion Game e adiciona uma camada de
comandos com tempo de sustentacao (dwell) para evitar falsos positivos.

Gestos:
  - Braco DIREITO esticado para cima  -> proximo slide   (tecla ->)
  - Braco ESQUERDO esticado para cima -> slide anterior  (tecla <-)
  - Duas maos na cabeca               -> tela preta / volta (tecla B)

Uso:
  python slide_controller.py            # envia teclas de verdade
  python slide_controller.py --dry-run  # so mostra na tela, nao envia teclas
  python slide_controller.py --dwell 0.8 --cooldown 1.5

Teclas na janela: Q/ESC sai, R recalibra, D liga/desliga esqueleto.
"""
import argparse
import csv
import sys
import time

import cv2

from pose_tracker import PoseTracker

# --- Landmarks do MediaPipe Pose usados aqui ---
NOSE = 0
L_SHOULDER, R_SHOULDER = 11, 12
L_ELBOW, R_ELBOW = 13, 14
L_WRIST, R_WRIST = 15, 16

ACTIONS = {
    'right_up': ('PROXIMO', 'right'),
    'left_up': ('ANTERIOR', 'left'),
    'hands_head': ('TELA PRETA', 'b'),
}


def detect_gesture(landmarks):
    """Classifica o gesto do frame atual a partir dos 33 landmarks.

    Regras geometricas (coordenadas normalizadas 0..1, y cresce para baixo):
      braco para cima  = punho acima do nariz E cotovelo na altura do ombro ou acima,
                         com o outro punho abaixo do ombro (so um braco).
      maos na cabeca   = os dois punhos a menos de 0.22 (x) e 0.18 (y) do nariz.
    Retorna 'right_up', 'left_up', 'hands_head' ou None.
    """
    nose = landmarks[NOSE]
    ls, rs = landmarks[L_SHOULDER], landmarks[R_SHOULDER]
    le, re = landmarks[L_ELBOW], landmarks[R_ELBOW]
    lw, rw = landmarks[L_WRIST], landmarks[R_WRIST]

    def near_head(w):
        return abs(w.x - nose.x) < 0.22 and abs(w.y - nose.y) < 0.18

    if near_head(lw) and near_head(rw):
        return 'hands_head'

    # cotovelo pode ficar ate 0.08 abaixo do ombro (braco em L tambem vale)
    right_up = rw.y < nose.y and re.y < rs.y + 0.08 and lw.y > ls.y
    left_up = lw.y < nose.y and le.y < ls.y + 0.08 and rw.y > rs.y

    if right_up and not left_up:
        return 'right_up'
    if left_up and not right_up:
        return 'left_up'
    return None


class GestureCommander:
    """Maquina de estados: gesto sustentado por `dwell` s dispara uma acao,
    depois espera `cooldown` s antes de aceitar outra."""

    def __init__(self, dwell=1.0, cooldown=1.5, dry_run=False, log_path='gestos_log.csv'):
        self.dwell = dwell
        self.cooldown = cooldown
        self.dry_run = dry_run
        self.current = None
        self.started_at = None
        self.blocked_until = 0.0
        self.last_fired = ''
        self.last_fired_at = 0.0
        self.log = open(log_path, 'a', newline='', encoding='utf-8')
        self.writer = csv.writer(self.log)
        if self.log.tell() == 0:
            self.writer.writerow(['timestamp', 'gesto', 'acao', 'tecla', 'dry_run'])
        self.pyautogui = None
        if not dry_run:
            import pyautogui
            pyautogui.FAILSAFE = False
            self.pyautogui = pyautogui

    def update(self, gesture):
        """Chamar a cada frame. Retorna progresso 0..1 do dwell."""
        now = time.monotonic()
        if now < self.blocked_until:
            self.current, self.started_at = None, None
            return 0.0
        if gesture is None:
            self.current, self.started_at = None, None
            return 0.0
        if gesture != self.current:
            self.current, self.started_at = gesture, now
            return 0.0
        progress = (now - self.started_at) / self.dwell
        if progress >= 1.0:
            self._fire(gesture)
            self.blocked_until = now + self.cooldown
            self.current, self.started_at = None, None
            return 1.0
        return progress

    def _fire(self, gesture):
        name, key = ACTIONS[gesture]
        self.last_fired, self.last_fired_at = name, time.monotonic()
        if self.pyautogui:
            self.pyautogui.press(key)
        self.writer.writerow([time.strftime('%H:%M:%S'), gesture, name, key, self.dry_run])
        self.log.flush()
        print(f'[GESTO] {gesture:<11} -> {name} ({key}){"  [dry-run]" if self.dry_run else ""}')

    def close(self):
        self.log.close()


def draw_hud(frame, gesture, progress, commander, show_hint):
    h, w = frame.shape[:2]
    label = gesture or '-'
    cv2.putText(frame, f'Gesto: {label}', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

    # barra de dwell
    bar_w = int((w - 20) * min(progress, 1.0))
    cv2.rectangle(frame, (10, 45), (w - 10, 65), (80, 80, 80), 2)
    if bar_w > 0:
        cv2.rectangle(frame, (10, 45), (10 + bar_w, 65), (0, 200, 255), -1)

    # cooldown
    remaining = commander.blocked_until - time.monotonic()
    if remaining > 0:
        cv2.putText(frame, f'cooldown {remaining:.1f}s', (10, 95),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)

    # ultima acao disparada (fica 2 s na tela)
    if commander.last_fired and time.monotonic() - commander.last_fired_at < 2.0:
        cv2.putText(frame, commander.last_fired, (w // 2 - 120, h // 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.6, (0, 255, 255), 4)

    if show_hint:
        cv2.putText(frame, 'Dir. cima = proximo | Esq. cima = anterior | Maos cabeca = tela preta',
                    (10, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    return frame


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true', help='nao envia teclas')
    ap.add_argument('--dwell', type=float, default=1.0, help='segundos sustentando o gesto')
    ap.add_argument('--cooldown', type=float, default=1.5, help='segundos de espera apos um comando')
    ap.add_argument('--camera', type=int, default=0)
    ap.add_argument('--debug', action='store_true', help='mostra os valores dos landmarks na tela')
    args = ap.parse_args()

    cap = cv2.VideoCapture(args.camera)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    if not cap.isOpened():
        print('ERRO: camera nao abriu')
        sys.exit(1)

    tracker = PoseTracker()
    commander = GestureCommander(args.dwell, args.cooldown, args.dry_run)
    show_skeleton = True

    # Janela pequena, sempre por cima e no canto: da pra ver a barra de dwell
    # com o PowerPoint em tela cheia e em foco (quem esta em foco recebe a tecla).
    WIN = 'Controle de Slides por Gestos'
    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN, 640, 480)
    cv2.moveWindow(WIN, 20, 20)
    try:
        cv2.setWindowProperty(WIN, cv2.WND_PROP_TOPMOST, 1)
    except Exception:
        pass

    print('=' * 60)
    print('CONTROLE DE SLIDES POR GESTOS', '(dry-run)' if args.dry_run else '')
    print('Fique em posicao neutra para calibrar...')
    print('Q/ESC sai | R recalibra | D esqueleto on/off')
    print('Depois que a janela abrir, CLIQUE NO POWERPOINT para ele receber as teclas.')
    print('=' * 60)

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        # A deteccao roda no frame SEM espelhar, para que "braco direito"
        # seja o braco direito real da pessoa. So a exibicao e espelhada.
        results = tracker.process_frame(frame)

        gesture, progress = None, 0.0
        if not tracker.is_calibrated:
            tracker.calibrate(results)
        elif results.pose_landmarks:
            gesture = detect_gesture(results.pose_landmarks[0])
            progress = commander.update(gesture)
        else:
            commander.update(None)

        view = tracker.draw_landmarks(frame.copy(), results) if show_skeleton else frame.copy()
        view = cv2.flip(view, 1)

        # Diagnostico (--debug): mostra se ha pessoa detectada e os valores usados nas regras
        if not results.pose_landmarks:
            cv2.putText(view, 'SEM PESSOA DETECTADA', (10, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        elif args.debug:
            lm = results.pose_landmarks[0]
            n, rs, re_, rw = lm[NOSE], lm[R_SHOULDER], lm[R_ELBOW], lm[R_WRIST]
            ls, le_, lw = lm[L_SHOULDER], lm[L_ELBOW], lm[L_WRIST]
            cv2.putText(view, f'nariz y={n.y:.2f}', (10, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 0), 1)
            cv2.putText(view, f'DIR punho={rw.y:.2f} cotov={re_.y:.2f} ombro={rs.y:.2f}', (10, 155), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 0), 1)
            cv2.putText(view, f'ESQ punho={lw.y:.2f} cotov={le_.y:.2f} ombro={ls.y:.2f}', (10, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 0), 1)
            cv2.putText(view, f'dist maos-nariz: D=({abs(rw.x-n.x):.2f},{abs(rw.y-n.y):.2f}) E=({abs(lw.x-n.x):.2f},{abs(lw.y-n.y):.2f})', (10, 205), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)

        if not tracker.is_calibrated:
            p = tracker.get_state()['calibration_progress']
            cv2.putText(view, f'Calibrando... {int(p * 100)}%', (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        else:
            draw_hud(view, gesture, progress, commander, show_hint=True)

        cv2.imshow(WIN, view)
        key = cv2.waitKey(1) & 0xFF
        if key in (ord('q'), 27):
            break
        elif key == ord('r'):
            tracker.reset_calibration()
        elif key == ord('d'):
            show_skeleton = not show_skeleton

    commander.close()
    cap.release()
    cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
