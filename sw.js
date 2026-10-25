/* Service worker de EcoQR.
   - Guarda la "carcasa" de la app para que abra rápido y sin conexión.
   - NUNCA guarda ni intercepta /api/, /admin, /q/ ni las fotos (son datos privados o de acceso).
   Si cambias index.html o los archivos de static/, sube el número de VERSION. */
const VERSION = "v2";
const CACHE = `residuos-${VERSION}`;
const CARCASA = [
  "/",
  "/manifest.webmanifest",
  "/static/tailwind.css",
  "/static/fuentes.css",
  "/static/bricolage.woff2",
  "/static/icon-192.png",
  "/static/icon-512.png",
];

self.addEventListener("install", (evento) => {
  evento.waitUntil(caches.open(CACHE).then((c) => c.addAll(CARCASA)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (evento) => {
  evento.waitUntil(
    caches.keys()
      .then((nombres) => Promise.all(nombres.filter((n) => n !== CACHE).map((n) => caches.delete(n))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (evento) => {
  const peticion = evento.request;
  const url = new URL(peticion.url);
  if (peticion.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/admin") || url.pathname.startsWith("/q/")) return; // siempre directo a la red

  // Página principal: primero la red (para tener la última versión), si falla usa la copia guardada
  if (peticion.mode === "navigate" && url.pathname === "/") {
    evento.respondWith(
      fetch(peticion)
        .then((r) => { const copia = r.clone(); caches.open(CACHE).then((c) => c.put("/", copia)); return r; })
        .catch(() => caches.match("/"))
    );
    return;
  }

  // Archivos estáticos: primero la copia guardada y se actualiza en segundo plano
  if (url.pathname.startsWith("/static/") || url.pathname === "/manifest.webmanifest") {
    evento.respondWith(
      caches.match(peticion).then((guardado) => {
        const red = fetch(peticion).then((r) => {
          if (r.ok) { const copia = r.clone(); caches.open(CACHE).then((c) => c.put(peticion, copia)); }
          return r;
        }).catch(() => guardado);
        return guardado || red;
      })
    );
  }
});
