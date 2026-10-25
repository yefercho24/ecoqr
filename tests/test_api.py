import pytest
import sqlite3
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

import catalogo
import clasificador
import main
from conftest import JPG, JPG_CON_EXIF, JPG_GRANDE, PNG, PRINCIPAL, WEBP, crear_admin_secundario, enviar


# =============== Entrada por QR ===============
def test_sin_qr_no_hay_acceso(anonimo):
    assert anonimo.get("/api/inicio").json() == {"acceso": False}
    assert enviar(anonimo).status_code == 401


def test_qr_valido_da_acceso_y_lista_cursos(app_lista):
    c = TestClient(app_lista)
    r = c.get(f"/q/{main.cfg_get('qr_token')}", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    datos = c.get("/api/inicio").json()
    assert datos["acceso"] is True and datos["cursos"] == main.CURSOS_INICIALES


def test_qr_falso_es_rechazado(anonimo):
    r = anonimo.get("/q/codigo-inventado", follow_redirects=False)
    assert r.status_code == 403
    assert anonimo.get("/api/inicio").json()["acceso"] is False


def test_cookie_falsificada_no_sirve(anonimo):
    anonimo.cookies.set(main.COOKIE_ESTUDIANTE, "eyJ0IjoiZXN0In0.firmafalsa")
    assert anonimo.get("/api/inicio").json()["acceso"] is False


def test_renovar_qr_invalida_los_accesos_anteriores(estudiante, admin):
    assert estudiante.get("/api/inicio").json()["acceso"] is True
    viejo = main.cfg_get("qr_token")
    assert admin.post("/admin/api/qr/renovar").status_code == 200
    assert main.cfg_get("qr_token") != viejo
    assert estudiante.get("/api/inicio").json()["acceso"] is False
    assert TestClient(main.app).get(f"/q/{viejo}", follow_redirects=False).status_code == 403


# =============== Envío de reportes ===============
def test_reporte_valido_devuelve_residuos_con_caneca_y_explicacion(estudiante):
    r = enviar(estudiante)
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["estado"] == "ok" and cuerpo["residuos"]
    for x in cuerpo["residuos"]:
        assert x["caneca"] in ("blanca", "negra", "verde")
        assert x["explicacion"] and x["cantidad"] >= 1


def test_acepta_png_y_webp(estudiante):
    assert enviar(estudiante, foto=PNG, nombre="f.png", tipo="image/png").status_code == 200
    assert enviar(estudiante, foto=WEBP, nombre="f.webp", tipo="image/webp").status_code == 200


def test_rechaza_archivo_que_no_es_imagen_aunque_diga_serlo(estudiante):
    assert enviar(estudiante, foto=b"<script>alert(1)</script>").status_code == 415


def test_exige_consentimiento_nombre_y_curso_valido(estudiante):
    assert enviar(estudiante, consentimiento="false").status_code == 422
    assert enviar(estudiante, usuario="   ").status_code == 422
    assert enviar(estudiante, curso="curso-que-no-existe").status_code == 422


def test_rechaza_foto_demasiado_grande(estudiante):
    assert enviar(estudiante, foto=b"\xff\xd8\xff" + b"0" * (main.TAMANO_MAXIMO + 10)).status_code == 413


def test_limite_por_sesion_no_castiga_a_otros_estudiantes(app_lista):
    """Todos comparten la IP del WiFi del colegio: el límite principal es por estudiante."""
    def nuevo():
        c = TestClient(app_lista)
        c.get(f"/q/{main.cfg_get('qr_token')}", follow_redirects=False)
        return c
    a, b = nuevo(), nuevo()
    codigos = [enviar(a).status_code for _ in range(main.LIMITE_SESION + 1)]
    assert codigos[:-1] == [200] * main.LIMITE_SESION and codigos[-1] == 429
    assert enviar(b).status_code == 200        # otro estudiante, misma IP: sigue funcionando


def test_nombre_de_archivo_original_no_se_usa(estudiante, app_lista):
    enviar(estudiante, nombre="../../etc/passwd.jpg")
    archivo = main.db_one("SELECT nombre_archivo FROM reportes")["nombre_archivo"]
    assert main.NOMBRE_FOTO.fullmatch(archivo)


def test_sin_modelo_ni_modo_demo_no_se_inventan_respuestas(estudiante, monkeypatch):
    monkeypatch.setattr(clasificador, "MODO_DEMO", False)
    r = enviar(estudiante)
    assert r.status_code == 503
    assert main.db_one("SELECT COUNT(*) AS n FROM reportes")["n"] == 0


def test_baja_confianza_queda_como_sin_identificar(estudiante, monkeypatch):
    monkeypatch.setattr(clasificador, "detectar", lambda ruta: [])
    r = enviar(estudiante).json()
    assert r["estado"] == "sin_identificar" and r["residuos"] == []
    assert main.db_one("SELECT estado FROM reportes")["estado"] == "sin_identificar"
    assert main.db_one("SELECT COUNT(*) AS n FROM historial_residuos")["n"] == 0


def test_residuos_repetidos_se_agrupan(estudiante, monkeypatch):
    monkeypatch.setattr(clasificador, "detectar", lambda ruta: [
        {"residuo": "botella", "confianza": 0.9}, {"residuo": "botella", "confianza": 0.8}, {"residuo": "papel", "confianza": 0.7}])
    r = enviar(estudiante).json()
    botella = next(x for x in r["residuos"] if x["residuo"] == "botella")
    assert botella["cantidad"] == 2 and botella["caneca"] == "blanca"
    assert main.db_one("SELECT COUNT(*) AS n FROM historial_residuos")["n"] == 3   # un registro por residuo


# =============== Catálogo ===============
def test_catalogo_cubre_los_residuos_y_tres_canecas():
    assert set(catalogo.RESIDUOS) == {"botella", "empaque", "resto_comida", "cascara_fruta", "plastico", "papel", "carton",
                                      "plastico_sucio", "papel_sucio", "carton_sucio"}
    for clave in catalogo.RESIDUOS:
        d = catalogo.datos_residuo(clave)
        assert d["caneca"] in ("blanca", "negra", "verde") and len(d["explicacion"]) > 30
    assert catalogo.datos_residuo("resto_comida")["caneca"] == "verde"
    assert catalogo.datos_residuo("empaque")["caneca"] == "negra"


def test_clave_de_clase_tolera_tildes_y_espacios():
    assert clasificador._clave("Cáscara fruta") == "cascara_fruta"
    assert clasificador._clave("cascara de fruta") == "cascara_fruta"
    assert clasificador._clave(" Resto de comida ") == "resto_comida"


# =============== Administración: sesión y roles ===============
def test_rutas_de_admin_exigen_sesion(anonimo):
    for ruta in ["/admin/api/yo", "/admin/api/resumen", "/admin/api/ranking", "/admin/api/actividad",
                 "/admin/api/exportar.csv", "/admin/api/estado", "/admin/api/cursos", "/admin/api/qr", "/admin/api/administradores"]:
        assert anonimo.get(ruta).status_code == 401, ruta


def test_el_acceso_de_estudiante_no_abre_el_panel(estudiante):
    assert estudiante.get("/admin/api/resumen").status_code == 401


def test_login_correcto_e_incorrecto(app_lista):
    c = TestClient(app_lista)
    assert c.post("/admin/api/login", json={"usuario": "jaime", "clave": "mala"}).status_code == 401
    assert c.post("/admin/api/login", json={"usuario": "nadie", "clave": "x"}).status_code == 401
    r = c.post("/admin/api/login", json=PRINCIPAL)
    assert r.status_code == 200 and r.json()["rol"] == "principal"
    assert c.get("/admin/api/yo").json()["usuario"] == "jaime"


def test_bloqueo_tras_varios_intentos_fallidos(app_lista):
    c = TestClient(app_lista)
    for _ in range(main.INTENTOS_LOGIN):
        assert c.post("/admin/api/login", json={"usuario": "jaime", "clave": "mala"}).status_code == 401
    assert c.post("/admin/api/login", json=PRINCIPAL).status_code == 429


def test_logout_cierra_la_sesion(admin):
    assert admin.post("/admin/api/logout").status_code == 200
    assert admin.get("/admin/api/yo").status_code == 401


def test_el_principal_crea_admins_y_estos_tienen_menos_permisos(admin, app_lista):
    usuario, clave = crear_admin_secundario(admin)
    otro = TestClient(app_lista)
    assert otro.post("/admin/api/login", json={"usuario": usuario, "clave": clave}).status_code == 200
    # Puede ver
    for ruta in ["/admin/api/resumen", "/admin/api/ranking", "/admin/api/actividad", "/admin/api/estado", "/admin/api/cursos"]:
        assert otro.get(ruta).status_code == 200, ruta
    # No puede gestionar
    assert otro.get("/admin/api/administradores").status_code == 403
    assert otro.get("/admin/api/qr").status_code == 403
    assert otro.post("/admin/api/qr/renovar").status_code == 403
    assert otro.post("/admin/api/cursos", json={"nombre": "1201"}).status_code == 403
    assert otro.post("/admin/api/administradores", json={"usuario": "x1234", "nombre": "X", "clave": "12345678"}).status_code == 403


def test_admin_desactivado_pierde_el_acceso(admin, app_lista):
    usuario, clave = crear_admin_secundario(admin)
    otro = TestClient(app_lista)
    otro.post("/admin/api/login", json={"usuario": usuario, "clave": clave})
    pedro = next(a for a in admin.get("/admin/api/administradores").json() if a["usuario"] == usuario)
    assert admin.patch(f"/admin/api/administradores/{pedro['id']}", json={"activo": False}).status_code == 200
    assert otro.get("/admin/api/yo").status_code == 401
    assert otro.post("/admin/api/login", json={"usuario": usuario, "clave": clave}).status_code == 401


def test_el_principal_no_puede_desactivarse_a_si_mismo(admin):
    yo = admin.get("/admin/api/yo").json()
    assert admin.patch(f"/admin/api/administradores/{yo['id']}", json={"activo": False}).status_code == 400


def test_usuario_repetido_y_clave_corta(admin):
    crear_admin_secundario(admin)
    assert admin.post("/admin/api/administradores", json={"usuario": "PEDRO", "nombre": "P", "clave": "12345678"}).status_code == 409
    assert admin.post("/admin/api/administradores", json={"usuario": "nuevo1", "nombre": "N", "clave": "corta"}).status_code == 422


def test_cambiar_clave_cierra_otras_sesiones(admin, app_lista):
    segunda = TestClient(app_lista)
    segunda.post("/admin/api/login", json=PRINCIPAL)
    assert admin.post("/admin/api/cambiar-clave", json={"actual": "mala", "nueva": "otra-clave-9"}).status_code == 403
    assert admin.post("/admin/api/cambiar-clave", json={"actual": PRINCIPAL["clave"], "nueva": "otra-clave-9"}).status_code == 200
    assert admin.get("/admin/api/yo").status_code == 200      # la sesión actual se renueva
    assert segunda.get("/admin/api/yo").status_code == 401    # las demás se cierran
    assert TestClient(app_lista).post("/admin/api/login", json={"usuario": "jaime", "clave": "otra-clave-9"}).status_code == 200


def test_cookies_de_sesion_son_httponly(app_lista):
    r = TestClient(app_lista).post("/admin/api/login", json=PRINCIPAL)
    assert "httponly" in r.headers["set-cookie"].lower() and "samesite=strict" in r.headers["set-cookie"].lower()


# =============== Cursos ===============
def test_gestion_de_cursos(admin, estudiante):
    assert admin.post("/admin/api/cursos", json={"nombre": "1201", "estudiantes": 30}).status_code == 201
    assert admin.post("/admin/api/cursos", json={"nombre": "1201"}).status_code == 409
    curso = next(c for c in admin.get("/admin/api/cursos").json() if c["nombre"] == "1201")
    assert curso["estudiantes"] == 30
    assert "1201" in estudiante.get("/api/inicio").json()["cursos"]
    assert admin.patch(f"/admin/api/cursos/{curso['id']}", json={"activo": False}).status_code == 200
    assert "1201" not in estudiante.get("/api/inicio").json()["cursos"]
    assert enviar(estudiante, curso="1201").status_code == 422


# =============== Estadísticas, ranking y actividad ===============
def _crear_actividad(estudiante, monkeypatch):
    monkeypatch.setattr(clasificador, "detectar", lambda ruta: [{"residuo": "botella", "confianza": 0.9}, {"residuo": "cascara_fruta", "confianza": 0.9}])
    enviar(estudiante, usuario="Ana", curso="801")
    enviar(estudiante, usuario="Luis", curso="801")
    enviar(estudiante, usuario="Ana", curso="901")


def test_resumen_general_y_filtro_por_curso(admin, estudiante, monkeypatch):
    _crear_actividad(estudiante, monkeypatch)
    r = admin.get("/admin/api/resumen").json()
    assert r["total_residuos"] == 6 and r["total_reportes"] == 3 and r["participantes"] == 2
    assert r["por_categoria"] == {"Aprovechable": 3, "No Aprovechable": 0, "Orgánico": 3}
    assert r["por_curso"] == {"801": 4, "901": 2}
    assert r["por_residuo"] == {"Botella": 3, "Cáscara de fruta": 3}
    assert admin.get("/admin/api/resumen?curso=901").json()["total_residuos"] == 2


def test_filtros_de_fecha(admin, estudiante, monkeypatch):
    _crear_actividad(estudiante, monkeypatch)
    hoy = datetime.now().date()
    ayer = (hoy - timedelta(days=1)).isoformat()
    assert admin.get(f"/admin/api/resumen?desde={hoy}&hasta={hoy}").json()["total_reportes"] == 3
    assert admin.get(f"/admin/api/resumen?hasta={ayer}").json()["total_reportes"] == 0
    assert admin.get("/admin/api/resumen?desde=no-es-fecha").status_code == 422


def test_ranking_por_total_y_por_estudiante(admin, estudiante, monkeypatch):
    _crear_actividad(estudiante, monkeypatch)
    r = admin.get("/admin/api/ranking").json()
    assert r["criterio"] == "total"
    assert [f["curso"] for f in r["filas"][:2]] == ["801", "901"] and r["filas"][0]["posicion"] == 1
    assert any(f["curso"] == "802" and f["residuos"] == 0 for f in r["filas"])   # los cursos sin actividad también salen
    # Con el número de estudiantes de TODOS los cursos, el criterio pasa a ser por estudiante
    for c in admin.get("/admin/api/cursos").json():
        admin.patch(f"/admin/api/cursos/{c['id']}", json={"estudiantes": 40 if c["nombre"] == "801" else 10})
    r = admin.get("/admin/api/ranking").json()
    assert r["criterio"] == "por_estudiante"
    assert r["filas"][0]["curso"] == "901"        # 2 residuos / 10 estudiantes supera a 4 / 40


def test_actividad_lista_residuos_por_foto(admin, estudiante, monkeypatch):
    _crear_actividad(estudiante, monkeypatch)
    filas = admin.get("/admin/api/actividad").json()
    assert len(filas) == 3 and {r["nombre"] for r in filas[0]["residuos"]} == {"Botella", "Cáscara de fruta"}
    assert len(admin.get("/admin/api/actividad?curso=901").json()) == 1


def test_csv_con_tildes_caneca_y_formulas_neutralizadas(admin, estudiante, monkeypatch):
    monkeypatch.setattr(clasificador, "detectar", lambda ruta: [{"residuo": "cascara_fruta", "confianza": 0.9}])
    enviar(estudiante, usuario='=HYPERLINK("http://malo")')
    r = admin.get("/admin/api/exportar.csv")
    assert r.headers["content-type"].startswith("text/csv")
    texto = r.content.decode("utf-8-sig")
    assert "Cáscara de fruta" in texto and "verde" in texto
    assert "'=HYPERLINK" in texto and ",=HYPERLINK" not in texto


# =============== Fotos, borrado y privacidad ===============
def test_fotos_son_privadas_y_sin_path_traversal(admin, estudiante, anonimo):
    enviar(estudiante)
    archivo = main.db_one("SELECT nombre_archivo FROM reportes")["nombre_archivo"]
    assert anonimo.get(f"/admin/api/foto/{archivo}").status_code == 401
    assert estudiante.get(f"/admin/api/foto/{archivo}").status_code == 401
    assert admin.get(f"/admin/api/foto/{archivo}").status_code == 200
    assert admin.get("/admin/api/foto/..%2F..%2Fmain.py").status_code == 404
    assert anonimo.get("/uploads/" + archivo).status_code == 404


def test_solo_el_principal_borra_reportes_y_se_borra_la_foto(admin, estudiante, app_lista):
    enviar(estudiante)
    fila = main.db_one("SELECT id, nombre_archivo FROM reportes")
    usuario, clave = crear_admin_secundario(admin)
    otro = TestClient(app_lista)
    otro.post("/admin/api/login", json={"usuario": usuario, "clave": clave})
    assert otro.delete(f"/admin/api/reportes/{fila['id']}").status_code == 403
    assert admin.delete(f"/admin/api/reportes/{fila['id']}").status_code == 200
    assert main.db_one("SELECT COUNT(*) AS n FROM reportes")["n"] == 0
    assert main.db_one("SELECT COUNT(*) AS n FROM historial_residuos")["n"] == 0
    assert not (main.UPLOADS_DIR / fila["nombre_archivo"]).exists()


def test_limpieza_de_reportes_antiguos(estudiante, monkeypatch):
    enviar(estudiante)
    vieja = (datetime.now() - timedelta(days=40)).strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(main.DB_PATH) as conn:
        conn.execute("UPDATE reportes SET fecha_hora = ?", (vieja,))
    enviar(estudiante)
    monkeypatch.setattr(main, "RETENCION_DIAS", 30)
    assert main.limpiar_antiguos() == 1
    assert main.db_one("SELECT COUNT(*) AS n FROM reportes")["n"] == 1


# =============== QR, estado y páginas ===============
def test_qr_del_admin_apunta_a_la_direccion_de_entrada(admin):
    d = admin.get("/admin/api/qr").json()
    assert d["url"].endswith("/q/" + main.cfg_get("qr_token"))
    assert d["svg"].lstrip().startswith("<svg")


def test_estado_del_sistema(admin, estudiante):
    enviar(estudiante)
    e = admin.get("/admin/api/estado").json()
    assert e["ia"] == "simulado" and e["reportes_totales"] == 1 and e["reportes_hoy"] == 1 and e["disco_libre_mb"] > 0


def test_paginas_publicas_de_la_pwa(anonimo):
    assert anonimo.get("/").status_code == 200
    assert anonimo.get("/admin").status_code == 200
    assert anonimo.get("/manifest.webmanifest").headers["content-type"].startswith("application/manifest+json")
    sw = anonimo.get("/sw.js")
    assert sw.status_code == 200 and sw.headers["service-worker-allowed"] == "/"
    assert anonimo.get("/static/icon-512.png").status_code == 200
    assert anonimo.get("/salud").json()["estado"] == "ok"
    assert "frame-ancestors 'none'" in anonimo.get("/").headers["content-security-policy"]


def test_clase_otro_pide_otra_foto(tmp_path, monkeypatch):
    """Si el modelo elige la clase 'otro' (no es un residuo), no se devuelve ningún residuo."""
    import numpy as np
    from PIL import Image

    class FalsoModelo:
        def __init__(self, probs): self.probs = probs
        def predict(self, x, verbose=0): return np.array([self.probs])

    foto = tmp_path / "f.jpg"
    Image.new("RGB", (64, 64), (10, 200, 10)).save(foto)
    monkeypatch.setattr(clasificador, "_clases", ["botella", "papel", "otro"])
    monkeypatch.setattr(clasificador, "_modelo", FalsoModelo([0.05, 0.05, 0.90]))
    assert clasificador.detectar(foto) == []                          # eligió "otro" con mucha seguridad
    monkeypatch.setattr(clasificador, "_modelo", FalsoModelo([0.90, 0.05, 0.05]))
    assert clasificador.detectar(foto)[0]["residuo"] == "botella"     # una clase normal sigue funcionando


# =============== IA con la API de Claude (modo "claude") ===============
class _RespuestaFalsa:
    def __init__(self, estado=200, cuerpo=None, texto=""):
        self.status_code, self._cuerpo, self.text = estado, cuerpo, texto

    def json(self):
        return self._cuerpo


def _foto_grande(tmp_path):
    from PIL import Image
    ruta = tmp_path / "grande.jpg"
    Image.new("RGB", (2000, 1500), (90, 160, 80)).save(ruta)
    return ruta


def test_claude_envia_la_peticion_correcta_y_filtra_la_respuesta(tmp_path, monkeypatch):
    import base64, io
    import httpx
    from PIL import Image

    capturado = {}

    def post_falso(url, headers=None, json=None, timeout=None):
        capturado.update(url=url, headers=headers, cuerpo=json)
        texto = '```json\n{"residuos": ["Botella", "papel", "papel", "lata", "carton"]}\n```'
        return _RespuestaFalsa(200, {"content": [{"type": "text", "text": texto}]})

    monkeypatch.setattr(clasificador, "ANTHROPIC_API_KEY", "clave-falsa")
    monkeypatch.setattr(httpx, "post", post_falso)

    assert clasificador.modo() == "claude" and clasificador.detecta_varios() is True
    r = clasificador.detectar(_foto_grande(tmp_path))
    assert [x["residuo"] for x in r] == ["botella", "papel", "carton"]      # sin repetidos y sin "lata" (no está en el catálogo)

    assert capturado["url"] == "https://api.anthropic.com/v1/messages"
    assert capturado["headers"]["x-api-key"] == "clave-falsa" and capturado["headers"]["anthropic-version"] == "2023-06-01"
    cuerpo = capturado["cuerpo"]
    assert cuerpo["model"] == clasificador.CLAUDE_MODELO and cuerpo["max_tokens"] <= 300
    assert "clave-falsa" not in str(cuerpo)                                   # la clave nunca va dentro del mensaje
    bloque = cuerpo["messages"][0]["content"][0]
    assert bloque["type"] == "image" and bloque["source"]["media_type"] == "image/jpeg"
    enviada = Image.open(io.BytesIO(base64.b64decode(bloque["source"]["data"])))
    assert max(enviada.size) <= 1024                                          # la foto se reduce antes de enviarla


def test_claude_con_respuesta_rara_pide_otra_foto(tmp_path, monkeypatch):
    monkeypatch.setattr(clasificador, "ANTHROPIC_API_KEY", "clave-falsa")
    for texto in ["no sé qué es", '{"residuos": []}', '{"residuos": "botella"}', '{"otra_cosa": 1}', ""]:
        monkeypatch.setattr(clasificador, "_llamar_api", lambda cuerpo, t=texto: {"content": [{"type": "text", "text": t}]})
        assert clasificador.detectar(_foto_grande(tmp_path)) == []


def test_claude_si_la_api_falla_dice_detector_no_disponible(tmp_path, monkeypatch):
    import httpx
    monkeypatch.setattr(clasificador, "ANTHROPIC_API_KEY", "clave-mala")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _RespuestaFalsa(401, texto="invalid x-api-key"))
    with pytest.raises(RuntimeError):
        clasificador.detectar(_foto_grande(tmp_path))
    monkeypatch.setattr(clasificador.time, "sleep", lambda s: None)
    monkeypatch.setattr(httpx, "post", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("sin internet")))
    with pytest.raises(RuntimeError):
        clasificador.detectar(_foto_grande(tmp_path))


def test_tope_diario_de_fotos_con_ia_de_pago(estudiante, monkeypatch):
    monkeypatch.setattr(clasificador, "ANTHROPIC_API_KEY", "clave-falsa")
    monkeypatch.setattr(clasificador, "detectar", lambda ruta: [{"residuo": "botella", "confianza": None}])
    monkeypatch.setattr(main, "LIMITE_DIARIO_IA", 2)
    assert enviar(estudiante).status_code == 200
    assert enviar(estudiante).status_code == 200
    r = enviar(estudiante)
    assert r.status_code == 429 and "límite" in r.json()["detail"]
    monkeypatch.setattr(main, "LIMITE_DIARIO_IA", 0)                          # 0 = sin tope
    assert enviar(estudiante).status_code == 200


# =============== Arreglos de la revisión ===============
def test_papel_carton_y_plastico_sucios_van_a_la_negra_y_los_limpios_a_la_blanca():
    for limpio, sucio in [("papel", "papel_sucio"), ("carton", "carton_sucio"), ("plastico", "plastico_sucio")]:
        assert catalogo.datos_residuo(limpio)["caneca"] == "blanca"
        assert catalogo.datos_residuo(sucio)["caneca"] == "negra"
        assert catalogo.datos_residuo(sucio)["categoria"] == "No Aprovechable"


def test_la_ia_puede_devolver_las_variantes_sucias(monkeypatch):
    monkeypatch.setattr(clasificador, "ANTHROPIC_API_KEY", "clave-falsa")
    texto = '{"residuos": ["Carton sucio", "papel_sucio", "Papel sucio", "plástico sucio", "lata"]}'
    monkeypatch.setattr(clasificador, "_llamar_api", lambda cuerpo: {"content": [{"type": "text", "text": texto}]})
    from pathlib import Path
    import tempfile
    from PIL import Image
    ruta = Path(tempfile.mkdtemp()) / "f.jpg"
    Image.new("RGB", (200, 100)).save(ruta)
    assert [x["residuo"] for x in clasificador.detectar(ruta)] == ["carton_sucio", "papel_sucio", "plastico_sucio"]
    assert "papel_sucio" in clasificador.INSTRUCCIONES_CLAUDE and "carton_sucio" in clasificador.INSTRUCCIONES_CLAUDE


def test_el_reporte_de_papel_sucio_sale_en_caneca_negra(estudiante, monkeypatch):
    monkeypatch.setattr(clasificador, "detectar", lambda ruta: [{"residuo": "carton_sucio", "confianza": None}])
    r = enviar(estudiante).json()
    assert r["residuos"][0]["caneca"] == "negra" and r["residuos"][0]["categoria"] == "No Aprovechable"
    assert main.db_one("SELECT categoria_residuo FROM historial_residuos")["categoria_residuo"] == "No Aprovechable"


def test_la_foto_guardada_se_reduce_y_pierde_los_datos_exif(estudiante):
    from PIL import Image
    assert enviar(estudiante, foto=JPG_CON_EXIF).status_code == 200
    assert enviar(estudiante, foto=JPG_GRANDE).status_code == 200
    nombres = [f["nombre_archivo"] for f in main.db_all("SELECT nombre_archivo FROM reportes ORDER BY id")]
    assert all(n.endswith(".jpg") for n in nombres)
    for n in nombres:
        with Image.open(main.UPLOADS_DIR / n) as img:
            assert len(img.getexif()) == 0              # sin marca del celular ni ubicación
            assert max(img.size) <= 1600                # reducida
    with Image.open(main.UPLOADS_DIR / nombres[1]) as grande:
        assert max(grande.size) == 1600


def test_una_imagen_rota_se_rechaza_y_no_deja_archivos(estudiante):
    antes = len(list(main.UPLOADS_DIR.glob("*")))
    rota = JPG[:60]                                     # empieza como JPG pero está cortada
    assert enviar(estudiante, foto=rota).status_code == 422
    assert len(list(main.UPLOADS_DIR.glob("*"))) == antes


def test_las_fechas_usan_la_hora_de_colombia():
    from datetime import datetime, timedelta, timezone
    esperada = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=5)
    assert abs((main.ahora() - esperada).total_seconds()) < 5
    assert "-5 hours" in main.SQL_ESQUEMA                # la fecha por defecto de la base de datos tampoco usa la hora del servidor


def test_la_fecha_guardada_coincide_con_hora_colombia(estudiante):
    from datetime import datetime
    assert enviar(estudiante).status_code == 200
    guardada = datetime.strptime(main.db_one("SELECT fecha_hora FROM reportes")["fecha_hora"], "%Y-%m-%d %H:%M:%S")
    assert abs((guardada - main.ahora()).total_seconds()) < 5


def test_docs_publicos_estan_apagados(anonimo):
    for ruta in ("/docs", "/redoc", "/openapi.json"):
        assert anonimo.get(ruta).status_code == 404, ruta
