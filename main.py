"""
EcoQR - Servidor back-end (FastAPI + SQLite)

Ejecutar en desarrollo:
    pip install -r requirements.txt
    MODO_DEMO=1 uvicorn main:app --host 0.0.0.0 --port 8000 --reload

    Estudiantes:     entran escaneando el QR (la dirección /q/<código>)
    Administración:  http://localhost:8000/admin

La primera vez que arranca crea la cuenta del administrador principal (el profesor).
Usuario y contraseña salen de ADMIN_USER y ADMIN_PASSWORD; si no defines la contraseña,
se genera una y se escribe en la consola. Ver .env.example para todas las variables.
"""

import base64
import csv
import hashlib
import hmac
import io
import json
import logging
import os
import re
import secrets
import shutil
import sqlite3
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager, closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Tuple

import segno
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool


def _cargar_env() -> None:
    """Lee el archivo .env (si existe, junto a main.py). Lo que ya esté definido en el sistema tiene prioridad."""
    ruta = Path(__file__).parent / ".env"
    if not ruta.is_file():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        valor = re.split(r"\s+#", valor.strip(), maxsplit=1)[0].strip().strip("\"'")   # quita comentarios y comillas
        os.environ.setdefault(clave.strip(), valor)


_cargar_env()   # debe ir ANTES de importar clasificador, que lee ANTHROPIC_API_KEY al importarse

import catalogo
import clasificador

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("ecoqr")

# ----------------------------------------------------------------------
# Configuración (todo se puede cambiar con variables de entorno)
# ----------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))   # aquí viven la BD y las fotos
DB_PATH = DATA_DIR / "ecoqr.db"
UPLOADS_DIR = DATA_DIR / "uploads"

ADMIN_USER = os.getenv("ADMIN_USER", "jaime")
ADMIN_NOMBRE = os.getenv("ADMIN_NOMBRE", "Profesor Jaime")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
PUBLIC_URL = os.getenv("PUBLIC_URL", "").rstrip("/")         # dirección pública, para armar el QR
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]

# Hora: Colombia es UTC-5 todo el año. Los servidores en la nube trabajan en UTC, así que fijamos el desfase aquí.
TZ_OFFSET_HORAS = int(os.getenv("TZ_OFFSET_HORAS", "-5"))
ZONA = timezone(timedelta(hours=TZ_OFFSET_HORAS))


def ahora() -> datetime:
    """Hora actual del colegio (sin zona), para guardar y comparar fechas."""
    return datetime.now(ZONA).replace(tzinfo=None)


# Límites. OJO: en un colegio todos comparten la misma IP del WiFi, por eso el límite
# principal es por sesión de estudiante y el de IP es amplio.
LIMITE_SESION = int(os.getenv("LIMITE_SESION", "8"))         # reportes por minuto por estudiante
LIMITE_IP = int(os.getenv("LIMITE_IP", "200"))               # reportes por minuto por IP
LIMITE_DIARIO_IA = int(os.getenv("LIMITE_DIARIO_IA", "1500")) # fotos por día que se envían a la IA de pago (0 = sin tope)
INTENTOS_LOGIN = int(os.getenv("INTENTOS_LOGIN", "5"))       # fallos permitidos cada 10 minutos
RETENCION_DIAS = int(os.getenv("RETENCION_DIAS", "0"))       # 0 = no borrar nunca

TAMANO_MAXIMO = 12 * 1024 * 1024                             # 12 MB (la app ya reduce la foto antes de enviarla)
NOMBRE_FOTO = re.compile(r"[0-9a-f]{32}\.(jpg|png|webp)")
COOKIE_ESTUDIANTE = "ecoqr_acceso"
COOKIE_ADMIN = "ecoqr_admin"
CURSOS_INICIALES = ["801", "802", "901", "902", "1001", "1002", "1101", "1102"]   # el profesor los edita en el panel

SECRETO: bytes = b""   # clave para firmar cookies; se carga al arrancar

# ----------------------------------------------------------------------
# Base de datos SQLite
# ----------------------------------------------------------------------
_AHORA = f"strftime('%Y-%m-%d %H:%M:%S', 'now', '{TZ_OFFSET_HORAS:+d} hours')"   # hora de Colombia, no la del servidor
_CATEGORIAS_SQL = ", ".join(f"'{c}'" for c in catalogo.CATEGORIAS)

SQL_ESQUEMA = f"""
CREATE TABLE IF NOT EXISTS config (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS administradores (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario    TEXT NOT NULL UNIQUE COLLATE NOCASE,
    nombre     TEXT NOT NULL,
    clave_hash TEXT NOT NULL,
    rol        TEXT NOT NULL CHECK (rol IN ('principal', 'admin')),
    activo     INTEGER NOT NULL DEFAULT 1,
    creado     TEXT NOT NULL DEFAULT ({_AHORA})
);

CREATE TABLE IF NOT EXISTS cursos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre      TEXT NOT NULL UNIQUE,
    estudiantes INTEGER,                         -- opcional: sirve para un ranking justo (residuos por estudiante)
    activo      INTEGER NOT NULL DEFAULT 1
);

-- Un reporte = una foto enviada por un estudiante
CREATE TABLE IF NOT EXISTS reportes (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario        TEXT NOT NULL,
    curso          TEXT NOT NULL,
    fecha_hora     TEXT NOT NULL DEFAULT ({_AHORA}),
    nombre_archivo TEXT NOT NULL,
    estado         TEXT NOT NULL CHECK (estado IN ('ok', 'sin_identificar')),
    modo_ia        TEXT NOT NULL
);

-- Un registro por cada residuo clasificado (una foto puede tener varios)
CREATE TABLE IF NOT EXISTS historial_residuos (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    reporte_id        INTEGER NOT NULL REFERENCES reportes(id) ON DELETE CASCADE,
    usuario           TEXT NOT NULL,
    curso             TEXT NOT NULL,
    residuo           TEXT NOT NULL,
    categoria_residuo TEXT NOT NULL CHECK (categoria_residuo IN ({_CATEGORIAS_SQL})),
    confianza         REAL,
    fecha_hora        TEXT NOT NULL DEFAULT ({_AHORA}),
    nombre_archivo    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_reportes_curso ON reportes (curso);
CREATE INDEX IF NOT EXISTS idx_reportes_fecha ON reportes (fecha_hora);
CREATE INDEX IF NOT EXISTS idx_hist_curso ON historial_residuos (curso);
CREATE INDEX IF NOT EXISTS idx_hist_fecha ON historial_residuos (fecha_hora);
CREATE INDEX IF NOT EXISTS idx_hist_reporte ON historial_residuos (reporte_id);
"""


def obtener_conexion() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def db_all(sql: str, params=()) -> List[dict]:
    with closing(obtener_conexion()) as conn:
        return [dict(f) for f in conn.execute(sql, params).fetchall()]


def db_one(sql: str, params=()) -> Optional[dict]:
    filas = db_all(sql, params)
    return filas[0] if filas else None


def db_exec(sql: str, params=()) -> int:
    with closing(obtener_conexion()) as conn:
        cursor = conn.execute(sql, params)
        conn.commit()
        return cursor.lastrowid


def cfg_get(clave: str) -> Optional[str]:
    fila = db_one("SELECT valor FROM config WHERE clave = ?", (clave,))
    return fila["valor"] if fila else None


def cfg_set(clave: str, valor: str) -> None:
    db_exec("INSERT INTO config (clave, valor) VALUES (?, ?) "
            "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor", (clave, valor))


# ----------------------------------------------------------------------
# Contraseñas y cookies firmadas (solo librería estándar)
# ----------------------------------------------------------------------
ITERACIONES = 240_000


def hashear_clave(clave: str) -> str:
    sal = os.urandom(16)
    h = hashlib.pbkdf2_hmac("sha256", clave.encode(), sal, ITERACIONES)
    return f"pbkdf2${ITERACIONES}${sal.hex()}${h.hex()}"


def verificar_clave(clave: str, guardado: str) -> bool:
    try:
        _, iteraciones, sal, esperado = guardado.split("$")
        h = hashlib.pbkdf2_hmac("sha256", clave.encode(), bytes.fromhex(sal), int(iteraciones))
        return hmac.compare_digest(h.hex(), esperado)
    except (ValueError, TypeError):
        return False


def firmar(datos: dict, dias: float) -> str:
    datos = {**datos, "exp": int(time.time() + dias * 86400)}
    cuerpo = base64.urlsafe_b64encode(json.dumps(datos, separators=(",", ":")).encode()).decode().rstrip("=")
    firma = hmac.new(SECRETO, cuerpo.encode(), hashlib.sha256).hexdigest()
    return f"{cuerpo}.{firma}"


def leer_firmado(token: Optional[str]) -> Optional[dict]:
    """Devuelve los datos de una cookie firmada, o None si es falsa, está alterada o venció."""
    if not token or "." not in token:
        return None
    cuerpo, firma = token.rsplit(".", 1)
    esperada = hmac.new(SECRETO, cuerpo.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(firma, esperada):
        return None
    try:
        datos = json.loads(base64.urlsafe_b64decode(cuerpo + "=" * (-len(cuerpo) % 4)))
    except (ValueError, json.JSONDecodeError):
        return None
    return datos if datos.get("exp", 0) > time.time() else None


def poner_cookie(resp: Response, request: Request, nombre: str, valor: str, dias: float, samesite: str) -> None:
    resp.set_cookie(nombre, valor, max_age=int(dias * 86400), httponly=True, samesite=samesite,
                    secure=request.url.scheme == "https", path="/")


# ----------------------------------------------------------------------
# Arranque
# ----------------------------------------------------------------------
def iniciar_base_de_datos() -> None:
    global SECRETO, ADMIN_PASSWORD
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    with closing(obtener_conexion()) as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SQL_ESQUEMA)
        conn.commit()

    # Clave para firmar cookies: se guarda en la BD para que las sesiones sobrevivan a un reinicio
    secreto = os.getenv("SECRET_KEY") or cfg_get("secret_key")
    if not secreto:
        secreto = secrets.token_hex(32)
        cfg_set("secret_key", secreto)
    SECRETO = secreto.encode()

    # Código del QR (se puede renovar desde el panel)
    if not cfg_get("qr_token"):
        cfg_set("qr_token", secrets.token_urlsafe(12))
        cfg_set("qr_version", "1")

    # Cursos de ejemplo la primera vez
    if not db_one("SELECT id FROM cursos LIMIT 1"):
        for nombre in CURSOS_INICIALES:
            db_exec("INSERT INTO cursos (nombre) VALUES (?)", (nombre,))

    # Administrador principal la primera vez
    if not db_one("SELECT id FROM administradores LIMIT 1"):
        clave = ADMIN_PASSWORD
        if not clave:
            clave = secrets.token_urlsafe(10)
            log.warning("No definiste ADMIN_PASSWORD. Administrador principal -> usuario: %s  clave temporal: %s "
                        "(cámbiala al entrar)", ADMIN_USER, clave)
        db_exec("INSERT INTO administradores (usuario, nombre, clave_hash, rol) VALUES (?, ?, ?, 'principal')",
                (ADMIN_USER, ADMIN_NOMBRE, hashear_clave(clave)))


def limpiar_antiguos() -> int:
    """Borra reportes y fotos con más de RETENCION_DIAS días (privacidad)."""
    if RETENCION_DIAS <= 0:
        return 0
    limite = (ahora() - timedelta(days=RETENCION_DIAS)).strftime("%Y-%m-%d %H:%M:%S")
    viejos = db_all("SELECT id, nombre_archivo FROM reportes WHERE fecha_hora < ?", (limite,))
    for fila in viejos:
        (UPLOADS_DIR / fila["nombre_archivo"]).unlink(missing_ok=True)
    db_exec("DELETE FROM reportes WHERE fecha_hora < ?", (limite,))
    if viejos:
        log.info("Se borraron %d reportes con más de %d días.", len(viejos), RETENCION_DIAS)
    return len(viejos)


@asynccontextmanager
async def lifespan(app: FastAPI):
    iniciar_base_de_datos()
    limpiar_antiguos()
    clasificador.cargar_modelo()
    if clasificador.modo() == "ninguno":
        log.warning("No hay modelo de IA ni MODO_DEMO: los estudiantes verán 'detector no disponible'.")
    elif clasificador.modo() == "claude":
        log.info("IA: Claude (%s). Tope diario: %s fotos.", clasificador.CLAUDE_MODELO, LIMITE_DIARIO_IA or "sin tope")
    elif clasificador.modo() == "simulado":
        log.warning("MODO_DEMO activo: los resultados son inventados. No uses esto con estudiantes reales.")
    yield


# Sin /docs, /redoc ni /openapi.json públicos: no hay por qué mostrar la lista de rutas a cualquiera
app = FastAPI(title="EcoQR", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

# Estudiantes y panel se sirven desde el mismo sitio, así que CORS no hace falta.
# Si algún día la app vive en otra dirección, define ALLOWED_ORIGINS (separadas por comas).
if ALLOWED_ORIGINS:
    app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_credentials=True,
                       allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["*"])


@app.middleware("http")
async def cabeceras_de_seguridad(request: Request, call_next):
    respuesta = await call_next(request)
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    respuesta.headers["X-Frame-Options"] = "DENY"
    respuesta.headers["Referrer-Policy"] = "no-referrer"
    respuesta.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' blob: data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; connect-src 'self'; font-src 'self'; "
        "manifest-src 'self'; worker-src 'self'; frame-ancestors 'none'")
    if request.url.path.startswith("/admin/api"):
        respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


# ----------------------------------------------------------------------
# Límites de uso
# ----------------------------------------------------------------------
_limites = defaultdict(deque)


def limitar(clave: str, maximo: int, ventana: float, mensaje: str) -> None:
    ahora = time.monotonic()
    cola = _limites[clave]
    while cola and ahora - cola[0] > ventana:
        cola.popleft()
    if len(cola) >= maximo:
        raise HTTPException(status_code=429, detail=mensaje)
    cola.append(ahora)


def fotos_ia_hoy() -> int:
    """Cuántas fotos se enviaron hoy a la IA de pago (se cuenta en la base de datos, así que sobrevive a reinicios)."""
    hoy = ahora().date().isoformat() + " 00:00:00"
    return db_one("SELECT COUNT(*) AS n FROM reportes WHERE fecha_hora >= ? AND modo_ia = 'claude'", (hoy,))["n"]


def ip_de(request: Request) -> str:
    return request.client.host if request.client else "desconocida"


# ----------------------------------------------------------------------
# Acceso de estudiantes (por QR) y de administradores (por usuario y contraseña)
# ----------------------------------------------------------------------
def acceso_estudiante(request: Request) -> Optional[dict]:
    """Datos de la sesión si el estudiante entró con el QR vigente; si no, None."""
    datos = leer_firmado(request.cookies.get(COOKIE_ESTUDIANTE))
    if not datos or datos.get("t") != "est" or str(datos.get("v")) != (cfg_get("qr_version") or ""):
        return None
    return datos


def exigir_acceso(request: Request) -> dict:
    datos = acceso_estudiante(request)
    if not datos:
        raise HTTPException(status_code=401, detail="Escanea el código QR para entrar.")
    return datos


def exigir_admin(request: Request) -> dict:
    datos = leer_firmado(request.cookies.get(COOKIE_ADMIN))
    if not datos or datos.get("t") != "adm":
        raise HTTPException(status_code=401, detail="Inicia sesión para continuar.")
    fila = db_one("SELECT id, usuario, nombre, rol, activo, clave_hash FROM administradores WHERE id = ?",
                  (datos.get("id"),))
    # 'ch' cambia cuando se cambia la contraseña: así se cierran las sesiones viejas
    if not fila or not fila["activo"] or datos.get("ch") != fila["clave_hash"][-12:]:
        raise HTTPException(status_code=401, detail="Tu sesión venció. Inicia sesión de nuevo.")
    return {"id": fila["id"], "usuario": fila["usuario"], "nombre": fila["nombre"], "rol": fila["rol"]}


def exigir_principal(admin: dict = Depends(exigir_admin)) -> dict:
    if admin["rol"] != "principal":
        raise HTTPException(status_code=403, detail="Solo el administrador principal puede hacer esto.")
    return admin


# ----------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------
def detectar_tipo_imagen(datos: bytes) -> Optional[str]:
    """Identifica JPG/PNG/WebP por su contenido real (el tipo que declara el navegador se puede falsear)."""
    if datos.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if datos.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if datos[:4] == b"RIFF" and datos[8:12] == b"WEBP":
        return ".webp"
    return None


def limpiar_foto(datos: bytes) -> bytes:
    """
    Abre la foto de verdad (si no es una imagen válida, falla), corrige la rotación del celular, la reduce
    y la guarda de nuevo como JPEG. Así se borran los datos EXIF (ubicación GPS, modelo del celular, etc.).
    """
    from PIL import Image, ImageOps

    Image.MAX_IMAGE_PIXELS = 50_000_000     # protege contra imágenes gigantes hechas a propósito
    try:
        with Image.open(io.BytesIO(datos)) as img:
            img = ImageOps.exif_transpose(img).convert("RGB")
            img.thumbnail((1600, 1600))
            salida = io.BytesIO()
            img.save(salida, format="JPEG", quality=88)
            return salida.getvalue()
    except Exception:
        raise HTTPException(status_code=422, detail="No se pudo leer la foto. Toma otra.")


def parsear_fecha(valor: Optional[str], nombre: str) -> Optional[date]:
    if not valor:
        return None
    try:
        return date.fromisoformat(valor)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"'{nombre}' debe tener el formato AAAA-MM-DD.")


def construir_filtros(desde: Optional[str], hasta: Optional[str], curso: Optional[str]) -> Tuple[List[str], list]:
    """Condiciones SQL con parámetros (sin concatenar texto del usuario). Sirven para reportes e historial."""
    condiciones, parametros = [], []
    d, h = parsear_fecha(desde, "desde"), parsear_fecha(hasta, "hasta")
    if d:
        condiciones.append("fecha_hora >= ?")
        parametros.append(d.isoformat() + " 00:00:00")
    if h:
        condiciones.append("fecha_hora < ?")
        parametros.append((h + timedelta(days=1)).isoformat() + " 00:00:00")
    if curso:
        condiciones.append("curso = ?")
        parametros.append(curso)
    return condiciones, parametros


def where(condiciones: List[str], extra: Optional[str] = None) -> str:
    todas = condiciones + ([extra] if extra else [])
    return (" WHERE " + " AND ".join(todas)) if todas else ""


def celda_segura(valor) -> str:
    """Evita 'inyección de fórmulas' en Excel: un nombre como =CMD(...) se vuelve texto inofensivo."""
    texto = "" if valor is None else str(valor)
    return "'" + texto if texto[:1] in ("=", "+", "-", "@", "\t", "\r") else texto


def url_del_qr(request: Request) -> str:
    base = PUBLIC_URL or str(request.base_url).rstrip("/")
    return f"{base}/q/{cfg_get('qr_token')}"


# ======================================================================
# RUTAS DE ESTUDIANTES
# ======================================================================
def _pagina_simple(titulo: str, mensaje: str, codigo: int) -> HTMLResponse:
    html = (f'<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{titulo}</title><body style="font-family:system-ui;background:#f2f5f3;color:#14342b;margin:0;display:grid;'
            f'place-items:center;min-height:100vh;padding:24px;text-align:center"><main><h1>{titulo}</h1><p>{mensaje}</p></main>')
    return HTMLResponse(html, status_code=codigo)


@app.get("/q/{token}", include_in_schema=False)
def entrar_con_qr(token: str, request: Request):
    """El código QR apunta aquí. Si es el vigente, el estudiante queda con acceso por 30 días."""
    if not secrets.compare_digest(token.encode(), (cfg_get("qr_token") or "").encode()):
        return _pagina_simple("Este código QR ya no es válido",
                              "Pide al profesor el código QR nuevo, que está junto a las canecas.", 403)
    resp = RedirectResponse("/", status_code=303)
    valor = firmar({"t": "est", "v": cfg_get("qr_version"), "sid": secrets.token_hex(8)}, dias=30)
    poner_cookie(resp, request, COOKIE_ESTUDIANTE, valor, 30, "lax")
    return resp


@app.get("/api/inicio")
def inicio(request: Request):
    """La app pregunta qué mostrar: la pantalla de 'escanea el QR' o el formulario."""
    if not acceso_estudiante(request):
        return {"acceso": False}
    cursos = [f["nombre"] for f in db_all("SELECT nombre FROM cursos WHERE activo = 1 ORDER BY id")]
    return {"acceso": True, "cursos": cursos, "ia": clasificador.modo(), "varios": clasificador.detecta_varios()}


def agrupar(detecciones: List[dict]) -> List[dict]:
    """Junta residuos repetidos (dos botellas = Botella x2) y añade caneca y explicación."""
    grupos = {}
    for d in detecciones:
        g = grupos.setdefault(d["residuo"], {"cantidad": 0, "confianza": None})
        g["cantidad"] += 1
        if d.get("confianza") is not None:
            g["confianza"] = max(g["confianza"] or 0, d["confianza"])
    return [{**catalogo.datos_residuo(clave), **datos} for clave, datos in grupos.items()]


@app.post("/api/reportar")
async def reportar(
    request: Request,
    usuario: str = Form(..., max_length=80),
    curso: str = Form(..., max_length=40),
    foto: UploadFile = File(...),
    consentimiento: bool = Form(False),
    sesion: dict = Depends(exigir_acceso),
):
    """Recibe la foto, identifica los residuos y guarda el reporte."""
    limitar(f"sesion:{sesion.get('sid')}", LIMITE_SESION, 60, "Vas muy rápido. Espera un momento e inténtalo de nuevo.")
    limitar(f"ip:{ip_de(request)}", LIMITE_IP, 60, "Hay mucho tráfico ahora mismo. Inténtalo en un minuto.")

    usuario, curso = usuario.strip(), curso.strip()
    if not usuario or not curso:
        raise HTTPException(status_code=422, detail="Faltan el nombre o el curso.")
    if not consentimiento:
        raise HTTPException(status_code=422, detail="Debes aceptar el uso de tus datos para enviar el reporte.")
    if not db_one("SELECT id FROM cursos WHERE nombre = ? AND activo = 1", (curso,)):
        raise HTTPException(status_code=422, detail="Ese curso no existe. Elige uno de la lista.")
    if clasificador.modo() == "ninguno":
        raise HTTPException(status_code=503, detail="El detector todavía no está listo. Avisa al profesor.")
    if clasificador.modo() == "claude" and LIMITE_DIARIO_IA and fotos_ia_hoy() >= LIMITE_DIARIO_IA:
        raise HTTPException(status_code=429, detail="Hoy se alcanzó el límite de fotos de la app. Inténtalo mañana.")

    contenido = await foto.read(TAMANO_MAXIMO + 1)
    if len(contenido) > TAMANO_MAXIMO:
        raise HTTPException(status_code=413, detail="La foto pesa demasiado.")
    if detectar_tipo_imagen(contenido) is None:
        raise HTTPException(status_code=415, detail="La foto debe ser JPG, PNG o WebP.")
    contenido = await run_in_threadpool(limpiar_foto, contenido)    # reducida y sin datos EXIF

    nombre_archivo = f"{uuid.uuid4().hex}.jpg"           # nunca usamos el nombre original
    ruta = UPLOADS_DIR / nombre_archivo
    ruta.write_bytes(contenido)

    try:
        detecciones = await run_in_threadpool(clasificador.detectar, ruta)   # la API tarda: no bloquea a los demás
    except ValueError as e:
        ruta.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError:
        ruta.unlink(missing_ok=True)
        raise HTTPException(status_code=503, detail="El detector todavía no está listo. Avisa al profesor.")

    estado = "ok" if detecciones else "sin_identificar"
    reporte_id = db_exec(
        "INSERT INTO reportes (usuario, curso, nombre_archivo, estado, modo_ia) VALUES (?, ?, ?, ?, ?)",
        (usuario, curso, nombre_archivo, estado, clasificador.modo()))
    for d in detecciones:
        info = catalogo.RESIDUOS[d["residuo"]]
        db_exec("INSERT INTO historial_residuos (reporte_id, usuario, curso, residuo, categoria_residuo, confianza, nombre_archivo) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (reporte_id, usuario, curso, d["residuo"], info["categoria"], d.get("confianza"), nombre_archivo))

    return {"id": reporte_id, "estado": estado, "modo": clasificador.modo(), "residuos": agrupar(detecciones)}


@app.get("/salud", include_in_schema=False)
def salud():
    """Para que la plataforma de despliegue sepa que el servidor está vivo."""
    return {"estado": "ok", "ia": clasificador.modo()}


# ======================================================================
# RUTAS DE ADMINISTRACIÓN
# ======================================================================
class Login(BaseModel):
    usuario: str = Field(max_length=60)
    clave: str = Field(max_length=200)


@app.post("/admin/api/login")
def login(datos: Login, request: Request):
    clave_limite = f"login:{ip_de(request)}:{datos.usuario.lower()}"
    cola = _limites[clave_limite]
    ahora = time.monotonic()
    while cola and ahora - cola[0] > 600:
        cola.popleft()
    if len(cola) >= INTENTOS_LOGIN:
        raise HTTPException(status_code=429, detail="Demasiados intentos. Espera 10 minutos.")

    fila = db_one("SELECT * FROM administradores WHERE usuario = ?", (datos.usuario.strip(),))
    # Se verifica siempre algo, para que la respuesta tarde igual exista o no el usuario
    guardado = fila["clave_hash"] if fila else hashear_clave("relleno")
    correcto = verificar_clave(datos.clave, guardado) and fila is not None and bool(fila["activo"])
    if not correcto:
        cola.append(ahora)
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos.")
    cola.clear()

    resp = Response(content=json.dumps({"usuario": fila["usuario"], "nombre": fila["nombre"], "rol": fila["rol"]}),
                    media_type="application/json")
    valor = firmar({"t": "adm", "id": fila["id"], "ch": fila["clave_hash"][-12:]}, dias=1)
    poner_cookie(resp, request, COOKIE_ADMIN, valor, 1, "strict")
    return resp


@app.post("/admin/api/logout")
def logout():
    resp = Response(content=json.dumps({"ok": True}), media_type="application/json")
    resp.delete_cookie(COOKIE_ADMIN, path="/")
    return resp


@app.get("/admin/api/yo")
def yo(admin: dict = Depends(exigir_admin)):
    return admin


class CambioClave(BaseModel):
    actual: str = Field(max_length=200)
    nueva: str = Field(min_length=8, max_length=200)


@app.post("/admin/api/cambiar-clave")
def cambiar_clave(datos: CambioClave, request: Request, admin: dict = Depends(exigir_admin)):
    fila = db_one("SELECT clave_hash FROM administradores WHERE id = ?", (admin["id"],))
    if not verificar_clave(datos.actual, fila["clave_hash"]):
        raise HTTPException(status_code=403, detail="La contraseña actual no es correcta.")
    nuevo = hashear_clave(datos.nueva)
    db_exec("UPDATE administradores SET clave_hash = ? WHERE id = ?", (nuevo, admin["id"]))
    resp = Response(content=json.dumps({"ok": True}), media_type="application/json")
    poner_cookie(resp, request, COOKIE_ADMIN, firmar({"t": "adm", "id": admin["id"], "ch": nuevo[-12:]}, dias=1), 1, "strict")
    return resp


# ---------- Estadísticas ----------
@app.get("/admin/api/resumen")
def resumen(desde: Optional[str] = None, hasta: Optional[str] = None, curso: Optional[str] = None,
            _: dict = Depends(exigir_admin)):
    cond, par = construir_filtros(desde, hasta, curso)
    w = where(cond)

    total_residuos = db_one(f"SELECT COUNT(*) AS n FROM historial_residuos{w}", par)["n"]
    total_reportes = db_one(f"SELECT COUNT(*) AS n FROM reportes{w}", par)["n"]
    w_sin_id = where(cond, "estado = 'sin_identificar'")
    sin_identificar = db_one(f"SELECT COUNT(*) AS n FROM reportes{w_sin_id}", par)["n"]
    participantes = db_one(f"SELECT COUNT(DISTINCT lower(trim(usuario))) AS n FROM reportes{w}", par)["n"]

    por_categoria = {c: 0 for c in catalogo.CATEGORIAS}
    for f in db_all(f"SELECT categoria_residuo AS k, COUNT(*) AS n FROM historial_residuos{w} GROUP BY categoria_residuo", par):
        por_categoria[f["k"]] = f["n"]
    por_residuo = {catalogo.nombre_legible(f["k"]): f["n"] for f in db_all(
        f"SELECT residuo AS k, COUNT(*) AS n FROM historial_residuos{w} GROUP BY residuo ORDER BY n DESC", par)}
    por_curso = {f["k"]: f["n"] for f in db_all(
        f"SELECT curso AS k, COUNT(*) AS n FROM historial_residuos{w} GROUP BY curso ORDER BY n DESC", par)}
    por_dia = {f["k"]: f["n"] for f in db_all(
        f"SELECT substr(fecha_hora, 1, 10) AS k, COUNT(*) AS n FROM historial_residuos{w} GROUP BY k ORDER BY k", par)}

    return {"total_residuos": total_residuos, "total_reportes": total_reportes, "sin_identificar": sin_identificar,
            "participantes": participantes, "por_categoria": por_categoria, "por_residuo": por_residuo,
            "por_curso": por_curso, "por_dia": por_dia}


@app.get("/admin/api/ranking")
def ranking(desde: Optional[str] = None, hasta: Optional[str] = None, curso: Optional[str] = None,
            _: dict = Depends(exigir_admin)):
    """Ranking por salón. Si todos los cursos tienen número de estudiantes, se ordena por residuos por estudiante (más justo)."""
    cond, par = construir_filtros(desde, hasta, None)   # el ranking compara cursos, no se filtra por uno
    w = where(cond)
    residuos = {f["curso"]: f for f in db_all(
        f"SELECT curso, COUNT(*) AS residuos, SUM(categoria_residuo = 'Aprovechable') AS aprovechables "
        f"FROM historial_residuos{w} GROUP BY curso", par)}
    reportes = {f["curso"]: f for f in db_all(
        f"SELECT curso, COUNT(*) AS reportes, COUNT(DISTINCT lower(trim(usuario))) AS participantes "
        f"FROM reportes{w} GROUP BY curso", par)}
    cursos = db_all("SELECT nombre, estudiantes FROM cursos WHERE activo = 1 ORDER BY id")
    nombres = [c["nombre"] for c in cursos] + [n for n in list(residuos) + list(reportes) if n not in {c["nombre"] for c in cursos}]
    estudiantes = {c["nombre"]: c["estudiantes"] for c in cursos}

    filas = []
    for n in dict.fromkeys(nombres):
        r, p = residuos.get(n, {}), reportes.get(n, {})
        total = r.get("residuos", 0)
        est = estudiantes.get(n)
        filas.append({"curso": n, "residuos": total, "reportes": p.get("reportes", 0),
                      "participantes": p.get("participantes", 0), "estudiantes": est,
                      "por_estudiante": round(total / est, 2) if est else None,
                      "pct_aprovechable": round(100 * (r.get("aprovechables") or 0) / total) if total else None})
    justo = bool(cursos) and all(c["estudiantes"] for c in cursos)
    filas.sort(key=lambda f: (f["por_estudiante"] or 0) if justo else f["residuos"], reverse=True)
    for i, f in enumerate(filas, 1):
        f["posicion"] = i
    return {"criterio": "por_estudiante" if justo else "total", "filas": filas}


@app.get("/admin/api/actividad")
def actividad(desde: Optional[str] = None, hasta: Optional[str] = None, curso: Optional[str] = None,
              limite: int = Query(100, ge=1, le=1000), desplazamiento: int = Query(0, ge=0),
              _: dict = Depends(exigir_admin)):
    """Historial de actividad: cada foto enviada con lo que se identificó."""
    cond, par = construir_filtros(desde, hasta, curso)
    filas = db_all(
        "SELECT r.id, r.fecha_hora, r.usuario, r.curso, r.estado, r.nombre_archivo, r.modo_ia, "
        "(SELECT group_concat(residuo, ',') FROM historial_residuos h WHERE h.reporte_id = r.id) AS residuos "
        f"FROM reportes r{where(cond)} ORDER BY r.id DESC LIMIT ? OFFSET ?", par + [limite, desplazamiento])
    for f in filas:
        conteo = {}
        for clave in (f["residuos"] or "").split(","):
            if clave:
                conteo[clave] = conteo.get(clave, 0) + 1
        f["residuos"] = [{"nombre": catalogo.nombre_legible(k), "cantidad": n} for k, n in conteo.items()]
    return filas


@app.get("/admin/api/exportar.csv")
def exportar_csv(desde: Optional[str] = None, hasta: Optional[str] = None, curso: Optional[str] = None,
                 _: dict = Depends(exigir_admin)):
    """Un renglón por residuo clasificado (abre bien en Excel)."""
    cond, par = construir_filtros(desde, hasta, curso)
    filas = db_all("SELECT id, reporte_id, fecha_hora, usuario, curso, residuo, categoria_residuo, confianza, nombre_archivo "
                   f"FROM historial_residuos{where(cond)} ORDER BY id", par)
    salida = io.StringIO()
    salida.write("\ufeff")  # marca UTF-8 para que Excel muestre bien las tildes
    escritor = csv.writer(salida)
    escritor.writerow(["id", "reporte", "fecha_hora", "estudiante", "curso", "residuo", "categoria", "caneca", "confianza", "archivo"])
    for f in filas:
        escritor.writerow([celda_segura(v) for v in (
            f["id"], f["reporte_id"], f["fecha_hora"], f["usuario"], f["curso"], catalogo.nombre_legible(f["residuo"]),
            f["categoria_residuo"], catalogo.CANECA_POR_CATEGORIA[f["categoria_residuo"]], f["confianza"], f["nombre_archivo"])])
    nombre = f"ecoqr-{ahora():%Y%m%d-%H%M}.csv"
    return Response(content=salida.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@app.get("/admin/api/foto/{nombre}")
def ver_foto(nombre: str, _: dict = Depends(exigir_admin)):
    if not NOMBRE_FOTO.fullmatch(nombre):          # bloquea rutas como ../../etc/passwd
        raise HTTPException(status_code=404)
    ruta = UPLOADS_DIR / nombre
    if not ruta.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(ruta, headers={"Cache-Control": "private, max-age=3600"})


@app.delete("/admin/api/reportes/{reporte_id}")
def borrar_reporte(reporte_id: int, _: dict = Depends(exigir_principal)):
    fila = db_one("SELECT nombre_archivo FROM reportes WHERE id = ?", (reporte_id,))
    if not fila:
        raise HTTPException(status_code=404, detail="No existe ese reporte.")
    (UPLOADS_DIR / fila["nombre_archivo"]).unlink(missing_ok=True)
    db_exec("DELETE FROM reportes WHERE id = ?", (reporte_id,))   # borra también sus residuos (CASCADE)
    return {"ok": True}


@app.get("/admin/api/estado")
def estado_del_sistema(_: dict = Depends(exigir_admin)):
    """Para supervisar el funcionamiento de la aplicación."""
    hoy = ahora().date().isoformat() + " 00:00:00"
    total = db_one("SELECT COUNT(*) AS n FROM reportes")["n"]
    sin_id = db_one("SELECT COUNT(*) AS n FROM reportes WHERE estado = 'sin_identificar'")["n"]
    disco = shutil.disk_usage(DATA_DIR)
    return {
        "ia": clasificador.modo(),
        "detecta_varios": clasificador.detecta_varios(),
        "umbral_confianza": clasificador.UMBRAL_CONFIANZA,
        "limite_diario_ia": LIMITE_DIARIO_IA,
        "fotos_ia_hoy": fotos_ia_hoy(),
        "reportes_totales": total,
        "reportes_hoy": db_one("SELECT COUNT(*) AS n FROM reportes WHERE fecha_hora >= ?", (hoy,))["n"],
        "pct_sin_identificar": round(100 * sin_id / total) if total else None,
        "fotos_guardadas": sum(1 for _ in UPLOADS_DIR.glob("*")),
        "base_de_datos_kb": round(DB_PATH.stat().st_size / 1024),
        "disco_libre_mb": round(disco.free / 1024 / 1024),
        "retencion_dias": RETENCION_DIAS,
        "hora_servidor": ahora().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ---------- Cursos ----------
class CursoNuevo(BaseModel):
    nombre: str = Field(min_length=1, max_length=40)
    estudiantes: Optional[int] = Field(default=None, ge=1, le=500)


class CursoCambio(BaseModel):
    nombre: Optional[str] = Field(default=None, min_length=1, max_length=40)
    estudiantes: Optional[int] = Field(default=None, ge=1, le=500)
    activo: Optional[bool] = None


@app.get("/admin/api/cursos")
def listar_cursos(_: dict = Depends(exigir_admin)):
    return db_all("SELECT id, nombre, estudiantes, activo FROM cursos ORDER BY id")


@app.post("/admin/api/cursos", status_code=201)
def crear_curso(datos: CursoNuevo, _: dict = Depends(exigir_principal)):
    nombre = datos.nombre.strip()
    if db_one("SELECT id FROM cursos WHERE nombre = ?", (nombre,)):
        raise HTTPException(status_code=409, detail="Ya existe un curso con ese nombre.")
    return {"id": db_exec("INSERT INTO cursos (nombre, estudiantes) VALUES (?, ?)", (nombre, datos.estudiantes))}


@app.patch("/admin/api/cursos/{curso_id}")
def editar_curso(curso_id: int, datos: CursoCambio, _: dict = Depends(exigir_principal)):
    if not db_one("SELECT id FROM cursos WHERE id = ?", (curso_id,)):
        raise HTTPException(status_code=404, detail="No existe ese curso.")
    if datos.nombre is not None:
        nombre = datos.nombre.strip()
        if db_one("SELECT id FROM cursos WHERE nombre = ? AND id != ?", (nombre, curso_id)):
            raise HTTPException(status_code=409, detail="Ya existe un curso con ese nombre.")
        db_exec("UPDATE cursos SET nombre = ? WHERE id = ?", (nombre, curso_id))
    if datos.estudiantes is not None:
        db_exec("UPDATE cursos SET estudiantes = ? WHERE id = ?", (datos.estudiantes, curso_id))
    if datos.activo is not None:
        db_exec("UPDATE cursos SET activo = ? WHERE id = ?", (int(datos.activo), curso_id))
    return {"ok": True}


# ---------- Administradores (solo el principal) ----------
class AdminNuevo(BaseModel):
    usuario: str = Field(min_length=3, max_length=40, pattern=r"^[A-Za-z0-9_.\-]+$")
    nombre: str = Field(min_length=1, max_length=80)
    clave: str = Field(min_length=8, max_length=200)


class AdminCambio(BaseModel):
    activo: Optional[bool] = None
    clave: Optional[str] = Field(default=None, min_length=8, max_length=200)


@app.get("/admin/api/administradores")
def listar_admins(_: dict = Depends(exigir_principal)):
    return db_all("SELECT id, usuario, nombre, rol, activo, creado FROM administradores ORDER BY id")


@app.post("/admin/api/administradores", status_code=201)
def crear_admin(datos: AdminNuevo, _: dict = Depends(exigir_principal)):
    if db_one("SELECT id FROM administradores WHERE usuario = ?", (datos.usuario,)):
        raise HTTPException(status_code=409, detail="Ese usuario ya existe.")
    nuevo = db_exec("INSERT INTO administradores (usuario, nombre, clave_hash, rol) VALUES (?, ?, ?, 'admin')",
                    (datos.usuario, datos.nombre.strip(), hashear_clave(datos.clave)))
    return {"id": nuevo}


@app.patch("/admin/api/administradores/{admin_id}")
def editar_admin(admin_id: int, datos: AdminCambio, yo_: dict = Depends(exigir_principal)):
    fila = db_one("SELECT id, rol FROM administradores WHERE id = ?", (admin_id,))
    if not fila:
        raise HTTPException(status_code=404, detail="No existe ese administrador.")
    if datos.activo is False and fila["id"] == yo_["id"]:
        raise HTTPException(status_code=400, detail="No puedes desactivar tu propia cuenta.")
    if datos.activo is not None:
        db_exec("UPDATE administradores SET activo = ? WHERE id = ?", (int(datos.activo), admin_id))
    if datos.clave is not None:
        db_exec("UPDATE administradores SET clave_hash = ? WHERE id = ?", (hashear_clave(datos.clave), admin_id))
    return {"ok": True}


# ---------- Código QR (solo el principal) ----------
def _svg_qr(url: str) -> str:
    buf = io.BytesIO()
    segno.make(url, error="q").save(buf, kind="svg", scale=10, border=3, xmldecl=False, nl=False)
    return buf.getvalue().decode("utf-8")


@app.get("/admin/api/qr")
def ver_qr(request: Request, _: dict = Depends(exigir_principal)):
    url = url_del_qr(request)
    return {"url": url, "svg": _svg_qr(url), "version": int(cfg_get("qr_version") or 1),
            "direccion_publica_configurada": bool(PUBLIC_URL)}


@app.post("/admin/api/qr/renovar")
def renovar_qr(request: Request, _: dict = Depends(exigir_principal)):
    """Genera un QR nuevo. El anterior deja de funcionar y todos deben escanear de nuevo."""
    cfg_set("qr_token", secrets.token_urlsafe(12))
    cfg_set("qr_version", str(int(cfg_get("qr_version") or 1) + 1))
    return ver_qr(request, _)


# ======================================================================
# PÁGINAS Y ARCHIVOS DE LA PWA
# ======================================================================
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.get("/", include_in_schema=False)
def pagina_app():
    return FileResponse(BASE_DIR / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/admin", include_in_schema=False)
def pagina_admin():
    # La página no tiene datos: los datos solo llegan por /admin/api/*, que sí exige sesión
    return FileResponse(BASE_DIR / "admin.html", headers={"Cache-Control": "no-store"})


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifiesto():
    return FileResponse(BASE_DIR / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    return FileResponse(BASE_DIR / "sw.js", media_type="application/javascript",
                        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})
