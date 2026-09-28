import cv2
import mediapipe as mp
import subprocess
import time

# Inicializar IA de MediaPipe para manos
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(
    max_num_hands=1, 
    min_detection_confidence=0.7, 
    min_tracking_confidence=0.7
)

# Inicializar captura de la webcam (0 suele ser la cámara integrada)
cap = cv2.VideoCapture(0)
cooldown = 0  

print("🤖 IA en Ubuntu 24 iniciada. Levanta Índice y Medio (Señal de Paz) para ver las ventanas...")

while cap.isOpened():
    success, frame = cap.read()
    if not success:
        continue

    # Espejar la imagen para que sea natural e ir a RGB
    frame = cv2.flip(frame, 1)
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = hands.process(rgb_frame)

    if results.multi_hand_landmarks:
        for hand_landmarks in results.multi_hand_landmarks:
            pts = hand_landmarks.landmark

            # LÓGICA CORRECTA: En OpenCV, 'y' disminuye al subir la mano en pantalla
            indice_levantado = pts[8].y < pts[6].y
            medio_levantado  = pts[12].y < pts[10].y
            anular_doblado   = pts[16].y > pts[14].y
            menique_doblado  = pts[20].y > pts[18].y

            # DETECCIÓN DEL GESTO
            if indice_levantado and medio_levantado and anular_doblado and menique_doblado:
                if time.time() - cooldown > 1.5:  # Esperar 1.5 segundos antes de repetir
                    print("▲ ¡Gesto detectado! Abriendo el gestor de ventanas de GNOME...")
                    
                    # Ejecuta Super + S en Wayland (Mosaico de actividades de Ubuntu 24)
                    subprocess.Popen(["wtype", "-M", "logo", "s"])
                    
                    cooldown = time.time()

    # Mostrar la cámara para verificar que te encuadre bien
    cv2.imshow('Control Gestual IA - Ubuntu 24', frame)
    if cv2.waitKey(5) & 0xFF == 27:  # Salir con ESC
        break

cap.release()
cv2.destroyAllWindows()
