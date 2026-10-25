"""Configuración de las pruebas: usan una base de datos temporal, nunca la real."""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

# Estas variables se fijan ANTES de importar main
os.environ.update(
    DATA_DIR=tempfile.mkdtemp(),
    ADMIN_USER="jaime",
    ADMIN_PASSWORD="clave-de-prueba-1",
    MODO_DEMO="1",
    LIMITE_SESION="5",
    INTENTOS_LOGIN="3",
    MODELO_PATH="/no/existe/modelo.h5",
    RETENCION_DIAS="0",
)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

import main



def _imagen(formato: str, tamano=(320, 240), exif=False) -> bytes:
    """Una foto de verdad (el servidor ahora la abre y la guarda de nuevo, así que no sirven bytes inventados)."""
    import io
    from PIL import Image
    salida = io.BytesIO()
    img = Image.new("RGB", tamano, (60, 140, 90))
    if exif:
        datos = Image.Exif()
        datos[0x010F] = "MarcaDelCelular"       # un dato EXIF cualquiera: debe desaparecer
        img.save(salida, formato, exif=datos)
    else:
        img.save(salida, formato)
    return salida.getvalue()


JPG = _imagen("JPEG")
PNG = _imagen("PNG")
WEBP = _imagen("WEBP")
JPG_CON_EXIF = _imagen("JPEG", exif=True)
JPG_GRANDE = _imagen("JPEG", tamano=(3000, 2000))
PRINCIPAL = {"usuario": "jaime", "clave": "clave-de-prueba-1"}


@pytest.fixture
def app_lista():
    """Arranca la app (con su lifespan) y limpia los datos entre pruebas."""
    with TestClient(main.app):
        main._limites.clear()
        with sqlite3.connect(main.DB_PATH) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("DELETE FROM reportes")                       # borra también los residuos (CASCADE)
            conn.execute("DELETE FROM administradores WHERE rol = 'admin'")
            conn.execute("UPDATE administradores SET clave_hash = ? WHERE rol = 'principal'", (main.hashear_clave("clave-de-prueba-1"),))
            conn.execute("DELETE FROM cursos")
            for n in main.CURSOS_INICIALES:
                conn.execute("INSERT INTO cursos (nombre) VALUES (?)", (n,))
        yield main.app


@pytest.fixture
def estudiante(app_lista):
    """Cliente que YA escaneó el QR."""
    c = TestClient(app_lista)
    r = c.get(f"/q/{main.cfg_get('qr_token')}", follow_redirects=False)
    assert r.status_code == 303
    return c


@pytest.fixture
def anonimo(app_lista):
    return TestClient(app_lista)


@pytest.fixture
def admin(app_lista):
    c = TestClient(app_lista)
    assert c.post("/admin/api/login", json=PRINCIPAL).status_code == 200
    return c


def crear_admin_secundario(admin, usuario="pedro", clave="clave-pedro-123"):
    r = admin.post("/admin/api/administradores", json={"usuario": usuario, "nombre": "Pedro", "clave": clave})
    assert r.status_code == 201, r.text
    return usuario, clave


def enviar(cliente, usuario="Laura", curso="801", foto=JPG, nombre="f.jpg", tipo="image/jpeg", consentimiento="true"):
    return cliente.post(
        "/api/reportar",
        data={"usuario": usuario, "curso": curso, "consentimiento": consentimiento},
        files={"foto": (nombre, foto, tipo)},
    )
