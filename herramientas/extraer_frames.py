"""
Convierte VIDEOS cortos en fotos de entrenamiento para Teachable Machine.

Estructura de entrada (una carpeta por clase, con videos y/o fotos adentro):
    videos/botella/v1.mp4  v2.mp4 ...
    videos/papel/...
    videos/otro/...          <- manos, piso, mesa, canecas vacías, objetos que no son residuos

Uso:
    pip install opencv-python
    python herramientas/extraer_frames.py videos fotos --por-video 12

Salida: fotos/<clase>/*.jpg (reducidas a máximo 640 px), listas para subir a Teachable Machine.
Consejo: graba 5 a 8 videos de 15-20 s POR CLASE, cada uno con un objeto distinto,
girándolo y acercándolo/alejándolo. Cambia de fondo y de luz entre videos.
"""
import argparse
import shutil
import sys
from pathlib import Path

import cv2

VIDEOS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".3gp"}
FOTOS = {".jpg", ".jpeg", ".png", ".webp"}


def reducir(img, maximo=640):
    alto, ancho = img.shape[:2]
    escala = maximo / max(alto, ancho)
    return img if escala >= 1 else cv2.resize(img, (int(ancho * escala), int(alto * escala)), interpolation=cv2.INTER_AREA)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("entrada", type=Path)
    ap.add_argument("salida", type=Path)
    ap.add_argument("--por-video", type=int, default=12, help="fotos que se sacan de cada video (default 12)")
    a = ap.parse_args()
    if not a.entrada.is_dir():
        sys.exit(f"No existe la carpeta {a.entrada}")

    for clase in sorted(p for p in a.entrada.iterdir() if p.is_dir()):
        destino = a.salida / clase.name
        destino.mkdir(parents=True, exist_ok=True)
        n = 0
        for archivo in sorted(clase.iterdir()):
            ext = archivo.suffix.lower()
            if ext in FOTOS:
                img = cv2.imread(str(archivo))
                if img is not None:
                    n += 1
                    cv2.imwrite(str(destino / f"{archivo.stem}_{n:04d}.jpg"), reducir(img))
            elif ext in VIDEOS:
                cap = cv2.VideoCapture(str(archivo))
                total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                if total <= 0:
                    print(f"  (no se pudo leer {archivo.name})")
                    continue
                k = min(a.por_video, total)
                for i in range(k):                                  # k fotos repartidas a lo largo del video
                    cap.set(cv2.CAP_PROP_POS_FRAMES, int((i + 0.5) * total / k))
                    ok, frame = cap.read()
                    if ok:
                        n += 1
                        cv2.imwrite(str(destino / f"{archivo.stem}_{n:04d}.jpg"), reducir(frame))
                cap.release()
        print(f"{clase.name}: {n} fotos")


if __name__ == "__main__":
    main()
