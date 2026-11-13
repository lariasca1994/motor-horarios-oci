// Service worker del Coordinador de reuniones (PWA).
// - Guarda solo la "cáscara": páginas, estilos, scripts e íconos de este sitio. La API vive en
//   otro dominio (Render) y nunca pasa por aquí: no se guardan reuniones, agendas ni sesiones.
// - Navegación primero por red (cada despliegue se ve enseguida); sin red, la última versión
//   guardada de esa página o la página "Sin conexión".
// - Sin push, sin sincronización en segundo plano y sin consultas periódicas: nada mantiene
//   despierto el servidor.
const VERSION = "coordinador-v1";
const CASCARA = [
  "/offline", "/login", "/verificacion", "/reuniones", "/agenda",
  "/css/estilos.css", "/css/acceso.css", "/css/efectos.css",
  "/js/config.js", "/js/comun.js", "/js/tema.js", "/js/efectos.js",
  "/iconos/icono.svg", "/iconos/icono-192.png", "/manifest.webmanifest",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(VERSION).then((cache) => cache.addAll(CASCARA)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((nombres) => Promise.all(nombres.filter((n) => n !== VERSION).map((n) => caches.delete(n))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((respuesta) => {
          if (respuesta.ok) {
            const copia = respuesta.clone();
            caches.open(VERSION).then((cache) => cache.put(url.pathname, copia));
          }
          return respuesta;
        })
        .catch(async () => (await caches.match(url.pathname)) || (await caches.match("/offline"))),
    );
    return;
  }

  if (/^\/(css|js|iconos)\//.test(url.pathname) || url.pathname === "/manifest.webmanifest") {
    // Red primero para que los cambios se vean; la copia guardada solo sin conexión.
    event.respondWith(
      fetch(request)
        .then((respuesta) => {
          if (respuesta.ok) {
            const copia = respuesta.clone();
            caches.open(VERSION).then((cache) => cache.put(request, copia));
          }
          return respuesta;
        })
        .catch(() => caches.match(request)),
    );
  }
});
