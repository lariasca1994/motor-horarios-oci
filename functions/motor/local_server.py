"""
Servidor HTTP mínimo para correr el motor en local (docker-compose).
En OCI no se usa: allí el punto de entrada es func.handler vía fdk.

POST /  body: {"reunion_id": 1}
GET  /health
"""
import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from procesamiento import procesar_reunion

logger = logging.getLogger("motor-local")


class Handler(BaseHTTPRequestHandler):
    def _responder(self, codigo: int, cuerpo: dict):
        datos = json.dumps(cuerpo).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    def do_GET(self):
        self._responder(200, {"status": "ok"})

    def do_POST(self):
        largo = int(self.headers.get("Content-Length", 0))
        try:
            reunion_id = int(json.loads(self.rfile.read(largo) or b"{}")["reunion_id"])
        except (ValueError, KeyError, TypeError):
            return self._responder(400, {"status": "error", "mensaje": "reunion_id requerido"})
        try:
            resultado = procesar_reunion(reunion_id)
        except Exception as e:
            logger.exception("Error procesando reunión %s", reunion_id)
            return self._responder(500, {"status": "error", "mensaje": type(e).__name__})
        self._responder(404 if resultado["status"] == "error" else 200, resultado)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("Motor escuchando en :8001")
    ThreadingHTTPServer(("0.0.0.0", 8001), Handler).serve_forever()
