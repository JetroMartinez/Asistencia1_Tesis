"""Pruebas de los cuatro fallos de la seccion 5 de CLAUDE.md, datos sinteticos.

1. Depurador de Werkzeug apagado: arranca visor.py y firma_calificaciones/app.py como
   subprocesos y comprueba que /console y los recursos ?__debugger__ no se sirven.
2. CORS de Socket.IO: el handshake con un Origin permitido pasa, con uno ajeno da 400,
   y sin Origin (cliente Python de visor.py) pasa.
3. URL del servidor externalizada: visor.py toma SERVER_URL del entorno y la pasa al
   QR y a la plantilla.
4. Cookie user_tracker con Secure, HttpOnly y SameSite=Lax, conservando su valor.

Requiere Neo4j y .env con API_SECRET; los puertos 5555 y 45001 deben estar libres.
Crea un token QR sintetico y al final lo borra junto con los IntentoRechazado de su IP.

Uso: python tests/probar_endurecimiento.py (desde backend/)
"""
import os
import re
import socket
import subprocess
import sys
import time
import uuid

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

# Antes de importar visor: debe tomar la URL del entorno, no un valor incrustado
SERVER_URL_PRUEBA = "https://servidor-prueba.invalid"
os.environ["SERVER_URL"] = SERVER_URL_PRUEBA

import requests

import server
import visor


def verificar(nombre, ok):
    resultados.append(ok)
    print(f"{'OK ' if ok else 'FALLA'} {nombre}")


def esperar_puerto(puerto, segundos=20):
    limite = time.time() + segundos
    while time.time() < limite:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", puerto)) == 0:
                return True
        time.sleep(0.3)
    return False


def probar_depurador(nombre, argv, cwd, puerto):
    proc = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    try:
        if not esperar_puerto(puerto):
            verificar(f"{nombre}: no arranco en el puerto {puerto}", False)
            return
        base = f"http://127.0.0.1:{puerto}"
        r = requests.get(f"{base}/console", timeout=10)
        verificar(f"{nombre}: /console esperado 404, obtenido {r.status_code}",
                  r.status_code == 404)
        r = requests.get(f"{base}/?__debugger__=yes&cmd=resource&f=debugger.js", timeout=10)
        sirve_js = "javascript" in r.headers.get("Content-Type", "") or "EVALEX" in r.text
        verificar(f"{nombre}: recurso debugger.js no servido "
                  f"(Content-Type {r.headers.get('Content-Type')})", not sirve_js)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


cliente = server.app.test_client()
# IP de documentacion (RFC 5737) propia de este script, para borrar sus rechazos
IP_PRUEBA = "203.0.113.23"
cliente.environ_base["REMOTE_ADDR"] = IP_PRUEBA
resultados = []
token_qr = uuid.uuid4().hex[:32]

try:
    print("== 1. depurador de Werkzeug")
    python = sys.executable
    probar_depurador("visor.py", [python, "visor.py"], BACKEND, 5555)
    probar_depurador("firma_calificaciones/app.py", [python, "app.py"],
                     os.path.join(BACKEND, "firma_calificaciones"), 45001)

    print("== 2. CORS de Socket.IO")
    handshake = "/socket.io/?EIO=4&transport=polling"
    for origen in server.SOCKETIO_CORS_ORIGINS:
        r = cliente.get(handshake, headers={"Origin": origen})
        verificar(f"Origin permitido {origen}: esperado 200, obtenido {r.status_code}",
                  r.status_code == 200)
    for origen in ("https://atacante.invalid", "null"):
        r = cliente.get(handshake, headers={"Origin": origen})
        verificar(f"Origin ajeno {origen}: esperado 400, obtenido {r.status_code}",
                  r.status_code == 400)
    r = cliente.get(handshake)
    verificar(f"sin Origin (cliente Python de visor.py): esperado 200, obtenido "
              f"{r.status_code}", r.status_code == 200)

    print("== 3. URL del servidor externalizada")
    verificar(f"visor.S_SERVER_URL tomada de SERVER_URL: {visor.S_SERVER_URL}",
              visor.S_SERVER_URL == SERVER_URL_PRUEBA)
    visor.current_token = "0" * 32  # evita pedir token al servidor
    pagina = visor.app.test_client().get("/").get_data(as_text=True)
    verificar("qr_display.html conecta Socket.IO a SERVER_URL",
              f'io("{SERVER_URL_PRUEBA}")' in pagina)
    verificar("el QR apunta a SERVER_URL", f"{SERVER_URL_PRUEBA}?token=" in pagina)
    verificar("la pagina del QR no contiene el dominio incrustado",
              "almxlvx" not in pagina.replace("ALMXLVX", ""))

    print("== 4. cookie user_tracker")
    with server.driver.session() as s:
        s.execute_write(server.create_token_record, token_qr)
    r = cliente.get(f"/?token={token_qr}")
    cookies = [c for c in r.headers.getlist("Set-Cookie") if c.startswith("user_tracker=")]
    cookie = cookies[0] if cookies else ""
    print(f"     Set-Cookie: {cookie}")
    atributos = {a.strip().split("=")[0].lower(): a.strip() for a in cookie.split(";")[1:]}
    verificar("GET del formulario emite user_tracker", bool(cookie))
    verificar("atributo Secure", "secure" in atributos)
    verificar("atributo HttpOnly", "httponly" in atributos)
    verificar("atributo SameSite=Lax", atributos.get("samesite", "").lower() == "samesite=lax")
    verificar("Path=/", atributos.get("path") == "Path=/")
    valor = re.match(r"user_tracker=([^;]*)", cookie)
    verificar("valor de 32 hex (uuid4)", bool(valor and re.fullmatch(r"[0-9a-f]{32}",
                                                                      valor.group(1))))

    # Un visitante que ya trae la cookie conserva el mismo valor (rastreo intacto)
    previo = uuid.uuid4().hex
    cliente.set_cookie("user_tracker", previo)
    r = cliente.get(f"/?token={token_qr}")
    cookie = next((c for c in r.headers.getlist("Set-Cookie")
                   if c.startswith("user_tracker=")), "")
    verificar("se conserva el valor que trae el cliente",
              cookie.startswith(f"user_tracker={previo};"))

    # Rama del token ya usado (warning.html): mismos atributos
    with server.driver.session() as s:
        s.run("MATCH (t:Token {token: $t}) SET t.used = true", t=token_qr)
    r = cliente.get(f"/?token={token_qr}")
    cookie = next((c for c in r.headers.getlist("Set-Cookie")
                   if c.startswith("user_tracker=")), "")
    print(f"     Set-Cookie (warning.html): {cookie}")
    verificar("warning.html emite la cookie con Secure, HttpOnly y SameSite=Lax",
              all(a in cookie for a in ("Secure", "HttpOnly", "SameSite=Lax")))
finally:
    with server.driver.session() as s:
        s.run("MATCH (t:Token {token: $t}) DELETE t", t=token_qr)
        s.run("MATCH (r:IntentoRechazado {ip_origen: $ip}) DELETE r", ip=IP_PRUEBA)

print(f"\n{sum(resultados)}/{len(resultados)} verificaciones correctas")
sys.exit(0 if all(resultados) else 1)
