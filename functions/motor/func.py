"""
Punto de entrada en OCI Functions: recibe {"reunion_id": N} y delega en procesamiento.
"""
import io
import json
import logging

from procesamiento import procesar_reunion

logging.basicConfig(level=logging.INFO)


def handler(ctx, data: io.BytesIO = None):
    from fdk import response

    try:
        payload = json.loads(data.getvalue()) if data and data.getvalue() else {}
        reunion_id = int(payload["reunion_id"])
    except (ValueError, KeyError, TypeError):
        resultado, codigo = {"status": "error", "mensaje": "reunion_id requerido"}, 400
    else:
        resultado = procesar_reunion(reunion_id)
        codigo = 404 if resultado["status"] == "error" else 200

    return response.Response(
        ctx, response_data=json.dumps(resultado),
        headers={"Content-Type": "application/json"}, status_code=codigo,
    )
