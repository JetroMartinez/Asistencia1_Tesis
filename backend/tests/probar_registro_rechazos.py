"""Pruebas del registro de intentos rechazados (:IntentoRechazado), datos sinteticos.

Requiere Neo4j con los alumnos sinteticos de scripts/sembrar_identidad.py y .env con
API_SECRET. Provoca cada motivo del catalogo en /login, /cambiar_password,
/dispositivos/registrar y el canje, y verifica por cada uno:

- que se creo exactamente un nodo con el motivo, endpoint y status esperados;
- que alumno_id solo aparece cuando se pudo atribuir (nunca con HMAC invalido);
- que ninguna propiedad contiene contrasenas, tokens de sesion, tokens QR ni firmas.

Cada peticion lleva X-Id-Prueba con un prefijo propio de la corrida; al final se
borran esos nodos, los BloqueoLogin y los Token creados, y se invalidan las sesiones
emitidas. Usa SIM0001 (canje, enrola una llave local como probar_canje_firmado.py),
SIM0002 (bloqueo por matricula) y SIM0003 (sin dispositivo activo).

Uso: python tests/probar_registro_rechazos.py (desde backend/)
"""
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import uuid

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

import identidad
import rechazos
import server

SPKI = serialization.PublicFormat.SubjectPublicKeyInfo
# Prefijos de documentacion (RFC 5737): no son IPs reales
IP_BASE         = "203.0.113.10"
IP_BLOQUEO_MAT  = "203.0.113.11"
IP_BLOQUEO_IP   = "203.0.113.12"
IP_SIN_ETIQUETA = "203.0.113.13"

CORRIDA = uuid.uuid4().hex[:16]
contador = 0
resultados = []
secretos = []          # valores que nunca deben aparecer en el grafo
tokens_creados = []
claves_bloqueo = []
sesiones = set()


def nuevo_id():
    global contador
    contador += 1
    return f"{CORRIDA}{contador:06x}"


def emitir_token(matricula, alcance, vigencia=600):
    # Mismo formato que /login; se guarda su hash como sesion vigente
    expira_en = time.time() + vigencia
    payload = f"{matricula}.{alcance}.{expira_en}"
    firma = hmac.new(os.getenv("API_SECRET").encode(), payload.encode(), hashlib.sha256).hexdigest()
    token = f"{payload}.{firma}"
    with server.driver.session() as s:
        s.execute_write(identidad.establecer_sesion, matricula,
                        hashlib.sha256(token.encode()).hexdigest(), expira_en)
    secretos.append(token)
    sesiones.add(matricula)
    return token


def nuevo_token_qr():
    token_qr = uuid.uuid4().hex[:32]
    with server.driver.session() as s:
        s.execute_write(server.create_token_record, token_qr)
    tokens_creados.append(token_qr)
    secretos.append(token_qr)
    return token_qr


def firmar(llave_privada, timestamp, token_qr):
    mensaje = f"{timestamp}/asistencia:{token_qr}".encode()
    firma = base64.b64encode(llave_privada.sign(mensaje, ec.ECDSA(hashes.SHA256()))).decode()
    secretos.append(firma)
    return firma


def nodos(id_prueba):
    with server.driver.session() as s:
        return [dict(r["r"]) for r in s.run(
            "MATCH (r:IntentoRechazado {id_prueba: $id}) RETURN r", id=id_prueba)]


def verificar(nombre, ok):
    resultados.append(ok)
    print(f"{'OK ' if ok else 'FALLA'} {nombre}")


def caso(nombre, metodo, ruta, motivo, status, alumno_id=None, rol=None, huella=None,
         headers=None, ip=IP_BASE, **kwargs):
    """Manda la peticion con X-Id-Prueba y comprueba el nodo que dejo."""
    id_prueba = nuevo_id()
    h = dict(headers or {})
    h["X-Id-Prueba"] = id_prueba
    r = getattr(cliente, metodo)(ruta, headers=h, environ_base={"REMOTE_ADDR": ip}, **kwargs)
    encontrados = nodos(id_prueba)
    n = encontrados[0] if len(encontrados) == 1 else {}
    ok = (r.status_code == status and len(encontrados) == 1
          and n.get("motivo") == motivo and n.get("status_http") == status
          and n.get("endpoint") == ruta.split("?")[0] and n.get("ip_origen") == ip
          and n.get("alumno_id") == alumno_id and n.get("rol_alumno") == rol
          and n.get("huella_dispositivo") == huella
          and isinstance(n.get("marca_tiempo"), float))
    verificar(f"{nombre}: esperado {status}/{motivo}, obtenido {r.status_code}/"
              f"{n.get('motivo')} nodos={len(encontrados)} alumno_id={n.get('alumno_id')} "
              f"rol={n.get('rol_alumno')} huella={str(n.get('huella_dispositivo'))[:20]}", ok)
    return r, n


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


cliente = server.app.test_client()

# ---------------------------------------------------------------------------
# /login
# ---------------------------------------------------------------------------
print("== /login")
caso("falta password", "post", "/login", "solicitud_invalida", 400,
     json={"matricula": "SIM0002"})

password_falso = f"password-falso-{uuid.uuid4().hex}"
secretos.append(password_falso)
claves_bloqueo += ["matricula:SIM0002", f"ip:{IP_BASE}", f"ip:{IP_BLOQUEO_MAT}",
                   f"ip:{IP_BLOQUEO_IP}", f"ip:{IP_SIN_ETIQUETA}"]
caso("password incorrecto, matricula existente", "post", "/login", "credenciales_invalidas",
     401, alumno_id="SIM0002", rol="objetivo_login",
     json={"matricula": "SIM0002", "password": password_falso})
claves_bloqueo.append("matricula:SIMNOEXISTE")
caso("matricula inexistente: no se guarda", "post", "/login", "credenciales_invalidas", 401,
     json={"matricula": "SIMNOEXISTE", "password": password_falso})

for _ in range(server.UMBRAL_INTENTOS_MATRICULA - 1):
    caso("intento previo al bloqueo por matricula", "post", "/login", "credenciales_invalidas",
         401, alumno_id="SIM0002", rol="objetivo_login", ip=IP_BLOQUEO_MAT,
         json={"matricula": "SIM0002", "password": password_falso})
caso("bloqueo por matricula", "post", "/login", "login_bloqueado_matricula", 429,
     ip=IP_BLOQUEO_MAT, json={"matricula": "SIM0002", "password": password_falso})

# Matriculas distintas e inexistentes: cuentan para la IP (sin dispositivo
# activo) sin llegar al umbral por matricula
for i in range(server.UMBRAL_INTENTOS_IP):
    m = f"SIMPRUEBA{CORRIDA[:6]}{i:03d}"
    claves_bloqueo.append(f"matricula:{m}")
    r =cliente.post("/login", headers={"X-Id-Prueba": nuevo_id()},
                     environ_base={"REMOTE_ADDR": IP_BLOQUEO_IP},
                     json={"matricula": m, "password": password_falso})
verificar(f"{server.UMBRAL_INTENTOS_IP} fallos desde una IP: ultimo {r.status_code}",
          r.status_code == 401)
claves_bloqueo.append("matricula:SIMPRUEBAULTIMA")
caso("bloqueo por IP", "post", "/login", "login_bloqueado_ip", 429, ip=IP_BLOQUEO_IP,
     json={"matricula": "SIMPRUEBAULTIMA", "password": password_falso})

# ---------------------------------------------------------------------------
# /cambiar_password
# ---------------------------------------------------------------------------
print("== /cambiar_password")
caso("sin Bearer", "post", "/cambiar_password", "no_autenticado", 401,
     json={"password_nuevo": password_falso})
caso("Bearer sin formato de token", "post", "/cambiar_password", "token_invalido", 401,
     headers=bearer("basura"), json={"password_nuevo": password_falso})

# Token con la matricula de otro y HMAC falso: alumno_id NO se atribuye
falsificado = f"SIM0003.cambiar_password.{time.time() + 600}.{'0' * 64}"
secretos.append(falsificado)
caso("HMAC invalido con matricula ajena: sin alumno_id", "post", "/cambiar_password",
     "token_invalido", 401, headers=bearer(falsificado),
     json={"password_nuevo": password_falso})

caso("token completo en endpoint de cambiar_password", "post", "/cambiar_password",
     "alcance_insuficiente", 403, alumno_id="SIM0001", rol="titular_sesion",
     headers=bearer(emitir_token("SIM0001", "completo")), json={"password_nuevo": password_falso})
caso("token expirado (HMAC valido)", "post", "/cambiar_password", "token_expirado", 401,
     alumno_id="SIM0001", rol="titular_sesion",
     headers=bearer(emitir_token("SIM0001", "cambiar_password", vigencia=-10)),
     json={"password_nuevo": password_falso})
revocado = emitir_token("SIM0001", "cambiar_password")
emitir_token("SIM0001", "cambiar_password")  # sobrescribe la sesion vigente
caso("sesion revocada por login posterior", "post", "/cambiar_password", "sesion_cerrada", 401,
     alumno_id="SIM0001", rol="titular_sesion", headers=bearer(revocado),
     json={"password_nuevo": password_falso})
corto = "corta-" + uuid.uuid4().hex[:4]
secretos.append(corto)
caso("password nuevo demasiado corto", "post", "/cambiar_password", "solicitud_invalida", 400,
     alumno_id="SIM0001", rol="titular_sesion",
     headers=bearer(emitir_token("SIM0001", "cambiar_password")),
     json={"password_nuevo": corto})

# ---------------------------------------------------------------------------
# /dispositivos/registrar
# ---------------------------------------------------------------------------
print("== /dispositivos/registrar")
llave_enrolada = ec.generate_private_key(ec.SECP256R1())
llave_ajena = ec.generate_private_key(ec.SECP256R1())
der_b64 = base64.b64encode(llave_enrolada.public_key().public_bytes(
    serialization.Encoding.DER, SPKI)).decode()
huella = f"sintetica-huella-rechazos-{CORRIDA}"

caso("sin Bearer: guarda la huella recibida", "post", "/dispositivos/registrar",
     "no_autenticado", 401, huella=huella,
     json={"llave_publica": der_b64, "huella_dispositivo": huella})
completo = emitir_token("SIM0001", "completo")
caso("llave que no es P-256", "post", "/dispositivos/registrar", "solicitud_invalida", 400,
     alumno_id="SIM0001", rol="titular_sesion", huella=huella, headers=bearer(completo),
     json={"llave_publica": "no-es-una-llave", "huella_dispositivo": huella})
larga = "h" * 300
caso("huella de 300 caracteres: se guarda recortada a 256", "post", "/dispositivos/registrar",
     "solicitud_invalida", 400, alumno_id="SIM0001", rol="titular_sesion", huella="h" * 256,
     headers=bearer(completo), json={"llave_publica": der_b64, "huella_dispositivo": larga})

r = cliente.post("/dispositivos/registrar", headers=bearer(completo),
                 json={"llave_publica": der_b64, "huella_dispositivo": huella})
verificar(f"preparacion: enrolar llave local para SIM0001, obtenido {r.status_code}",
          r.status_code == 201)

# ---------------------------------------------------------------------------
# Canje
# ---------------------------------------------------------------------------
print("== canje (/?token=...)")
token_a = nuevo_token_qr()
ahora = int(time.time())

caso("sin parametro token", "post", "/", "solicitud_invalida", 400)
caso("navegador: sin encabezados", "post", f"/?token={token_a}", "no_autenticado", 401,
     data={"nombre": "Suplantador", "matricula": "SIM9999"})
caso("sesion valida sin X-SIGNATURE", "post", f"/?token={token_a}", "encabezados_faltantes",
     401, alumno_id="SIM0001", rol="titular_sesion",
     headers={**bearer(completo), "X-TIMESTAMP": str(ahora)})
caso("X-TIMESTAMP no entero", "post", f"/?token={token_a}", "timestamp_fuera_ventana", 401,
     alumno_id="SIM0001", rol="titular_sesion",
     headers={**bearer(completo), "X-TIMESTAMP": "ayer", "X-SIGNATURE": "AAAA"})
viejo = ahora - 120
caso("timestamp -120 s con firma correcta", "post", f"/?token={token_a}",
     "timestamp_fuera_ventana", 401, alumno_id="SIM0001", rol="titular_sesion",
     headers={**bearer(completo), "X-TIMESTAMP": str(viejo),
              "X-SIGNATURE": firmar(llave_enrolada, viejo, token_a)})
_, n = caso("firma de llave no enrolada", "post", f"/?token={token_a}", "firma_invalida", 401,
            alumno_id="SIM0001", rol="titular_sesion", huella=huella,
            headers={**bearer(completo), "X-TIMESTAMP": str(ahora),
                     "X-SIGNATURE": firmar(llave_ajena, ahora, token_a)})
enc = json.loads(n.get("encabezados", "{}"))
verificar(f"encabezados saneados: solo presencia de Authorization/X-SIGNATURE, {enc}",
          enc.get("Authorization_presente") is True and enc.get("X-SIGNATURE_presente") is True
          and enc.get("X-TIMESTAMP") == str(ahora) and "Authorization" not in enc
          and "X-SIGNATURE" not in enc)
verificar("token_qr_hash es el prefijo de SHA-256 del token QR",
          n.get("token_qr_hash") == rechazos.huella_corta(token_a))
verificar("sesion_id es el prefijo de SHA-256 del token de sesion",
          n.get("sesion_id") == rechazos.huella_corta(completo))

sin_disp = emitir_token("SIM0003", "completo")
caso("alumno sin dispositivo activo", "post", f"/?token={token_a}", "sin_dispositivo_activo",
     403, alumno_id="SIM0003", rol="titular_sesion",
     headers={**bearer(sin_disp), "X-TIMESTAMP": str(ahora),
              "X-SIGNATURE": firmar(llave_ajena, ahora, token_a)})
caso("token QR inexistente (GET)", "get", f"/?token={uuid.uuid4().hex[:32]}",
     "token_qr_inexistente", 404)

ahora = int(time.time())
validos = {**bearer(completo), "X-TIMESTAMP": str(ahora),
           "X-SIGNATURE": firmar(llave_enrolada, ahora, token_a)}
id_exito = nuevo_id()
r = cliente.post(f"/?token={token_a}", headers={**validos, "X-Id-Prueba": id_exito})
verificar(f"canje valido: {r.status_code} y sin nodo de rechazo",
          r.status_code == 200 and nodos(id_exito) == [])
caso("replay autenticado", "post", f"/?token={token_a}", "token_reutilizado", 409,
     alumno_id="SIM0001", rol="titular_sesion", huella=huella, headers=validos)
caso("GET de token usado (warning.html)", "get", f"/?token={token_a}", "token_reutilizado", 200)

# ---------------------------------------------------------------------------
# X-Id-Prueba: instrumentacion, no decide
# ---------------------------------------------------------------------------
print("== X-Id-Prueba")
token_b = nuevo_token_qr()
respuestas = []
for etiqueta in (None, "NO-ES-HEX", nuevo_id()):
    h = {} if etiqueta is None else {"X-Id-Prueba": etiqueta}
    r = cliente.post(f"/?token={token_b}", headers=h, environ_base={"REMOTE_ADDR": IP_SIN_ETIQUETA})
    respuestas.append((r.status_code, r.get_json()))
verificar(f"misma respuesta con, sin y con X-Id-Prueba invalido: {respuestas}",
          len(set(json.dumps(x, sort_keys=True) for x in respuestas)) == 1)
with server.driver.session() as s:
    sin_etiqueta = s.run("MATCH (r:IntentoRechazado {ip_origen: $ip}) "
                         "RETURN r.id_prueba AS id", ip=IP_SIN_ETIQUETA).data()
verificar(f"X-Id-Prueba invalido no se guarda: {sin_etiqueta}",
          len(sin_etiqueta) == 3 and sum(x["id"] is None for x in sin_etiqueta) == 2)

# ---------------------------------------------------------------------------
# Ningun secreto en el grafo, y cobertura del catalogo
# ---------------------------------------------------------------------------
print("== secretos y cobertura")
with server.driver.session() as s:
    todos = [dict(r["r"]) for r in s.run(
        "MATCH (r:IntentoRechazado) WHERE r.id_prueba STARTS WITH $c OR r.ip_origen = $ip "
        "RETURN r", c=CORRIDA, ip=IP_SIN_ETIQUETA)]
texto = json.dumps(todos, ensure_ascii=False)
fugas = [s_[:12] + "..." for s_ in secretos if s_ in texto]
verificar(f"{len(todos)} nodos revisados contra {len(secretos)} secretos; fugas: {fugas}",
          not fugas and len(todos) > 0)
motivos_vistos = {n["motivo"] for n in todos}
faltantes = sorted(rechazos.MOTIVOS - motivos_vistos)
verificar(f"los {len(rechazos.MOTIVOS)} motivos del catalogo aparecen; faltan: {faltantes}",
          not faltantes)

# ---------------------------------------------------------------------------
# Limpieza
# ---------------------------------------------------------------------------
with server.driver.session() as s:
    s.run("MATCH (r:IntentoRechazado) WHERE r.id_prueba STARTS WITH $c OR r.ip_origen = $ip "
          "DELETE r", c=CORRIDA, ip=IP_SIN_ETIQUETA)
    s.run("MATCH (b:BloqueoLogin) WHERE b.clave IN $claves DELETE b", claves=claves_bloqueo)
    s.run("MATCH (t:Token) WHERE t.token IN $tokens DELETE t", tokens=tokens_creados)
    for m in sesiones:
        s.execute_write(identidad.invalidar_sesion, m)

print(f"\n{sum(resultados)}/{len(resultados)} verificaciones correctas")
sys.exit(0 if all(resultados) else 1)
