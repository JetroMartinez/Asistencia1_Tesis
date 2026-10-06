"""Genera el conjunto de datos de evaluacion de la seccion 9 de CLAUDE.md (metrica 2:
tasa de deteccion y de falsos positivos), con datos sinteticos contra el Neo4j local.

No sale nada a la red: usa el test_client de Flask de server.py, igual que
tests/probar_registro_rechazos.py. Reutiliza esa misma logica (emitir tokens de
sesion, firmar canjes, enrolar dispositivos, provocar bloqueos de login), pero en
vez de verificar cada caso una vez, repite cada escenario --n veces y escribe el
manifiesto JSONL que espera scripts/metricas_deteccion.py:

    {"id_prueba": "<hex>", "escenario": "...", "clase": "ataque"|"legitimo"|"informativo",
     "motivo_esperado": "<motivo del catalogo>" | null}

Cada peticion lleva su X-Id-Prueba; el servidor lo guarda como etiqueta en el nodo
(:IntentoRechazado) y nunca lo usa para decidir. metricas_deteccion.py cruza el
manifiesto con los nodos: una peticion con nodo se cuenta rechazada; sin nodo,
aceptada.

Escenarios (plan aprobado, docs/decisiones.md):

  ataque      proxy_otro_dispositivo   sesion valida de A, firma con la llave de B
  ataque      llave_no_enrolada        firma de una llave P-256 nunca enrolada
  ataque      timestamp_fuera_ventana  firma valida con X-TIMESTAMP de -120 s
  ataque      replay_token             repite un canje ya aceptado
  ataque      script_sin_app           POST del formulario sin Bearer ni firma
  ataque      suplantacion_matricula   token de sesion con matricula ajena y HMAC falso
  ataque      fuerza_bruta_login       contrasenas incorrectas seguidas
  ataque      proxy_reenrolado         se enrola otro telefono bajo la victima y se canjea
  legitimo    canje_normal             token QR, sesion y firma correctos
  legitimo    login_correcto           credenciales correctas
  legitimo    error_captura            login correcto que sigue a un intento mal tecleado
  informativo error_captura_fallido    el intento mal tecleado (se cuenta aparte)

Dos resultados se verifican fuera del manifiesto (no son "ataque no detectado",
son resultados positivos) y se escriben en una seccion propia del .txt de evidencia:

  - suplantacion por formulario: el servidor registra la matricula de la sesion,
    no la que viene en el formulario.
  - disuasion con rastro del proxy_reenrolado: enrolar otro telefono desactiva el
    dispositivo del dueno y el evento queda registrado.

Al terminar corre metricas_deteccion.py sobre el manifiesto y deja su salida en
docs/evidencias/. Conserva los nodos (:IntentoRechazado) (son el conjunto de datos);
borra los Token, BloqueoLogin y alumnos BANCO* que creo. El manifiesto es .jsonl, que
.gitignore ya excluye, asi que no se versiona (docs/decisiones.md, decision 5).

Uso: python scripts/generar_datos_evaluacion.py [--n 30] (desde backend/)
"""
import argparse
import base64
import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
import uuid
from   datetime import datetime
from   pathlib  import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from cryptography.hazmat.primitives            import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from werkzeug.security                         import generate_password_hash

import identidad
import rechazos
import server

DER  = serialization.Encoding.DER
SPKI = serialization.PublicFormat.SubjectPublicKeyInfo

EVIDENCIAS = BACKEND.parent / "docs" / "evidencias"
# RFC 5737 (TEST-NET-2): no es una IP real; marca el trafico como sintetico.
IP = "198.51.100.7"
# Contrasena sintetica compartida por los alumnos del banco. Es un dato de
# laboratorio, no una credencial real (seccion 6 de CLAUDE.md).
PASSWORD = "clave-evaluacion-sintetica-0"

# Alumnos del banco: NO se usan SIM0001..SIM0003 para no invalidar la sesion del
# telefono de pruebas ni mezclar con otras pruebas del backend.
ALUMNO    = "BANCO0001"   # dueno legitimo, dispositivo = llave_a
ATACANTE  = "BANCO0002"   # dispositivo propio enrolado = llave_b
VICTIMA   = "BANCO0003"   # proxy_reenrolado reemplaza su dispositivo
BRUTO     = "BANCO0004"   # blanco de fuerza bruta de login
CAPTURA   = "BANCO0005"   # alumno que teclea mal y luego acierta

CORRIDA  = uuid.uuid4().hex[:16]
_contador = 0
manifiesto: list[dict] = []
tokens_creados: list[str] = []


def nuevo_id() -> str:
    global _contador
    _contador += 1
    return f"{CORRIDA}{_contador:06x}"


def anotar(id_prueba: str, escenario: str, clase: str, motivo_esperado) -> None:
    manifiesto.append({"id_prueba": id_prueba, "escenario": escenario,
                       "clase": clase, "motivo_esperado": motivo_esperado})


def emitir_token(matricula: str, alcance: str, vigencia: float = 600) -> str:
    """Mismo formato que /login; guarda su hash como la sesion vigente del alumno."""
    expira_en = time.time() + vigencia
    payload   = f"{matricula}.{alcance}.{expira_en}"
    firma     = hmac.new(os.getenv("API_SECRET").encode(), payload.encode(),
                         hashlib.sha256).hexdigest()
    token     = f"{payload}.{firma}"
    with server.driver.session() as s:
        s.execute_write(identidad.establecer_sesion, matricula,
                        hashlib.sha256(token.encode()).hexdigest(), expira_en)
    return token


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def firmar(llave_privada, timestamp: int, token_qr: str) -> str:
    mensaje = f"{timestamp}/asistencia:{token_qr}".encode()
    return base64.b64encode(llave_privada.sign(mensaje, ec.ECDSA(hashes.SHA256()))).decode()


def nuevo_token_qr() -> str:
    token_qr = uuid.uuid4().hex[:32]
    with server.driver.session() as s:
        s.execute_write(server.create_token_record, token_qr)
    tokens_creados.append(token_qr)
    return token_qr


def preparar_alumno(matricula: str, nombre: str):
    """Crea (o reutiliza) el alumno y le fija una contrasena conocida. actualizar_password
    tambien pone debe_cambiar_password=false, para poder emitir sesiones de alcance
    completo y enrolar dispositivos."""
    with server.driver.session() as s:
        s.execute_write(identidad.crear_alumno, matricula, nombre,
                        generate_password_hash(PASSWORD))
        s.execute_write(identidad.actualizar_password, matricula,
                        generate_password_hash(PASSWORD))


def enrolar(matricula: str, llave_privada) -> None:
    der_b64 = base64.b64encode(llave_privada.public_key().public_bytes(DER, SPKI)).decode()
    r = cliente.post("/dispositivos/registrar", headers=bearer(emitir_token(matricula, "completo")),
                     json={"llave_publica": der_b64, "huella_dispositivo": f"huella-{matricula}"})
    if r.status_code != 201:
        sys.exit(f"No se pudo enrolar el dispositivo de {matricula}: {r.status_code} {r.get_json()}")


def canje(matricula: str, llave_firma, token_qr: str, id_prueba: str,
          timestamp: int | None = None):
    """Un POST de canje firmado, con sesion fresca de alcance completo del alumno."""
    ts = int(time.time()) if timestamp is None else timestamp
    headers = {**bearer(emitir_token(matricula, "completo")),
               "X-TIMESTAMP": str(ts), "X-SIGNATURE": firmar(llave_firma, ts, token_qr),
               "X-Id-Prueba": id_prueba}
    return cliente.post(f"/?token={token_qr}", headers=headers,
                        environ_base={"REMOTE_ADDR": IP})


def post_login(matricula: str, password: str, id_prueba: str):
    return cliente.post("/login", headers={"X-Id-Prueba": id_prueba},
                        environ_base={"REMOTE_ADDR": IP},
                        json={"matricula": matricula, "password": password})


cliente = server.app.test_client()


# ---------------------------------------------------------------------------
# Escenarios
# ---------------------------------------------------------------------------
def gen_proxy_otro_dispositivo(n: int, llave_b) -> None:
    # Sesion valida de ALUMNO, firma con la llave del dispositivo de ATACANTE.
    # El servidor verifica contra el dispositivo activo de ALUMNO -> firma_invalida.
    for _ in range(n):
        idp = nuevo_id()
        canje(ALUMNO, llave_b, nuevo_token_qr(), idp)
        anotar(idp, "proxy_otro_dispositivo", "ataque", "firma_invalida")


def gen_llave_no_enrolada(n: int) -> None:
    for _ in range(n):
        idp = nuevo_id()
        canje(ALUMNO, ec.generate_private_key(ec.SECP256R1()), nuevo_token_qr(), idp)
        anotar(idp, "llave_no_enrolada", "ataque", "firma_invalida")


def gen_timestamp_fuera_ventana(n: int, llave_a) -> None:
    for _ in range(n):
        idp = nuevo_id()
        viejo = int(time.time()) - (server.VENTANA_CANJE_SEGUNDOS + 60)
        canje(ALUMNO, llave_a, nuevo_token_qr(), idp, timestamp=viejo)
        anotar(idp, "timestamp_fuera_ventana", "ataque", "timestamp_fuera_ventana")


def gen_replay_token(n: int, llave_a) -> None:
    # Primer canje valido (no se anota: es el uso legitimo) y luego el replay exacto.
    for _ in range(n):
        token_qr = nuevo_token_qr()
        ts       = int(time.time())
        headers  = {**bearer(emitir_token(ALUMNO, "completo")),
                    "X-TIMESTAMP": str(ts), "X-SIGNATURE": firmar(llave_a, ts, token_qr)}
        r0 = cliente.post(f"/?token={token_qr}", headers=headers, environ_base={"REMOTE_ADDR": IP})
        if r0.status_code != 200:
            sys.exit(f"replay_token: el primer canje debia ser 200, fue {r0.status_code}")
        idp = nuevo_id()
        cliente.post(f"/?token={token_qr}", headers={**headers, "X-Id-Prueba": idp},
                     environ_base={"REMOTE_ADDR": IP})
        anotar(idp, "replay_token", "ataque", "token_reutilizado")


def gen_script_sin_app(n: int) -> None:
    # POST del formulario tal como lo haria un navegador o curl: sin Bearer.
    for _ in range(n):
        idp = nuevo_id()
        cliente.post(f"/?token={nuevo_token_qr()}", headers={"X-Id-Prueba": idp},
                     environ_base={"REMOTE_ADDR": IP},
                     data={"nombre": "Anonimo", "matricula": "SIM9999"})
        anotar(idp, "script_sin_app", "ataque", "no_autenticado")


def gen_suplantacion_matricula(n: int) -> None:
    # Token de sesion que lleva la matricula de ALUMNO pero con HMAC invalido:
    # cualquiera puede escribir la matricula, el servidor la rechaza al no verificar.
    for _ in range(n):
        idp       = nuevo_id()
        falsificado = f"{ALUMNO}.completo.{time.time() + 600}.{'0' * 64}"
        cliente.post(f"/?token={nuevo_token_qr()}",
                     headers={**bearer(falsificado), "X-Id-Prueba": idp},
                     environ_base={"REMOTE_ADDR": IP})
        anotar(idp, "suplantacion_matricula", "ataque", "token_invalido")


def gen_fuerza_bruta_login(n: int) -> None:
    # Contrasenas incorrectas seguidas contra BRUTO. Hasta el umbral el servidor
    # responde credenciales_invalidas; despues, login_bloqueado_matricula.
    for i in range(n):
        idp = nuevo_id()
        post_login(BRUTO, f"incorrecta-{uuid.uuid4().hex}", idp)
        esperado = ("credenciales_invalidas" if i < server.UMBRAL_INTENTOS_MATRICULA
                    else "login_bloqueado_matricula")
        anotar(idp, "fuerza_bruta_login", "ataque", esperado)


def gen_proxy_reenrolado(n: int) -> None:
    # El prestamo consciente: quien conoce la contrasena de VICTIMA enrola su propio
    # telefono y canjea. Es aceptado -> deteccion esperada ~0 (hallazgo honesto).
    for _ in range(n):
        llave_atacante = ec.generate_private_key(ec.SECP256R1())
        enrolar(VICTIMA, llave_atacante)   # desactiva el dispositivo anterior de VICTIMA
        idp = nuevo_id()
        r = canje(VICTIMA, llave_atacante, nuevo_token_qr(), idp)
        if r.status_code != 200:
            sys.exit(f"proxy_reenrolado: el canje debia ser 200, fue {r.status_code}")
        anotar(idp, "proxy_reenrolado", "ataque", None)


def gen_canje_normal(n: int, llave_a) -> None:
    for _ in range(n):
        idp = nuevo_id()
        r = canje(ALUMNO, llave_a, nuevo_token_qr(), idp)
        if r.status_code != 200:
            sys.exit(f"canje_normal: el canje debia ser 200, fue {r.status_code}")
        anotar(idp, "canje_normal", "legitimo", None)


def gen_login_correcto(n: int) -> None:
    for _ in range(n):
        idp = nuevo_id()
        r = post_login(ALUMNO, PASSWORD, idp)
        if r.status_code != 200:
            sys.exit(f"login_correcto: el login debia ser 200, fue {r.status_code}")
        anotar(idp, "login_correcto", "legitimo", None)


def gen_error_captura(n: int) -> None:
    # Un alumno real que teclea mal una vez y luego acierta. El intento fallido es
    # "informativo" (se cuenta aparte); solo el login correcto cuenta como legitimo.
    # El login correcto llama a limpiar_intentos, asi que el contador nunca se acumula.
    for _ in range(n):
        idp_fallo = nuevo_id()
        post_login(CAPTURA, f"mal-tecleada-{uuid.uuid4().hex}", idp_fallo)
        anotar(idp_fallo, "error_captura_fallido", "informativo", "credenciales_invalidas")

        idp_ok = nuevo_id()
        r = post_login(CAPTURA, PASSWORD, idp_ok)
        if r.status_code != 200:
            sys.exit(f"error_captura: el login correcto debia ser 200, fue {r.status_code}")
        anotar(idp_ok, "error_captura", "legitimo", None)


# ---------------------------------------------------------------------------
# Verificaciones fuera del manifiesto (resultados positivos, no ataques)
# ---------------------------------------------------------------------------
def verificar_suplantacion_formulario(llave_a) -> dict:
    """Canje valido de ALUMNO con el formulario trayendo datos de otra persona.
    El servidor debe registrar la matricula de la sesion, no la del formulario."""
    token_qr = nuevo_token_qr()
    ts       = int(time.time())
    headers  = {**bearer(emitir_token(ALUMNO, "completo")),
                "X-TIMESTAMP": str(ts), "X-SIGNATURE": firmar(llave_a, ts, token_qr)}
    r = cliente.post(f"/?token={token_qr}", headers=headers, environ_base={"REMOTE_ADDR": IP},
                     data={"nombre": "Nombre Suplantado", "matricula": "SIM9999"})
    with server.driver.session() as s:
        rec = s.run("MATCH (t:Token {token: $t}) RETURN t.matricula AS m, t.nombre AS n",
                    t=token_qr).single()
    registrada = rec["m"] if rec else None
    return {"status": r.status_code, "matricula_formulario": "SIM9999",
            "matricula_registrada": registrada, "nombre_registrado": rec["n"] if rec else None,
            "ok": r.status_code == 200 and registrada == ALUMNO}


def verificar_rastro_reenrolado() -> dict:
    """Tras los re-enrolamientos de VICTIMA: debe quedar exactamente un dispositivo
    activo y el resto desactivado (el del dueno y los intermedios). Eso documenta la
    disuasion con rastro: enrolar otro telefono desactiva el del dueno y queda registro."""
    with server.driver.session() as s:
        filas = s.run(
            "MATCH (:Alumno {matricula: $m})-[:USA]->(d:Dispositivo) "
            "RETURN d.activo AS activo, count(*) AS n", m=VICTIMA).data()
    activos    = sum(f["n"] for f in filas if f["activo"])
    inactivos  = sum(f["n"] for f in filas if not f["activo"])
    return {"dispositivos_activos": activos, "dispositivos_desactivados": inactivos,
            "ok": activos == 1 and inactivos >= 1}


# ---------------------------------------------------------------------------
# Orquestacion
# ---------------------------------------------------------------------------
def escribir_manifiesto(ruta: Path) -> None:
    with ruta.open("w", encoding="utf-8") as f:
        for linea in manifiesto:
            f.write(json.dumps(linea, ensure_ascii=False) + "\n")


def escribir_evidencia(ruta: Path, suplantacion: dict, rastro: dict, manifiesto_ruta: Path) -> None:
    clases = {}
    for e in manifiesto:
        clases[e["clase"]] = clases.get(e["clase"], 0) + 1
    lineas = [
        f"# Conjunto de datos de evaluacion — {datetime.now().isoformat(timespec='seconds')}",
        f"# Corrida: {CORRIDA}",
        "",
        f"Peticiones en el manifiesto: {len(manifiesto)}",
        *[f"  {clase}: {n}" for clase, n in sorted(clases.items())],
        f"Manifiesto (no versionado, .jsonl): {manifiesto_ruta.name}",
        "",
        "## Verificaciones fuera del manifiesto (resultados positivos, no ataques)",
        "",
        "### Suplantacion por formulario",
        "Canje valido cuyo formulario trae nombre y matricula de otra persona. El",
        "servidor ignora el formulario y registra la identidad de la sesion.",
        f"  status HTTP:            {suplantacion['status']}",
        f"  matricula en formulario: {suplantacion['matricula_formulario']}",
        f"  matricula registrada:    {suplantacion['matricula_registrada']}",
        f"  nombre registrado:       {suplantacion['nombre_registrado']}",
        f"  RESULTADO: {'OK — se registro la matricula de la sesion' if suplantacion['ok'] else 'FALLA'}",
        "",
        "### Disuasion con rastro del proxy_reenrolado",
        "Enrolar otro telefono bajo la victima desactiva el dispositivo del dueno; el",
        "evento queda registrado como un nodo Dispositivo nuevo con su marca de tiempo.",
        f"  dispositivos activos:      {rastro['dispositivos_activos']}",
        f"  dispositivos desactivados: {rastro['dispositivos_desactivados']}",
        f"  RESULTADO: {'OK — un solo activo, el del dueno quedo desactivado y registrado' if rastro['ok'] else 'FALLA'}",
        "",
    ]
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")


def limpiar() -> None:
    """Conserva los (:IntentoRechazado) (son el conjunto de datos). Borra los Token,
    BloqueoLogin y alumnos BANCO* con sus dispositivos."""
    with server.driver.session() as s:
        s.run("MATCH (t:Token) WHERE t.token IN $tokens DELETE t", tokens=tokens_creados)
        s.run("MATCH (b:BloqueoLogin) WHERE b.clave = $mat OR b.clave = $ip DELETE b",
              mat=f"matricula:{BRUTO}", ip=f"ip:{IP}")
        s.run("MATCH (a:Alumno) WHERE a.matricula STARTS WITH 'BANCO' "
              "OPTIONAL MATCH (a)-[:USA]->(d:Dispositivo) DETACH DELETE a, d")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--n", type=int, default=30,
                        help="Peticiones por escenario (por defecto 30).")
    args = parser.parse_args()
    if args.n < 1:
        sys.exit("--n debe ser >= 1")

    ahora = datetime.now()
    EVIDENCIAS.mkdir(parents=True, exist_ok=True)

    # Alta de los alumnos del banco y enrolamiento de dispositivos
    for matricula, nombre in [(ALUMNO, "Banco Alumno"), (ATACANTE, "Banco Atacante"),
                              (VICTIMA, "Banco Victima"), (BRUTO, "Banco FuerzaBruta"),
                              (CAPTURA, "Banco Captura")]:
        preparar_alumno(matricula, nombre)

    llave_a = ec.generate_private_key(ec.SECP256R1())
    llave_b = ec.generate_private_key(ec.SECP256R1())
    enrolar(ALUMNO, llave_a)
    enrolar(ATACANTE, llave_b)
    enrolar(VICTIMA, ec.generate_private_key(ec.SECP256R1()))  # dispositivo del "dueno"
    enrolar(BRUTO, ec.generate_private_key(ec.SECP256R1()))    # con dispositivo: no cuenta por IP
    enrolar(CAPTURA, ec.generate_private_key(ec.SECP256R1()))  # idem

    try:
        gen_proxy_otro_dispositivo(args.n, llave_b)
        gen_llave_no_enrolada(args.n)
        gen_timestamp_fuera_ventana(args.n, llave_a)
        gen_replay_token(args.n, llave_a)
        gen_script_sin_app(args.n)
        gen_suplantacion_matricula(args.n)
        gen_proxy_reenrolado(args.n)
        gen_canje_normal(args.n, llave_a)
        gen_login_correcto(args.n)
        gen_error_captura(args.n)
        # fuerza_bruta deja BRUTO bloqueado; se corre al final
        gen_fuerza_bruta_login(args.n)

        suplantacion = verificar_suplantacion_formulario(llave_a)
        rastro       = verificar_rastro_reenrolado()

        manifiesto_ruta = EVIDENCIAS / f"manifiesto_evaluacion_{ahora:%Y-%m-%d_%H%M%S}.jsonl"
        escribir_manifiesto(manifiesto_ruta)
        evidencia_ruta = EVIDENCIAS / f"datos_evaluacion_{ahora:%Y-%m-%d_%H%M%S}.txt"
        escribir_evidencia(evidencia_ruta, suplantacion, rastro, manifiesto_ruta)
    finally:
        limpiar()

    print(f"Manifiesto: {manifiesto_ruta}  ({len(manifiesto)} peticiones)")
    print(f"Evidencia:  {evidencia_ruta}")
    print(f"Suplantacion por formulario: {'OK' if suplantacion['ok'] else 'FALLA'}")
    print(f"Rastro proxy_reenrolado:     {'OK' if rastro['ok'] else 'FALLA'}")
    print("\n== metricas_deteccion.py ==")
    subprocess.run([sys.executable, str(BACKEND / "scripts" / "metricas_deteccion.py"),
                    "--manifiesto", str(manifiesto_ruta)], check=True)


if __name__ == "__main__":
    main()
