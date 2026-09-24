"""Pruebas de POST /dispositivos/registrar con el test_client de Flask (datos sinteticos).

Requiere Neo4j con el alumno sintetico SIM0001 (scripts/sembrar_identidad.py) y .env
con API_SECRET. Emite el token de sesion con el mismo formato que /login y lo guarda
con identidad.establecer_sesion, asi verificar_token_sesion se ejercita completa.
Deja nodos Dispositivo sinteticos en SIM0001 y termina invalidando la sesion.

Uso: python tests/probar_registro_dispositivo.py (desde backend/)
"""
import base64
import hashlib
import hmac
import os
import sys
import time

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa

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


def pem(llave):
    return llave.public_bytes(serialization.Encoding.PEM, SPKI).decode()


def der_b64(llave):
    return base64.b64encode(llave.public_bytes(serialization.Encoding.DER, SPKI)).decode()


def dispositivos():
    with server.driver.session() as s:
        return s.run(
            "MATCH (:Alumno {matricula: $m})-[:USA]->(d:Dispositivo) "
            "RETURN d.activo AS activo, d.llave_publica AS llave ORDER BY d.creado_en",
            m=MATRICULA).data()


cliente = server.app.test_client()
p256_a = ec.generate_private_key(ec.SECP256R1()).public_key()
p256_b = ec.generate_private_key(ec.SECP256R1()).public_key()
p384 = ec.generate_private_key(ec.SECP384R1()).public_key()
rsa_k = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key()
ed = ed25519.Ed25519PrivateKey.generate().public_key()
HUELLA = "sintetica-huella-01"

resultados = []


def caso(nombre, esperado, token, cuerpo):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    r = cliente.post("/dispositivos/registrar", json=cuerpo, headers=headers)
    ok = r.status_code == esperado
    resultados.append(ok)
    print(f"{'OK ' if ok else 'FALLA'} {nombre}: esperado {esperado}, obtenido {r.status_code} {r.get_json()}")


token_limitado = emitir_token("cambiar_password")
caso("token de alcance cambiar_password", 403, token_limitado,
     {"llave_publica": pem(p256_a), "huella_dispositivo": HUELLA})

caso("sin token", 401, None, {"llave_publica": pem(p256_a), "huella_dispositivo": HUELLA})

token = emitir_token("completo")
caso("token con firma alterada", 401, token[:-1] + ("0" if token[-1] != "0" else "1"),
     {"llave_publica": pem(p256_a), "huella_dispositivo": HUELLA})

antes = len(dispositivos())
caso("P-256 en PEM", 201, token, {"llave_publica": pem(p256_a), "huella_dispositivo": HUELLA})
caso("P-256 en DER base64", 201, token, {"llave_publica": der_b64(p256_b), "huella_dispositivo": HUELLA})

nuevos = dispositivos()[antes:]
activos = [d for d in dispositivos() if d["activo"]]
ok = (len(nuevos) == 2 and not nuevos[0]["activo"] and nuevos[1]["activo"]
      and len(activos) == 1 and activos[0]["llave"] == pem(p256_b))
resultados.append(ok)
print(f"{'OK ' if ok else 'FALLA'} el anterior queda activo=false y solo hay un activo, normalizado a PEM")

caso("P-384", 400, token, {"llave_publica": pem(p384), "huella_dispositivo": HUELLA})
caso("RSA 2048", 400, token, {"llave_publica": pem(rsa_k), "huella_dispositivo": HUELLA})
caso("Ed25519", 400, token, {"llave_publica": der_b64(ed), "huella_dispositivo": HUELLA})
caso("base64 corrupto", 400, token, {"llave_publica": "no-es-base64!!", "huella_dispositivo": HUELLA})
caso("PEM truncado", 400, token, {"llave_publica": pem(p256_a)[:80], "huella_dispositivo": HUELLA})
caso("llave no string", 400, token, {"llave_publica": 123, "huella_dispositivo": HUELLA})
caso("falta huella", 400, token, {"llave_publica": pem(p256_a)})
caso("huella de 257 caracteres", 400, token, {"llave_publica": pem(p256_a), "huella_dispositivo": "x" * 257})
caso("cuerpo no JSON", 400, token, None)

der_fuera = bytearray(p256_a.public_bytes(serialization.Encoding.DER, SPKI))
der_fuera[-1] ^= 0x01  # altera la coordenada Y: el punto deja de estar sobre la curva
caso("P-256 con punto fuera de la curva", 400, token,
     {"llave_publica": base64.b64encode(bytes(der_fuera)).decode(), "huella_dispositivo": HUELLA})

activos = [d for d in dispositivos() if d["activo"]]
ok = len(activos) == 1 and activos[0]["llave"] == pem(p256_b)
resultados.append(ok)
print(f"{'OK ' if ok else 'FALLA'} los rechazos no cambiaron el dispositivo activo")

# No deja una sesion emitida por este script vigente en SIM0001
with server.driver.session() as s:
    s.execute_write(identidad.invalidar_sesion, MATRICULA)

print(f"\n{sum(resultados)}/{len(resultados)} verificaciones correctas")
sys.exit(0 if all(resultados) else 1)
