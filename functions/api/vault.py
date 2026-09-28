import base64
import json
import os
from functools import lru_cache

import oci
from oci.secrets import SecretsClient


@lru_cache(maxsize=None)
def obtener_signer():
    """
    Credenciales de OCI sin llaves en disco:
    OCI_AUTH=instance_principal (VM) o resource_principal (OCI Functions, por defecto).
    """
    if os.environ.get("OCI_AUTH", "resource_principal") == "instance_principal":
        return oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
    return oci.auth.signers.get_resource_principals_signer()


def cliente_oci(clase, **kwargs):
    signer = obtener_signer()
    return clase(config={"region": signer.region}, signer=signer, **kwargs)


@lru_cache(maxsize=None)
def leer_secreto(secret_ocid: str) -> dict:
    """
    Lee un secreto JSON desde OCI Vault. Se cachea mientras el proceso siga vivo
    para no llamar al Vault en cada petición.
    """
    bundle = cliente_oci(SecretsClient).get_secret_bundle(secret_id=secret_ocid).data
    contenido = base64.b64decode(bundle.secret_bundle_content.content)
    return json.loads(contenido)


def credenciales_bd() -> dict:
    """
    El secreto referenciado por DB_SECRET_OCID debe tener la forma:
    {"host": "...", "port": 3306, "user": "...", "password": "...",
     "database": "...", "ssl_ca": "-----BEGIN CERTIFICATE-----..." (opcional)}
    """
    return leer_secreto(os.environ["DB_SECRET_OCID"])
