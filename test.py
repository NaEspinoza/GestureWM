#!/usr/bin/env python3
"""
gesture_wm.py — Control de WM mediante gestos de mano
Compatibilidad: GNOME Wayland/X11, Sway, Hyprland, X11 genérico
Deps: mediapipe, opencv-python
Opcionales: gdbus (GNOME), wtype (Wayland), swaymsg (Sway), xdotool (X11)
"""

import cv2
import mediapipe as mp
import subprocess
import time
import shutil
import os
import warnings
from collections import deque, Counter

# ── Silenciar logs ruidosos ANTES de importar mediapipe ──────────────────────
warnings.filterwarnings("ignore")
os.environ.update({
    "GRPC_VERBOSITY":       "ERROR",
    "GLOG_minloglevel":     "2",
    "TF_CPP_MIN_LOG_LEVEL": "3",
    "ABSL_MIN_LOG_LEVEL":   "3",
})

# ── Detección de entorno ─────────────────────────────────────────────────────
SESSION  = os.environ.get("XDG_SESSION_TYPE", "x11").lower()
DESKTOP  = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
IS_GNOME   = "gnome"        in DESKTOP
IS_SWAY    = "sway" in DESKTOP or "i3" in DESKTOP
IS_WAYLAND = SESSION == "wayland"

def has(cmd: str) -> bool:
    return bool(shutil.which(cmd))

# ── Backends de acción ───────────────────────────────────────────────────────

def _run(*cmd: str) -> None:
    subprocess.Popen(list(cmd), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def _gdbus(js: str) -> None:
    """GNOME Shell JS vía D-Bus. Requiere org.gnome.Shell.Eval habilitado."""
    _run("gdbus", "call", "--session",
         "--dest",        "org.gnome.Shell",
         "--object-path", "/org/gnome/Shell",
         "--method",      "org.gnome.Shell.Eval", js)

def _wtype(*args: str) -> None:
    _run("wtype", *args)

def _xdotool(*args: str) -> None:
    _run("xdotool", *args)

def _swaymsg(cmd: str) -> None:
    _run("swaymsg", cmd)

# ── GNOME Shell JS snippets (Mutter API) ─────────────────────────────────────
_GS = {
    "overview": "Main.overview.toggle();",
    "close":    "var w=global.display.focus_window;if(w)w.delete(global.get_current_time());",
    "minimize": "var w=global.display.focus_window;if(w)w.minimize();",
    "maximize": "var w=global.display.focus_window;if(w)w.maximize(3);",  # 3 = BOTH axes
    "restore":  "var w=global.display.focus_window;if(w)w.unmaximize(3);",
}

# ── Registro de acciones: (gnome_js, wtype_args, xdotool_args, sway_cmd) ────
_REGISTRY: dict[str, tuple] = {
    # acción        gdbus JS            wtype args                     xdotool args              swaymsg
    "overview":  (_GS["overview"],  ["-M","logo","-k","Super_L"],  ["key","super"],         "workspace next_on_output"),
    "launcher":  (None,             ["-M","alt", "-k","F2"     ],  ["key","alt+F2"],         "exec fuzzel"),
    "close":     (_GS["close"],     ["-M","alt", "-k","F4"     ],  ["key","alt+F4"],         "kill"),
    "minimize":  (_GS["minimize"],  ["-M","alt", "-k","F9"     ],  ["key","alt+F9"],         "move scratchpad"),
    "maximize":  (_GS["maximize"],  ["-M","logo","-k","Up"     ],  ["key","super+Up"],       "fullscreen toggle"),
    "restore":   (_GS["restore"],   ["-M","logo","-k","Down"   ],  ["key","super+Down"],     "fullscreen disable"),
    "snap_left": (None,             ["-M","logo","-k","Left"   ],  ["key","super+Left"],     "split h"),
    "snap_right":(None,             ["-M","logo","-k","Right"  ],  ["key","super+Right"],    "split v"),
}

def execute(action: str) -> str:
    """Ejecuta una acción de WM usando el mejor backend disponible."""
    if action not in _REGISTRY:
        return "? accion desconocida"
    js, wtype_a, xdo_a, sway_cmd = _REGISTRY[action]

    if IS_GNOME:
        if js and has("gdbus"):
            _gdbus(js)
            return "gdbus/GNOME"
        if wtype_a and has("wtype"):
            _wtype(*wtype_a)
            return "wtype/GNOME"

    if IS_SWAY and has("swaymsg"):
        _swaymsg(sway_cmd)
        return "swaymsg/Sway"

    if IS_WAYLAND and has("wtype") and wtype_a:
        _wtype(*wtype_a)
        return "wtype/Wayland"

    if has("xdotool") and xdo_a:
        _xdotool(*xdo_a)
        return "xdotool/X11"

    return "SIN HERRAMIENTA"

# ── Clasificación de gestos ──────────────────────────────────────────────────
#
#  Mapa de landmarks MediaPipe:
#  Muñeca=0  | Pulgar: 1-2-3-4  | Índice: 5-6-7-8
#  Medio: 9-10-11-12  | Anular: 13-14-15-16 | Meñique: 17-18-19-20
#
#  TABLA DE GESTOS:
#  ─────────────────────────────────────────────────────────────
#  Índice  Medio  Anular  Meñique  Pulgar │ Gesto       Acción
#  ─────────────────────────────────────────────────────────────
#  UP      -      -       -        -      │ ☝ Índice   → Launcher
#  UP      UP     -       -        -      │ ✌ Paz      → Overview
#  UP      UP     UP      -        -      │ 3 dedos    → Snap izq
#  UP      UP     UP      UP       -      │ 🖐 Abierta → Maximizar
#  UP      -      -       UP       -      │ 🤘 Rock    → Cerrar
#  -       -      -       -        UP     │ 👍 Pulgar  → Restaurar
#  -       -      -       -        -      │ ✊ Puño    → Minimizar
#  -       UP     UP      UP       -      │ (M+R+P)   → Snap der
#  ─────────────────────────────────────────────────────────────

def _ext(pts, tip: int, pip: int) -> bool:
    """True si el dedo está extendido (tip por encima del PIP joint)."""
    return pts[tip].y < pts[pip].y

def classify(pts) -> str | None:
    """Clasifica el gesto actual. Retorna nombre o None."""

    # Verificar orientación: muñeca (0) debe estar BAJO el nudillo medio (9)
    # Si no, la mano está boca abajo o de lado → ignorar
    if pts[0].y < pts[9].y:
        return None

    i = _ext(pts, 8,  6)   # índice
    m = _ext(pts, 12, 10)  # medio
    r = _ext(pts, 16, 14)  # anular
    p = _ext(pts, 20, 18)  # meñique

    # Pulgar: tip claramente por encima de su CMC y MCP joint
    t = pts[4].y < pts[2].y and pts[4].y < pts[3].y

    match (i, m, r, p):
        case (True,  False, False, False): return "launcher"
        case (True,  True,  False, False): return "overview"
        case (True,  True,  True,  False): return "snap_left"
        case (True,  True,  True,  True ): return "maximize"
        case (True,  False, False, True ): return "close"
        case (False, True,  True,  True ): return "snap_right"
        case (False, False, False, False) if t: return "restore"
        case (False, False, False, False):      return "minimize"
        case _:                                 return None

# ── HUD ─────────────────────────────────────────────────────────────────────

_LEGEND = [
    ("[I]    Indice solo ",  "Launcher / Alt+F2      "),
    ("[II]   Paz         ",  "Overview / Activities   "),
    ("[III]  3 (I+M+R)   ",  "Snap Izquierda          "),
    ("[IIII] Mano abierta",  "Maximizar               "),
    ("[I  P] Rock        ",  "Cerrar ventana          "),
    ("[ MRP] 3 (M+R+P)   ",  "Snap Derecha            "),
    ("[T]    Pulgar arriba",  "Restaurar               "),
    ("[===]  Puno        ",  "Minimizar               "),
]

_ACTION_COLOR = {
    "launcher":   (50,  200, 255),   # amarillo
    "overview":   (255, 255, 50 ),   # cyan
    "close":      (50,  50,  255),   # rojo
    "minimize":   (50,  150, 200),   # naranja
    "maximize":   (50,  255, 50 ),   # verde
    "restore":    (100, 255, 200),   # verde claro
    "snap_left":  (255, 150, 50 ),   # azul
    "snap_right": (200, 50,  200),   # violeta
}

def draw_hud(frame, current: str | None, progress: float, last_log: str) -> None:
    h, w = frame.shape[:2]
    font   = cv2.FONT_HERSHEY_SIMPLEX
    LS     = 18  # line step

    # Panel leyenda semitransparente (top-right)
    panel_w = 380
    overlay = frame.copy()
    cv2.rectangle(overlay, (w - panel_w - 8, 0), (w, len(_LEGEND) * LS + 12), (10, 10, 10), -1)
    cv2.addWeighted(overlay, 0.60, frame, 0.40, 0, frame)

    for idx, (gname, aname) in enumerate(_LEGEND):
        cv2.putText(frame, f"{gname}: {aname}",
                    (w - panel_w, 14 + idx * LS),
                    font, 0.38, (140, 140, 140), 1, cv2.LINE_AA)

    # Gesto activo (grande, izquierda abajo)
    if current:
        color = _ACTION_COLOR.get(current, (255, 255, 255))
        label = f">> {current.upper()}"
        cv2.putText(frame, label, (12, h - 52), font, 1.1, color, 2, cv2.LINE_AA)

    # Log último action (pequeño, muy abajo)
    if last_log:
        cv2.putText(frame, last_log, (12, h - 20), font, 0.48, (160, 160, 160), 1, cv2.LINE_AA)

    # Barra de cooldown (bottom, crece hasta estar listo)
    cv2.rectangle(frame, (0, h - 7), (w, h), (25, 25, 25), -1)
    bar_w = int(w * min(progress, 1.0))
    bar_color = (0, 200, 90) if progress < 1.0 else (0, 255, 120)
    cv2.rectangle(frame, (0, h - 7), (bar_w, h), bar_color, -1)

    # Indicador de sesión (top-left, pequeño)
    cv2.putText(frame, f"{SESSION}/{DESKTOP or 'WM'}",
                (8, 18), font, 0.38, (80, 80, 80), 1, cv2.LINE_AA)

# ── Main ─────────────────────────────────────────────────────────────────────

STABILITY_N = 6     # frames consecutivos del mismo gesto para disparar
COOLDOWN_S  = 1.5   # segundos mínimos entre acciones

mp_h = mp.solutions.hands
mp_d = mp.solutions.drawing_utils

detector = mp_h.Hands(
    max_num_hands          = 1,
    min_detection_confidence  = 0.7,
    min_tracking_confidence   = 0.7,
)

cap      = cv2.VideoCapture(0)
buf      = deque(maxlen=STABILITY_N)
ts       = time.time()
last_log = ""

print(f"\n🖥  Entorno: {SESSION.upper()} / {DESKTOP or 'desconocido'}")
print(f"   gdbus={'✓' if has('gdbus') else '✗'}  "
      f"wtype={'✓' if has('wtype') else '✗'}  "
      f"xdotool={'✓' if has('xdotool') else '✗'}  "
      f"swaymsg={'✓' if has('swaymsg') else '✗'}")
print()
print("  GESTOS:")
for g, a in _LEGEND:
    print(f"    {g} → {a.strip()}")
print("\n  ESC para salir\n")

try:
    while cap.isOpened():
        ok, frame = cap.read()
        if not ok:
            continue

        frame   = cv2.flip(frame, 1)
        results = detector.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

        raw = None
        if results.multi_hand_landmarks:
            for lm in results.multi_hand_landmarks:
                mp_d.draw_landmarks(frame, lm, mp_h.HAND_CONNECTIONS)
                raw = classify(lm.landmark)

        buf.append(raw)

        # Solo dispara si TODOS los frames del buffer son el mismo gesto
        stable = None
        if len(buf) == STABILITY_N:
            top, n = Counter(buf).most_common(1)[0]
            if top is not None and n == STABILITY_N:
                stable = top

        if stable and (time.time() - ts > COOLDOWN_S):
            method   = execute(stable)
            last_log = f"[{stable}]  via {method}"
            print(f"▲ {last_log}")
            ts = time.time()
            buf.clear()

        draw_hud(frame, raw, (time.time() - ts) / COOLDOWN_S, last_log)
        cv2.imshow("GestureWM", frame)
        if cv2.waitKey(5) & 0xFF == 27:
            break

finally:
    cap.release()
    cv2.destroyAllWindows()
    detector.close()
