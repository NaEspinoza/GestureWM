import cv2
import mediapipe as mp
import subprocess
import time
import shutil

# Verificar dependencia
if not shutil.which("wtype"):
    print("❌ wtype no encontrado. Instalá: sudo apt install wtype")
    exit(1)

mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils

hands = mp_hands.Hands(
    max_num_hands=1,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.7
)

cap = cv2.VideoCapture(0)
cooldown = time.time()  # ← fix: no disparar en el primer frame

print("🤖 Listo. Señal de paz (✌️) para abrir Activities...")

try:
    while cap.isOpened():
        success, frame = cap.read()
        if not success:
            continue

        frame = cv2.flip(frame, 1)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = hands.process(rgb_frame)

        gesto_activo = False

        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:
                mp_drawing.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)
                pts = hand_landmarks.landmark

                indice_levantado = pts[8].y < pts[6].y
                medio_levantado  = pts[12].y < pts[10].y
                anular_doblado   = pts[16].y > pts[14].y
                menique_doblado  = pts[20].y > pts[18].y

                if indice_levantado and medio_levantado and anular_doblado and menique_doblado:
                    gesto_activo = True
                    if time.time() - cooldown > 1.5:
                        print("▲ Gesto detectado → disparando Super")
                        # Super solo abre Activities en GNOME 46
                        subprocess.Popen(["wtype", "-k", "super"])
                        cooldown = time.time()

        if gesto_activo:
            cv2.putText(frame, "GESTO OK!", (10, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 0), 3)

        cv2.imshow('Control Gestual', frame)
        if cv2.waitKey(5) & 0xFF == 27:
            break

finally:
    cap.release()
    cv2.destroyAllWindows()
    hands.close()
