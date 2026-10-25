"""
Copia de seguridad de la base de datos (segura aunque el servidor esté funcionando).

Uso:
    python respaldo.py              # guarda en backups/ y conserva las 14 más recientes
    python respaldo.py --conservar 30

Prográmalo cada día (cron en Linux, Programador de tareas en Windows).
Las fotos están en data/uploads/: respáldala también (copia de la carpeta completa).
"""
import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

import main

parser = argparse.ArgumentParser()
parser.add_argument("--conservar", type=int, default=14)
args = parser.parse_args()

carpeta = main.DATA_DIR / "backups"
carpeta.mkdir(parents=True, exist_ok=True)
destino = carpeta / f"residuos-{datetime.now():%Y%m%d-%H%M%S}.db"

origen = sqlite3.connect(main.DB_PATH)
copia = sqlite3.connect(destino)
with copia:
    origen.backup(copia)   # API oficial de SQLite para copiar en caliente
copia.close()
origen.close()
print("Respaldo creado:", destino)

for viejo in sorted(carpeta.glob("residuos-*.db"))[:-args.conservar]:
    viejo.unlink()
