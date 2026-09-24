from   datetime import datetime
from   typing   import Optional

from   neo4j    import ManagedTransaction


def asegurar_esquema_identidad(tx: ManagedTransaction) -> None:
    tx.run("CREATE CONSTRAINT alumno_matricula_unica IF NOT EXISTS "
           "FOR (a:Alumno) REQUIRE a.matricula IS UNIQUE")
    tx.run("CREATE CONSTRAINT bloqueo_login_clave_unica IF NOT EXISTS "
           "FOR (b:BloqueoLogin) REQUIRE b.clave IS UNIQUE")


# ---------------------------------------------------------------------------
# Alumno
# ---------------------------------------------------------------------------

def crear_alumno(tx: ManagedTransaction, matricula: str, nombre: str,
                  password_hash: str) -> bool:
    query = (
        "MERGE (a:Alumno {matricula: $matricula}) "
        "ON CREATE SET a.nombre = $nombre, "
        "a.password_hash         = $password_hash, "
        "a.debe_cambiar_password = true, "
        "a.sesion_token_hash     = null, "
        "a.sesion_expira_en      = null, "
        "a.creado_en             = $creado_en "
        "RETURN a.creado_en = $creado_en AS recien_creado"
    )
    creado_en = datetime.now().isoformat()
    # Si el alumno ya existia, ON CREATE SET no corrio y a.creado_en guarda una
    # fecha anterior distinta a la de esta llamada, asi que la comparacion da false.
    record = tx.run(query, matricula=matricula, nombre=nombre,
                     password_hash=password_hash, creado_en=creado_en).single()
    return bool(record["recien_creado"])


def obtener_alumno(tx: ManagedTransaction, matricula: str) -> Optional[dict]:
    query = "MATCH (a:Alumno {matricula: $matricula}) RETURN a"
    record = tx.run(query, matricula=matricula).single()
    return dict(record["a"]) if record else None


def tiene_dispositivo_activo(tx: ManagedTransaction, matricula: str) -> bool:
    query = ("MATCH (:Alumno {matricula: $matricula})-[:USA]->(:Dispositivo {activo: true}) "
              "RETURN count(*) > 0 AS tiene")
    record = tx.run(query, matricula=matricula).single()
    return bool(record["tiene"]) if record else False


def actualizar_password(tx: ManagedTransaction, matricula: str, password_hash: str) -> None:
    query = ("MATCH (a:Alumno {matricula: $matricula}) "
              "SET a.password_hash = $password_hash, a.debe_cambiar_password = false")
    tx.run(query, matricula=matricula, password_hash=password_hash)


def establecer_sesion(tx: ManagedTransaction, matricula: str,
                       sesion_token_hash: str, sesion_expira_en: float) -> None:
    query = ("MATCH (a:Alumno {matricula: $matricula}) "
              "SET a.sesion_token_hash = $sesion_token_hash, "
              "a.sesion_expira_en      = $sesion_expira_en")
    tx.run(query, matricula=matricula, sesion_token_hash=sesion_token_hash,
           sesion_expira_en=sesion_expira_en)


def invalidar_sesion(tx: ManagedTransaction, matricula: str) -> None:
    # Se llama tras cambiar la contrasena para que el token de alcance
    # limitado deje de servir incluso antes de expirar, y fuerce login nuevo.
    query = ("MATCH (a:Alumno {matricula: $matricula}) "
              "SET a.sesion_token_hash = null, a.sesion_expira_en = null")
    tx.run(query, matricula=matricula)


# ---------------------------------------------------------------------------
# Dispositivo
# ---------------------------------------------------------------------------

def registrar_dispositivo(tx: ManagedTransaction, matricula: str, llave_publica: str,
                           huella_dispositivo: str) -> None:
    tx.run(
        "MATCH (:Alumno {matricula: $matricula})-[:USA]->(d:Dispositivo {activo: true}) "
        "SET d.activo = false",
        matricula=matricula,
    )
    tx.run(
        "MATCH (a:Alumno {matricula: $matricula}) "
        "CREATE (a)-[:USA]->(:Dispositivo {llave_publica: $llave_publica, "
        "huella_dispositivo: $huella_dispositivo, creado_en: $creado_en, activo: true})",
        matricula=matricula, llave_publica=llave_publica,
        huella_dispositivo=huella_dispositivo, creado_en=datetime.now().isoformat(),
    )


def obtener_dispositivo_activo(tx: ManagedTransaction, matricula: str) -> Optional[dict]:
    query = (
        "MATCH (:Alumno {matricula: $matricula})-[:USA]->(d:Dispositivo {activo: true}) "
        "RETURN d.llave_publica AS llave_publica, d.huella_dispositivo AS huella_dispositivo"
    )
    record = tx.run(query, matricula=matricula).single()
    return dict(record) if record else None


# ---------------------------------------------------------------------------
# BloqueoLogin
# ---------------------------------------------------------------------------

def registrar_intento_fallido(tx: ManagedTransaction, clave: str, ahora: float,
                               ventana_segundos: float) -> int:
    query = (
        "MERGE (b:BloqueoLogin {clave: $clave}) "
        "ON CREATE SET b.conteo = 1, b.primer_intento = $ahora, b.bloqueado_hasta = null "
        "ON MATCH SET "
        "  b.conteo = CASE WHEN $ahora - b.primer_intento > $ventana THEN 1 "
        "                  ELSE b.conteo + 1 END, "
        "  b.primer_intento = CASE WHEN $ahora - b.primer_intento > $ventana THEN $ahora "
        "                          ELSE b.primer_intento END "
        "RETURN b.conteo AS conteo"
    )
    # MERGE + restriccion de unicidad sobre "clave" hace atomico el incremento
    # (o el reinicio de la ventana) frente a peticiones concurrentes.
    record = tx.run(query, clave=clave, ahora=ahora, ventana=ventana_segundos).single()
    return record["conteo"]


def marcar_bloqueo(tx: ManagedTransaction, clave: str, bloqueado_hasta: float) -> None:
    query = "MATCH (b:BloqueoLogin {clave: $clave}) SET b.bloqueado_hasta = $bloqueado_hasta"
    tx.run(query, clave=clave, bloqueado_hasta=bloqueado_hasta)


def esta_bloqueado(tx: ManagedTransaction, clave: str, ahora: float) -> bool:
    query = "MATCH (b:BloqueoLogin {clave: $clave}) RETURN b.bloqueado_hasta AS bloqueado_hasta"
    record = tx.run(query, clave=clave).single()
    if not record or record["bloqueado_hasta"] is None:
        return False
    return ahora < record["bloqueado_hasta"]


def limpiar_intentos(tx: ManagedTransaction, clave: str) -> None:
    # Se llama tras un login exitoso para que los fallos previos no se acumulen
    # hacia un bloqueo futuro que ya no tiene motivo.
    tx.run("MATCH (b:BloqueoLogin {clave: $clave}) DELETE b", clave=clave)
