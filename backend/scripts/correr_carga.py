"""Pruebas de carga del canje completo (seccion 9 de CLAUDE.md, metrica 1).

Mide latencia p50/p95/p99 y tasa de exito del canje autenticado con 60 y 90
peticiones concurrentes, que es el tamano de grupo del protocolo. Datos sinteticos
contra el Neo4j local; no sale nada a la red.

El canje exige sesion valida y firma ECDSA del dispositivo activo (docs/decisiones.md,
2026-09-24), asi que ANTES de medir el generador:
  1. arranca server.py como subproceso (si no hay ya uno escuchando el puerto);
  2. crea alumnos sinteticos CARGA0001.., cada uno con contrasena conocida, una
     sesion de alcance completo y un par de llaves EC P-256 enrolado por el endpoint
     real /dispositivos/registrar;
  3. crea un lote de tokens QR de un solo uso (cada canje exitoso consume uno).

Luego, por cada nivel de concurrencia, lanza Locust en modo biblioteca con ese numero
de usuarios virtuales (FastHttpUser, sin pausa entre peticiones -> ~N canjes en vuelo)
y corre hasta agotar el lote de tokens. Cada usuario virtual es un alumno distinto, con
su propia sesion y su propia llave; firma cada canje y lo manda al servidor real.

No se puede importar server.py aqui: usa eventlet, que choca con el gevent de Locust.
Por eso la provision usa el driver de Neo4j y identidad.py directamente (sin eventlet) y
el enrolamiento se hace por HTTP contra el server.py que corre aparte.

Limpieza: borra los alumnos CARGA*, sus dispositivos y todos los tokens QR creados. Los
canjes exitosos no deben dejar (:IntentoRechazado); si alguno falla, su nodo se etiqueta
con X-Id-Prueba y tambien se borra. Resultados en docs/evidencias/.

Uso (desde backend/):
    python scripts/correr_carga.py                 # niveles 60 y 90, 3000 canjes c/u
    python scripts/correr_carga.py --canjes 1500 --niveles 60 90
"""
import gevent.monkey
gevent.monkey.patch_all()  # debe ir antes de todo lo que use sockets

import argparse
import base64
import hashlib
import hmac
import json
import os
import socket
import subprocess
import sys
import time
import uuid
from   collections import Counter, deque
from   datetime    import datetime
from   pathlib     import Path

import gevent
import requests
from   dotenv  import load_dotenv
from   neo4j   import GraphDatabase
from   cryptography.hazmat.primitives            import hashes, serialization
from   cryptography.hazmat.primitives.asymmetric import ec
from   werkzeug.security import generate_password_hash

from   locust           import FastHttpUser, task, constant
from   locust.env       import Environment
from   locust.exception import StopUser

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)
load_dotenv(BACKEND / ".env")

import identidad

EVIDENCIAS = BACKEND.parent / "docs" / "evidencias"
PORT       = 26998
HOST       = f"http://127.0.0.1:{PORT}"
DER        = serialization.Encoding.DER
SPKI       = serialization.PublicFormat.SubjectPublicKeyInfo
PASSWORD   = "clave-carga-sintetica-0"
# Etiqueta de laboratorio para los nodos de rechazo que pudiera dejar un canje fallido
# (no deberia haber ninguno). 16 hex: cumple el patron de X-Id-Prueba.
CORRIDA    = uuid.uuid4().hex[:16]
NEO4J_URI  = os.getenv("NEO4J_URI")
NEO4J_AUTH = (os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD"))
API_SECRET = os.getenv("API_SECRET")

# Estado compartido entre los greenlets de los usuarios virtuales
COLA_QR: deque           = deque()
IDENTIDADES: deque       = deque()
_DISP_LOCK               = gevent.lock.Semaphore()
ESTADOS                  = Counter()
tokens_creados: list[str] = []


# ---------------------------------------------------------------------------
# Provision (sin eventlet: driver de Neo4j + identidad.py + HTTP real)
# ---------------------------------------------------------------------------
def emitir_token(driver, matricula: str, alcance: str, vigencia: float = 12 * 3600) -> str:
    """Mismo formato que /login; guarda su hash como la sesion vigente del alumno."""
    expira_en = time.time() + vigencia
    payload   = f"{matricula}.{alcance}.{expira_en}"
    firma     = hmac.new(API_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    token     = f"{payload}.{firma}"
    with driver.session() as s:
        s.execute_write(identidad.establecer_sesion, matricula,
                        hashlib.sha256(token.encode()).hexdigest(), expira_en)
    return token


def crear_tokens_qr(driver, tokens: list[str]) -> None:
    # Misma forma que server.create_token_record, en lote. Se replica aqui (2 lineas)
    # para no importar server.py (eventlet).
    with driver.session() as s:
        s.run("UNWIND $toks AS tok CREATE (t:Token {token: tok, used: false, warnings: 0})",
              toks=tokens)


def provisionar_alumnos(driver, n: int) -> list[dict]:
    """Crea n alumnos con sesion y dispositivo enrolado. Devuelve su material de firma."""
    usuarios = []
    for i in range(1, n + 1):
        matricula = f"CARGA{i:04d}"
        with driver.session() as s:
            s.execute_write(identidad.crear_alumno, matricula, f"Carga Alumno {i:03d}",
                            generate_password_hash(PASSWORD))
            # actualizar_password deja debe_cambiar_password=false -> sesion completa
            s.execute_write(identidad.actualizar_password, matricula,
                            generate_password_hash(PASSWORD))
        token   = emitir_token(driver, matricula, "completo")
        llave   = ec.generate_private_key(ec.SECP256R1())
        der_b64 = base64.b64encode(llave.public_key().public_bytes(DER, SPKI)).decode()
        r = requests.post(f"{HOST}/dispositivos/registrar",
                          headers={"Authorization": f"Bearer {token}"},
                          json={"llave_publica": der_b64,
                                "huella_dispositivo": f"huella-{matricula}"},
                          timeout=30)
        if r.status_code != 201:
            sys.exit(f"No se pudo enrolar {matricula}: {r.status_code} {r.text}")
        usuarios.append({"matricula": matricula, "token": token, "llave": llave})
    return usuarios


def reponer_lote_qr(driver, cantidad: int) -> None:
    COLA_QR.clear()
    nuevos = [uuid.uuid4().hex[:32] for _ in range(cantidad)]
    crear_tokens_qr(driver, nuevos)
    COLA_QR.extend(nuevos)
    tokens_creados.extend(nuevos)


# ---------------------------------------------------------------------------
# Usuario virtual de Locust
# ---------------------------------------------------------------------------
class Canjeador(FastHttpUser):
    wait_time = constant(0)  # sin pausa: cada usuario mantiene un canje en vuelo

    def on_start(self):
        global IDENTIDADES
        with _DISP_LOCK:
            self.ident = IDENTIDADES.popleft()

    @task
    def canje(self):
        try:
            qr = COLA_QR.popleft()
        except IndexError:
            raise StopUser()  # lote agotado: este usuario termina

        ts    = int(time.time())
        firma = base64.b64encode(
            self.ident["llave"].sign(f"{ts}/asistencia:{qr}".encode(),
                                     ec.ECDSA(hashes.SHA256()))).decode()
        headers = {
            "Authorization": f"Bearer {self.ident['token']}",
            "X-TIMESTAMP":   str(ts),
            "X-SIGNATURE":   firma,
            "X-Id-Prueba":   CORRIDA,
        }
        with self.client.post(f"/?token={qr}", headers=headers, name="canje",
                              catch_response=True) as resp:
            ESTADOS[resp.status_code] += 1
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"status {resp.status_code}")


# ---------------------------------------------------------------------------
# Corrida de un nivel de concurrencia
# ---------------------------------------------------------------------------
def correr_nivel(driver, nivel: int, usuarios: list[dict], canjes: int,
                 max_segundos: float) -> dict:
    global IDENTIDADES
    ESTADOS.clear()
    reponer_lote_qr(driver, canjes)
    IDENTIDADES = deque(usuarios[:nivel])

    env = Environment(user_classes=[Canjeador], host=HOST)
    env.create_local_runner()

    t0 = time.time()
    env.runner.start(nivel, spawn_rate=nivel)
    # Corre hasta agotar el lote (o hasta el tope de seguridad)
    while COLA_QR and (time.time() - t0) < max_segundos:
        gevent.sleep(0.2)
    # Deja drenar los canjes en vuelo y detiene
    gevent.sleep(0.5)
    env.runner.stop()
    env.runner.quit()
    t1 = time.time()

    st = env.stats.total
    duracion = t1 - t0
    exitos   = st.num_requests - st.num_failures
    return {
        "nivel_concurrencia":   nivel,
        "canjes_solicitados":   canjes,
        "peticiones_totales":   st.num_requests,
        "exitos":               exitos,
        "fallos":               st.num_failures,
        "tasa_exito":           (exitos / st.num_requests) if st.num_requests else None,
        "latencia_ms": {
            "min":  round(st.min_response_time) if st.min_response_time is not None else None,
            "p50":  st.get_response_time_percentile(0.50),
            "p95":  st.get_response_time_percentile(0.95),
            "p99":  st.get_response_time_percentile(0.99),
            "max":  round(st.max_response_time) if st.max_response_time is not None else None,
            "media": round(st.avg_response_time, 1),
        },
        "duracion_s":           round(duracion, 2),
        "throughput_rps":       round(st.num_requests / duracion, 1) if duracion else None,
        "codigos_http":         dict(ESTADOS),
    }


# ---------------------------------------------------------------------------
# Arranque / parada de server.py y limpieza
# ---------------------------------------------------------------------------
def puerto_escucha() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def arrancar_server(log_path: Path):
    proc = subprocess.Popen([sys.executable, "server.py"], cwd=str(BACKEND),
                            stdout=log_path.open("w"), stderr=subprocess.STDOUT)
    for _ in range(100):  # hasta ~20 s
        if puerto_escucha():
            return proc
        if proc.poll() is not None:
            sys.exit(f"server.py termino al arrancar; revisa {log_path}")
        time.sleep(0.2)
    proc.terminate()
    sys.exit("server.py no empezo a escuchar a tiempo")


def limpiar(driver) -> int:
    with driver.session() as s:
        s.run("MATCH (t:Token) WHERE t.token IN $toks DETACH DELETE t", toks=tokens_creados)
        s.run("MATCH (a:Alumno) WHERE a.matricula STARTS WITH 'CARGA' "
              "OPTIONAL MATCH (a)-[:USA]->(d:Dispositivo) DETACH DELETE a, d")
        n = s.run("MATCH (r:IntentoRechazado {id_prueba: $c}) "
                  "DELETE r RETURN count(*) AS n", c=CORRIDA).single()["n"]
    return n


# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--niveles", type=int, nargs="+", default=[60, 90],
                        help="Niveles de concurrencia (por defecto 60 90).")
    parser.add_argument("--canjes", type=int, default=3000,
                        help="Canjes a medir por nivel (tamano del lote de tokens).")
    parser.add_argument("--max-segundos", type=float, default=180,
                        help="Tope de seguridad por nivel.")
    args = parser.parse_args()

    ahora   = datetime.now()
    log_srv = BACKEND / "scripts" / f".server_carga_{ahora:%H%M%S}.log"

    proc = None
    gestionado = not puerto_escucha()
    if gestionado:
        print(f"Arrancando server.py (log: {log_srv.name})")
        proc = arrancar_server(log_srv)
    else:
        print(f"Usando el server.py que ya escucha en {HOST}")

    driver   = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    n_max    = max(args.niveles)
    niveles  = []
    try:
        print(f"Provisionando {n_max} alumnos con sesion y dispositivo enrolado...")
        usuarios = provisionar_alumnos(driver, n_max)
        for nivel in args.niveles:
            print(f"Midiendo nivel {nivel} ({args.canjes} canjes)...")
            niveles.append(correr_nivel(driver, nivel, usuarios, args.canjes, args.max_segundos))
    finally:
        rechazos_borrados = limpiar(driver)
        driver.close()
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()

    resultado = {
        "generado_en":      ahora.isoformat(timespec="seconds"),
        "endpoint":         "POST /?token=... (canje autenticado)",
        "host":             HOST,
        "modelo_carga":     "closed-loop, N usuarios FastHttpUser sin pausa (N canjes en vuelo)",
        "nota_latencia":    "ms de ida y vuelta medidos por Locust (servidor + pila local); "
                            "no incluye la firma ECDSA del cliente",
        "server_gestionado": gestionado,
        "niveles":          niveles,
    }

    EVIDENCIAS.mkdir(parents=True, exist_ok=True)
    base = EVIDENCIAS / f"carga_canje_{ahora:%Y-%m-%d_%H%M%S}"
    base.with_suffix(".json").write_text(json.dumps(resultado, indent=2, ensure_ascii=False),
                                         encoding="utf-8")
    texto = a_texto(resultado, rechazos_borrados)
    base.with_suffix(".txt").write_text(texto, encoding="utf-8")
    print("\n" + texto)
    print(f"Guardado en {base}.txt y .json")
    if log_srv.exists():
        log_srv.unlink()


def a_texto(r: dict, rechazos_borrados: int) -> str:
    L = [f"# Pruebas de carga del canje — {r['generado_en']}",
         f"# Endpoint: {r['endpoint']}",
         f"# Modelo: {r['modelo_carga']}",
         f"# Latencia: {r['nota_latencia']}",
         f"# server.py gestionado por el script: {r['server_gestionado']}",
         ""]
    cab = (f"{'conc.':>6}{'peticiones':>12}{'exito':>9}{'p50':>7}{'p95':>7}{'p99':>7}"
           f"{'max':>7}{'rps':>9}")
    L += [cab, "-" * len(cab)]
    for n in r["niveles"]:
        lat = n["latencia_ms"]
        tasa = f"{n['tasa_exito']*100:.1f}%" if n["tasa_exito"] is not None else "n/a"
        L.append(f"{n['nivel_concurrencia']:>6}{n['peticiones_totales']:>12}{tasa:>9}"
                 f"{lat['p50']:>7}{lat['p95']:>7}{lat['p99']:>7}{lat['max']:>7}"
                 f"{n['throughput_rps']:>9}")
    L += ["", "Detalle por nivel:"]
    for n in r["niveles"]:
        lat  = n["latencia_ms"]
        tasa = f"{n['tasa_exito']*100:.2f}%" if n["tasa_exito"] is not None else "n/a"
        L += [f"  Concurrencia {n['nivel_concurrencia']}:",
              f"    peticiones={n['peticiones_totales']}  exitos={n['exitos']}  "
              f"fallos={n['fallos']}  tasa_exito={tasa}",
              f"    latencia ms: min={lat['min']} p50={lat['p50']} p95={lat['p95']} "
              f"p99={lat['p99']} max={lat['max']} media={lat['media']}",
              f"    duracion={n['duracion_s']}s  throughput={n['throughput_rps']} req/s",
              f"    codigos HTTP: {n['codigos_http']}"]
    L += ["", f"Nodos IntentoRechazado del banco borrados en la limpieza: {rechazos_borrados} "
          f"(0 = ningun canje fue rechazado)"]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
