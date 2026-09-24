"""Pruebas del canje autenticado en process_checkin (POST /?token=...), datos sinteticos.

Requiere Neo4j con el alumno sintetico SIM0001 (scripts/sembrar_identidad.py) y .env
con API_SECRET. Genera una llave EC P-256 local, la enrola por /dispositivos/registrar
(DER base64, como la app) y firma cada canje como lo haria Android Keystore
(SHA256withECDSA, firma DER en base64). Crea tokens QR sinteticos con
create_token_record y al final los borra, para no dejar registros de prueba en el
conjunto de datos de la tesis; termina invalidando la sesion de SIM0001.

Uso: python tests/probar_canje_firmado.py (desde backend/)
"""
import base64
import hashlib
import hmac
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
import server

MATRICULA = "SIM0001"
SPKI = serialization.PublicFormat.SubjectPublicKeyInfo


def emitir_token(alcance):
    # Mismo formato que /login, y se guarda su hash como sesion vigente
    expira_en = time.time() + 600
    payload = f"{MATRICULA}.{alcance}.{expira_en}"
    firma = hmac.new(os.getenv("API_SECRET").encode(), payload.encode(), hashlib.sha256).hexdigest()
    token = f"{payload}.{firma}"
    with server.driver.session() as s:
        s.execute_write(identidad.establecer_sesion, MATRICULA,
                        hashlib.sha256(token.encode()).hexdigest(), expira_en)
    return token


def nuevo_token_qr():
    token_qr = uuid.uuid4().hex[:32]
    with server.driver.session() as s:
        s.execute_write(server.create_token_record, token_qr)
    tokens_creados.append(token_qr)
    return token_qr


def estado_token(token_qr):
    with server.driver.session() as s:
        return s.run(
            "MATCH (t:Token {token: $t}) RETURN t.used AS used, t.warnings AS warnings, "
            "t.matricula AS matricula, t.nombre AS nombre", t=token_qr).single().data()


def firmar(llave_privada, timestamp, token_qr):
    mensaje = f"{timestamp}/asistencia:{token_qr}".encode()
    return base64.b64encode(llave_privada.sign(mensaje, ec.ECDSA(hashes.SHA256()))).decode()


def encabezados(timestamp=None, firma=None, bearer=None):
    h = {}
    if bearer:
        h["Authorization"] = f"Bearer {bearer}"
    if timestamp is not None:
        h["X-TIMESTAMP"] = str(timestamp)
    if firma:
        h["X-SIGNATURE"] = firma
    return h


def verificar(nombre, ok):
    resultados.append(ok)
    print(f"{'OK ' if ok else 'FALLA'} {nombre}")


def rechazo(nombre, token_qr, headers, form=None):
    # Un canje rechazado no debe consumir el token ni contar como reintento
    r = cliente.post(f"/?token={token_qr}", data=form or {}, headers=headers)
    t = estado_token(token_qr)
    ok = r.status_code == 401 and t["used"] is False and t["warnings"] == 0
    verificar(f"{nombre}: esperado 401 sin tocar el token, obtenido {r.status_code} "
              f"{r.get_json()} used={t['used']} warnings={t['warnings']}", ok)


cliente = server.app.test_client()
resultados = []
tokens_creados = []
FORM_FALSO = {"nombre": "Suplantador", "matricula": "SIM9999"}

llave_enrolada = ec.generate_private_key(ec.SECP256R1())
llave_ajena = ec.generate_private_key(ec.SECP256R1())

bearer = emitir_token("completo")
der_b64 = base64.b64encode(llave_enrolada.public_key().public_bytes(
    serialization.Encoding.DER, SPKI)).decode()
r = cliente.post("/dispositivos/registrar", headers={"Authorization": f"Bearer {bearer}"},
                 json={"llave_publica": der_b64, "huella_dispositivo": "sintetica-huella-canje"})
verificar(f"preparacion: enrolar llave P-256 local, obtenido {r.status_code}", r.status_code == 201)

with server.driver.session() as s:
    alumno = s.execute_read(identidad.obtener_alumno, MATRICULA)

token_a = nuevo_token_qr()
token_b = nuevo_token_qr()
ahora = int(time.time())

rechazo("navegador: solo formulario, sin encabezados", token_a, {}, FORM_FALSO)
rechazo("curl con sesion valida y sin X-SIGNATURE", token_a,
        encabezados(ahora, None, bearer), FORM_FALSO)
rechazo("firma de otra llave P-256 no enrolada", token_a,
        encabezados(ahora, firmar(llave_ajena, ahora, token_a), bearer))
viejo = ahora - 120
rechazo("timestamp fuera de ventana (-120 s), firma correcta", token_a,
        encabezados(viejo, firmar(llave_enrolada, viejo, token_a), bearer))
rechazo("firma valida de token_b enviada al canje de token_a", token_a,
        encabezados(ahora, firmar(llave_enrolada, ahora, token_b), bearer))

ahora = int(time.time())
validos = encabezados(ahora, firmar(llave_enrolada, ahora, token_a), bearer)
r = cliente.post(f"/?token={token_a}", data=FORM_FALSO, headers=validos)
t = estado_token(token_a)
verificar(f"firma valida (formulario con datos falsos): obtenido {r.status_code}, {t}",
          r.status_code == 200 and t["used"] is True and t["warnings"] == 0
          and t["matricula"] == MATRICULA and t["nombre"] == alumno["nombre"])

r = cliente.post(f"/?token={token_a}", data=FORM_FALSO, headers=validos)
t = estado_token(token_a)
# Pasa la autenticacion y cae en la logica existente de token ya usado (warning.html)
verificar(f"replay exacto del mismo token_qr: cuenta como reintento y no reescribe el "
          f"registro, obtenido {r.status_code}, {t}",
          r.status_code == 200 and t["used"] is True and t["warnings"] == 1
          and t["matricula"] == MATRICULA and t["nombre"] == alumno["nombre"])

with server.driver.session() as s:
    s.run("MATCH (t:Token) WHERE t.token IN $tokens DELETE t", tokens=tokens_creados)
    s.execute_write(identidad.invalidar_sesion, MATRICULA)

print(f"\n{sum(resultados)}/{len(resultados)} verificaciones correctas")
sys.exit(0 if all(resultados) else 1)
