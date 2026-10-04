import hashlib
import json
import re
from   typing   import Optional

from   neo4j    import ManagedTransaction


# Catalogo cerrado de motivos (docs/decisiones.md, 2026-10-04). Un motivo fuera
# de esta lista es un error de programacion, no un dato.
MOTIVOS = frozenset({
    "token_invalido",
    "token_expirado",
    "token_reutilizado",
    "token_qr_inexistente",
    "sesion_cerrada",
    "no_autenticado",
    "alcance_insuficiente",
    "encabezados_faltantes",
    "solicitud_invalida",
    "credenciales_invalidas",
    "login_bloqueado_matricula",
    "login_bloqueado_ip",
    "firma_invalida",
    "timestamp_fuera_ventana",
    "sin_dispositivo_activo",
})

# Lista blanca: de estos se guarda el valor, recortado
ENCABEZADOS_CON_VALOR = (
    "User-Agent",
    "Accept-Language",
    "Content-Type",
    "Origin",
    "Referer",
    "X-Forwarded-For",   # lo pone el cliente o un proxy; dato sin verificar
    "CF-Connecting-IP",  # idem
    "X-TIMESTAMP",       # no es secreto; sirve para estudiar el desfase de reloj
)
# De estos solo se guarda si venian, nunca el valor
ENCABEZADOS_SOLO_PRESENCIA = ("Authorization", "X-SIGNATURE", "Cookie")

LONGITUD_MAXIMA_VALOR = 256
# X-Id-Prueba: etiqueta de laboratorio para cruzar con el manifiesto del banco
# de ataques. Nunca interviene en la decision de aceptar o rechazar.
PATRON_ID_PRUEBA = re.compile(r"[0-9a-f]{1,64}")


def asegurar_esquema_rechazos(tx: ManagedTransaction) -> None:
    tx.run("CREATE INDEX intento_rechazado_motivo IF NOT EXISTS "
           "FOR (r:IntentoRechazado) ON (r.motivo)")
    tx.run("CREATE INDEX intento_rechazado_marca_tiempo IF NOT EXISTS "
           "FOR (r:IntentoRechazado) ON (r.marca_tiempo)")
    tx.run("CREATE INDEX intento_rechazado_id_prueba IF NOT EXISTS "
           "FOR (r:IntentoRechazado) ON (r.id_prueba)")


def recortar(valor: object) -> Optional[str]:
    if not isinstance(valor, str) or not valor:
        return None
    return valor[:LONGITUD_MAXIMA_VALOR]


def sanear_encabezados(headers) -> str:
    """Devuelve JSON con la lista blanca de encabezados. Neo4j no admite mapas
    como propiedad, por eso se guarda como texto."""
    saneados: dict[str, object] = {}
    for nombre in ENCABEZADOS_CON_VALOR:
        valor = recortar(headers.get(nombre))
        if valor is not None:
            saneados[nombre] = valor
    for nombre in ENCABEZADOS_SOLO_PRESENCIA:
        saneados[f"{nombre}_presente"] = nombre in headers
    return json.dumps(saneados, ensure_ascii=False, sort_keys=True)


def id_prueba_valido(valor: Optional[str]) -> Optional[str]:
    if valor and PATRON_ID_PRUEBA.fullmatch(valor):
        return valor
    return None


def huella_corta(secreto: str) -> str:
    """Primeros 16 hexadecimales de SHA-256: identifica sin guardar el valor."""
    return hashlib.sha256(secreto.encode()).hexdigest()[:16]


def registrar_rechazo(tx: ManagedTransaction, datos: dict) -> None:
    if datos.get("motivo") not in MOTIVOS:
        raise ValueError(f"Motivo de rechazo desconocido: {datos.get('motivo')!r}")
    # SET r = $datos omite las claves con valor null
    tx.run("CREATE (r:IntentoRechazado) SET r = $datos", datos=datos)
