# EcoQR

App para que los estudiantes sepan en qué caneca (blanca, negra o verde) va cada residuo y por qué.
Entran escaneando un código QR, toman una foto y reciben el resultado con una explicación.
El profesor administra todo desde un panel.

```
index.html            App del estudiante (PWA, celular vertical)
admin.html            Panel del profesor y de otros administradores
main.py               Servidor FastAPI + SQLite
catalogo.py           Los residuos (7 + 3 variantes sucias), su caneca y su explicación (aquí se editan los textos)
clasificador.py       Puente de IA (API de Claude, modelo propio o modo de prueba)
sw.js / manifest.webmanifest / static/   PWA, CSS, fuentes y gráficas locales
tests/                Pruebas automáticas (pytest)
reset_clave.py        Recuperar la contraseña de un administrador
respaldo.py           Copia de seguridad de la base de datos
Dockerfile, render.yaml, .env.example   Despliegue
```

## Cómo funciona

- **Estudiantes:** escanean el QR (un solo código para todo el colegio) → quedan con acceso 30 días → escriben su nombre, eligen su curso, toman la foto → ven una tarjeta por residuo con su caneca y la explicación. Sin el QR no pueden enviar nada.
- **Profesor (administrador principal):** entra en `/admin` con usuario y contraseña. Ve el resumen general, el ranking por salón, el historial de actividad con fotos y el estado del sistema. Solo él gestiona cursos, administradores, el código QR y los borrados.
- **Otros administradores:** el profesor les crea una cuenta en la pestaña *Administradores*. Pueden ver estadísticas, actividad y fotos, pero no gestionar.
- **Ranking:** por total de residuos. Si anotas cuántos estudiantes tiene cada curso (pestaña *Cursos*), se ordena por residuos por estudiante, que es más justo.

## 1. Probar en tu computador

```bash
pip install -r requirements.txt
MODO_DEMO=1 uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
(PowerShell: `$env:MODO_DEMO="1"; uvicorn main:app --host 0.0.0.0 --port 8000`)

1. Mira la consola: la primera vez imprime la contraseña temporal del administrador (usuario `jaime`) si no definiste `ADMIN_PASSWORD`.
2. Abre `http://localhost:8000/admin`, entra, y en *Código QR* verás el cartel.
3. Escanea ese QR con el celular (misma red WiFi, usando la IP del computador en vez de `localhost`) o abre la dirección que aparece bajo el código.

`MODO_DEMO=1` inventa los resultados. Sirve para probar, nunca para estudiantes reales.

## 2. La IA con la API de Claude (recomendada: no hay que entrenar nada)

Si defines `ANTHROPIC_API_KEY`, la app envía cada foto (reducida a 1024 px y sin datos EXIF) a la API de Claude, que dice
qué residuos del catálogo ve. Puede identificar **varios por foto** y distingue papel, cartón o plástico **limpio** (caneca blanca) de **sucio, mojado o con comida** (caneca negra). Las reglas están en `INSTRUCCIONES_CLAUDE`
(`clasificador.py`); si cambias el catálogo, cámbialas también.

1. Crea una cuenta en la consola de Anthropic (platform.claude.com), carga crédito y crea una **clave de API**
   (se muestra una sola vez). La API se cobra aparte de claude.ai.
2. En la consola, pon un **límite de gasto mensual**.
3. Prueba en tu computador:
   ```bash
   pip install -r requirements.txt
   export ANTHROPIC_API_KEY="tu-clave"      # PowerShell: $env:ANTHROPIC_API_KEY="tu-clave"
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```
   En el panel, pestaña *Sistema*, debe decir «La IA está activa (Claude)».
4. Envía unas 20 fotos reales y mira el gasto en la consola: multiplícalo por 50 y tendrás el costo real por 1.000 fotos.
5. En producción define `ANTHROPIC_API_KEY` en las variables de la plataforma. **Nunca** la pongas en `index.html`,
   en GitHub ni en un chat. Si se filtra, bórrala en la consola y crea otra.

Variables útiles (`.env.example`): `CLAUDE_MODELO` (por defecto `claude-haiku-5-5`, el más barato) y
`LIMITE_DIARIO_IA` (tope de fotos por día; con 1500 y un uso normal el crédito no se agota por un abuso del QR).

**Si algo falla**, los estudiantes ven «detector no disponible» y la consola del servidor dice por qué:
401/403 = clave incorrecta; 400 con «credit balance» = se acabó el crédito; 404 = nombre de modelo mal escrito;
429 = demasiadas peticiones (reintenta solo una vez).

**Límites:** reconoce solo los residuos del catálogo (7 más las variantes sucias de papel, cartón y plástico; una lata o un vidrio suelto no se identifican y la app pide otra
foto), no acierta siempre, y cada foto sale del servidor hacia un tercero: el aviso de privacidad y la autorización de
los acudientes deben decirlo.

## 2b. Alternativa: modelo propio con Teachable Machine (opcional)

Solo si no quieres depender de la API. (Si `ANTHROPIC_API_KEY` está definida, esto se ignora.)

**Sin modelo entrenado y sin `MODO_DEMO`, la app responde «el detector todavía no está listo»** en lugar de inventar respuestas. Eso es a propósito. Para que funcione de verdad:

1. Entra a [Teachable Machine](https://teachablemachine.withgoogle.com/) → *Proyecto de imágenes*.
2. Crea **8 clases** (las 7 de abajo más `otro`, con fotos de manos, pisos, mesas, canecas vacías y objetos que no son residuos; si sale, la app pide otra foto). Nombres: `botella`, `empaque`, `resto de comida`, `cascara fruta`, `plastico`, `papel`, `carton`, `otro` (las tildes, mayúsculas y las palabras «de/la/el» no importan).
3. Sube **100 a 200 fotos por clase**, tomadas en el colegio, con distintas luces, fondos y ángulos, y con el residuo solo en la foto. Más fotos y más variedad = menos errores.
4. Entrena y exporta: *Exportar modelo → Tensorflow → Keras*. Copia `keras_model.h5` y `labels.txt` a la carpeta `modelo/`.
5. `pip install tensorflow-cpu` (en Python 3.12 no existe la versión 2.15; se probó con la 2.21) y quita el `#` de esa línea en `requirements.txt` para que el despliegue también la instale. Reinicia. En el panel, pestaña *Sistema*, debe decir «La IA está activa» (o abre `/salud`: `"ia": "modelo"`).

**Límites que debes conocer (y decirle al cliente):**
- Esta IA identifica **un residuo por foto**. Para varios residuos en una misma foto hace falta un modelo de detección de objetos (tipo YOLO) con fotos marcadas una a una; `clasificador.py` está listo para recibirlo (solo cambia `detectar()`).
- Ninguna IA acierta siempre. Si está menos segura que `UMBRAL_CONFIANZA` (60 %), la app pide otra foto en vez de adivinar. El panel muestra el porcentaje de fotos que no se pudieron identificar.
- Las explicaciones están en `catalogo.py`; que las revise un profesor de ciencias antes de la entrega.
- Casos ambiguos: una botella con líquido, un papel grasoso o un empaque de cartón pueden confundir al modelo. Incluye ejemplos de esos casos al entrenar.

## 3. Publicar en internet

Para que los estudiantes entren desde sus celulares hace falta que la app esté publicada con **HTTPS** (la cámara lo exige).

1. Define las variables de `.env.example` en la plataforma (sobre todo `ADMIN_PASSWORD` y `PUBLIC_URL`).
2. **Disco persistente en `/data`**: ahí quedan la base de datos y las fotos. Sin disco que sobreviva a los reinicios, se pierden los datos. Revisa qué ofrece cada plataforma en su plan gratuito: muchas no incluyen disco persistente.
3. Usa **un solo proceso** del servidor (los límites de uso viven en memoria).
4. Con el Dockerfile funciona en cualquier plataforma que corra Docker; `render.yaml` es un punto de partida sin probar.
5. Entra al panel → *Código QR*, comprueba que la dirección sea la pública, **imprime** y pega los carteles.

Para pruebas rápidas, ngrok o Cloudflare Tunnel exponen tu computador, pero la dirección puede cambiar y tendrías que reimprimir los QR.

**Respaldos:** programa `python respaldo.py` cada día y copia también la carpeta `data/uploads/`.
**Si el profesor olvida su contraseña:** `python reset_clave.py jaime` en el servidor.

## 4. Seguridad y privacidad (son menores de edad)
- El panel y las fotos exigen sesión; las cookies son `HttpOnly` y de sesión firmada. Cinco contraseñas erradas bloquean 10 minutos.
- El QR se puede **renovar** desde el panel si se filtra: el anterior deja de funcionar al instante.
- Se valida el contenido real de la foto, tamaño máximo y nombres aleatorios; la app reduce la foto antes de enviarla.
- Límite por estudiante (no por red), porque todo el colegio comparte la misma IP del WiFi.
- Consentimiento obligatorio antes de enviar. `RETENCION_DIAS` borra datos viejos automáticamente.
- **Pendiente de tu parte:** revisar con el colegio el aviso de privacidad y la autorización de los acudientes (Ley 1581 de 2012).
- Un QR no es un secreto (alguien puede fotografiarlo). Es una puerta, no una cerradura: por eso existen el límite de uso y la renovación.

## 5. Pruebas y cambios de diseño
```bash
pip install -r requirements-dev.txt
pytest
```
Si cambias clases de Tailwind en los HTML: `npm install` y `npm run build:css`. Si cambias `index.html` o `static/`, sube `VERSION` en `sw.js`.

## Cambios de la última revisión
- **Hora de Colombia:** todas las fechas, el «día» del tope de fotos y el panel usan UTC-5 (variable `TZ_OFFSET_HORAS`, por defecto `-5`), aunque el servidor esté en otro país.
- **Papel, cartón y plástico sucios:** la IA elige la variante limpia o sucia, y la caneca cambia (blanca/negra) según el estado. Los textos están en `catalogo.py` y las reglas en `INSTRUCCIONES_CLAUDE` (`clasificador.py`).
- **Foto guardada:** el servidor la abre, corrige la rotación, la reduce a máximo 1600 px y la vuelve a guardar como JPEG. Así se borran la ubicación GPS y los demás datos EXIF, y una foto dañada se rechaza.
- **Sin `/docs`:** la documentación automática de FastAPI ya no es pública.

## Limitaciones conocidas
- Sin conexión la app abre, pero no puede enviar reportes (no hay cola de envíos pendientes).
- Si un estudiante «instala» la app en iPhone, esa copia puede no compartir el acceso del navegador y pedirá escanear el QR de nuevo. Conviene usarla desde el navegador.
- El estudiante no puede corregir resultados (el cliente pidió que no); las correcciones se ven y se borran desde el panel.
- Nombres y cursos los escribe el estudiante: las cifras de «participantes» son aproximadas.
- El panel carga hasta 100 reportes por página en *Actividad*.
