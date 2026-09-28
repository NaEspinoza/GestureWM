# Gesture Windows Manager - Testeado en Ubuntu 24 gnome

8 gestos distintos, en orden de "falsas alarmas" de menor a mayor riesgo:

Gesto	Combinación	Acción
☝ Índice	solo I arriba	Launcher
✌ Paz	I+M arriba	Overview
3 dedos IMR	I+M+R, P abajo	Snap izquierda
🖐 Abierta	I+M+R+P arriba	Maximizar
🤘 Rock	I+P, sin M ni R	Cerrar
MRP	M+R+P, I abajo	Snap derecha
👍 Pulgar	puño + pulgar arriba	Restaurar
✊ Puño	todo abajo	Minimizar

Buffer de estabilidad: 6 frames consecutivos idénticos antes de disparar. Elimina casi todos los falsos positivos de mano en movimiento.

Check de orientación: si la muñeca está más arriba que el nudillo del dedo medio, la mano está boca abajo → ignorar. Evita que bajar la mano dispare el puño.
