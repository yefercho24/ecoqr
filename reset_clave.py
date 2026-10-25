"""
Restablece la contraseña de un administrador (por ejemplo, si el profesor la olvidó).
Hay que ejecutarlo en el servidor donde corre EcoQR.

Uso:
    python reset_clave.py jaime
"""
import getpass
import sys

import main

if len(sys.argv) != 2:
    sys.exit("Uso: python reset_clave.py USUARIO")

fila = main.db_one("SELECT id, usuario FROM administradores WHERE usuario = ?", (sys.argv[1],))
if not fila:
    sys.exit(f"No existe el usuario '{sys.argv[1]}'.")

clave = getpass.getpass("Nueva contraseña (mínimo 8 caracteres): ")
if len(clave) < 8 or clave != getpass.getpass("Repítela: "):
    sys.exit("Las contraseñas no coinciden o son muy cortas. No se cambió nada.")

main.db_exec("UPDATE administradores SET clave_hash = ?, activo = 1 WHERE id = ?", (main.hashear_clave(clave), fila["id"]))
print(f"Listo: la contraseña de '{fila['usuario']}' fue cambiada (y la cuenta quedó activa).")
