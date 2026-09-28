"""
Punto de entrada en OCI Functions.

API Gateway -> OCI Functions (fdk) -> este handler -> app FastAPI (ASGI en memoria).
Mangum no sirve aquí porque traduce eventos de AWS Lambda, no de OCI.
"""
import os
from urllib.parse import urlsplit

import httpx
from fdk import response

from main import app

# Prefijo de ruta del deployment en API Gateway (p. ej. "/horarios"), se elimina
# antes de pasar la ruta a FastAPI.
PREFIJO = os.environ.get("API_PATH_PREFIX", "").rstrip("/")

_HEADERS_EXCLUIDOS = {"host", "content-length", "connection", "transfer-encoding"}
_transport = httpx.ASGITransport(app=app)


def _ruta(ctx) -> str:
    url = ctx.RequestURL() or "/"
    partes = urlsplit(url)
    ruta = partes.path or "/"
    if PREFIJO and ruta.startswith(PREFIJO):
        ruta = ruta[len(PREFIJO):] or "/"
    return ruta + (f"?{partes.query}" if partes.query else "")


def _headers(ctx) -> dict:
    headers = {}
    for k, v in (ctx.HTTPHeaders() or {}).items():
        if k.lower() in _HEADERS_EXCLUIDOS:
            continue
        headers[k] = ", ".join(v) if isinstance(v, list) else str(v)
    return headers


async def handler(ctx, data=None):
    cuerpo = data.getvalue() if data is not None else b""
    async with httpx.AsyncClient(transport=_transport, base_url="http://fn") as cliente:
        r = await cliente.request(ctx.Method() or "GET", _ruta(ctx),
                                  headers=_headers(ctx), content=cuerpo)

    headers = {k: v for k, v in r.headers.items()
               if k.lower() not in ("content-length", "transfer-encoding")}
    return response.Response(ctx, response_data=r.content,
                             headers=headers, status_code=r.status_code)
