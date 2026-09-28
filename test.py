import cv2
import mediapipe as mp
import subprocess
import time
import shutil
import os
import warnings

# Silenciar warnings de librerías que no son nuestros
warnings.filterwarnings("ignore")
os.environ["GRPC_VERBOSITY"] = "ERROR"
os.environ["GLOG_minloglevel"] = "2"

# ─── Detección de entorno ───────────────────────────────────────────────────
SESSION  = os.environ.get("XDG_SESSION_TYPE", "x11").lower()       # wayland / x11
DESKTOP  = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()       # gnome / sway / hyprland / kde
WAYLAND_DISPLAY = os.environ.get("WAYLAND_DISPLAY", "")

def check_tool(name):
    return shutil.which(name) is not None

def trigger_wm_overview():
    """
    Dispara el overview/actividades del WM detectado.
    Compatible con GNOME (X11/Wayland), Sway, Hyprland, KDE, XFCE.
    """

    # ── GNOME: dbus es MÁS confiable que wtype en GNOME ──
    if "gnome" in DESKTOP:
        try:
            subprocess.Popen([
                "gdbus", "call", "--session",
                "--dest", "org.gnome.Shell",
                "--object-path", "/org/gnome/Shell",
                "--method", "org.gnome.Shell.Eval",
                "Main.overview.toggle();"
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return "gdbus → GNOME overview"
        except FileNotFoundError:
            pass  # fallback abajo

    # ── Sway: swaymsg es lo más directo ──
    if "sway" in DESKTOP and check_tool("swaymsg"):
        subprocess.Popen(
            ["swaymsg", "exec", "swayr switch-window"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return "swaymsg"

    # ── Wayland genérico (Hyprland, Sway sin XDG seteado, etc.) ──
    if SESSION == "wayland" or WAYLAND_DISPLAY:
        if check_tool("wtype"):
            # Nombre XKB correcto: Super_L, no 'super'
            subprocess.Popen(
                ["wtype", "-k", "Super_L"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            return "wtype -k Super_L"
        if check_tool("ydotool"):
            # ydotool usa keycodes Linux: 125 = KEY_LEFTMETA (Super)
            subprocess.Popen(
                ["ydotool", "key", "125:1", "125:0"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            return "ydotool key Super"

    # ── X11 ──
    if check_tool("xdotool"):
        subprocess.Popen(
            ["xdotool", "key", "super"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return "xdotool key super"

    return "⚠️  Ninguna herramienta disponible"

# ─── Info del entorno al inicio ────────────────────────────────────────────
print(f"🖥️  Entorno detectado: SESSION={SESSION}, DESKTOP={DESKTOP}")
print(f"   wtype={check_tool('wtype')} | xdotool={check_tool('xdotool')} | "
      f"ydotool={check_tool('ydotool')} | swaymsg={check_tool('swaymsg')}")

# ─── MediaPipe ────────────────────────────────────────────────────────────
mp_hands   = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils

hands = mp_hands.Hands(
    max_num_hands=1,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.7
)

cap = cv2.VideoCapture(0)
cooldown = time.time()

print("✌️  Listo. Señal de paz para activar el WM. ESC para salir.")

try:
    while cap.isOpened():
        success, frame = cap.read()
        if not success:
            continue

        frame     = cv2.flip(frame, 1)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results   = hands.process(rgb_frame)

        gesto_activo = False

        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:
                mp_drawing.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)
                pts = hand_landmarks.landmark

                indice_levantado = pts[8].y  < pts[6].y
                medio_levantado  = pts[12].y < pts[10].y
                anular_doblado   = pts[16].y > pts[14].y
                menique_doblado  = pts[20].y > pts[18].y
                pulgar_neutro    = True  # no lo usamos como filtro

                if indice_levantado and medio_levantado and anular_doblado and menique_doblado:
                    gesto_activo = True
                    if time.time() - cooldown > 1.5:
                        metodo = trigger_wm_overview()
                        print(f"▲ Gesto detectado → {metodo}")
                        cooldown = time.time()

        label = f"GESTO OK [{SESSION}/{DESKTOP or 'WM'}]" if gesto_activo else f"{SESSION}/{DESKTOP or 'WM'}"
        color = (0, 255, 0) if gesto_activo else (200, 200, 200)
        cv2.putText(frame, label, (10, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

        cv2.imshow("Control Gestual", frame)
        if cv2.waitKey(5) & 0xFF == 27:
            break

finally:
    cap.release()
    cv2.destroyAllWindows()
    hands.close()
