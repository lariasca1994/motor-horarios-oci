"""
Dispara la función del motor para una reunión.

MOTOR_MODE=http        -> POST a MOTOR_URL (motor como servicio HTTP: local o VM).
MOTOR_MODE=oci         -> invoca la función en OCI Functions (asíncrona / detached)
                          usando MOTOR_FUNCTION_OCID y MOTOR_INVOKE_ENDPOINT.
MOTOR_MODE=inproceso  -> ejecuta el motor en este mismo proceso (Render; requiere
                          los módulos de functions/motor en el PYTHONPATH).
MOTOR_MODE=off         -> no hace nada (la reunión queda 'pendiente').
"""
import json
import logging
import os

import httpx

logger = logging.getLogger(__name__)


def disparar_motor(reunion_id: int) -> bool:
    modo = os.environ.get("MOTOR_MODE", "oci")
    payload = json.dumps({"reunion_id": reunion_id})
    try:
        if modo == "inproceso":
            from procesamiento import procesar_reunion
            resultado = procesar_reunion(reunion_id)
            logger.info("Motor reunión %s: %s", reunion_id, resultado)
            return resultado.get("status") != "error"
        if modo == "http":
            r = httpx.post(os.environ["MOTOR_URL"], content=payload,
                           headers={"Content-Type": "application/json"}, timeout=30)
            r.raise_for_status()
            return True
        if modo == "oci":
            from oci.functions import FunctionsInvokeClient
            from vault import cliente_oci
            client = cliente_oci(FunctionsInvokeClient,
                                 service_endpoint=os.environ["MOTOR_INVOKE_ENDPOINT"])
            client.invoke_function(
                function_id=os.environ["MOTOR_FUNCTION_OCID"],
                invoke_function_body=payload,
                fn_invoke_type="detached",
            )
            return True
        return False
    except Exception:
        # La reunión ya quedó guardada; se puede recalcular después.
        logger.exception("No se pudo disparar el motor para la reunión %s", reunion_id)
        return False
