import os
import uuid
import secrets
from   datetime       import datetime
from   dotenv         import load_dotenv
from   flask          import Flask, jsonify, request, render_template, make_response
from   flask_socketio import SocketIO
from   neo4j          import GraphDatabase
from   werkzeug.security import check_password_hash, generate_password_hash
import eventlet
import hmac
import hashlib
import time

import identidad



# Initialize
load_dotenv()
NEO4J_URI      = os.getenv("NEO4J_URI")
NEO4J_USER     = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
S_IP           = "0.0.0.0"
S_PORT         = 26998
app            = Flask(__name__)
socketio       = SocketIO(app, cors_allowed_origins="*")
driver         = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

# /login: limite de intentos y sesion (valores de punto de partida, ver docs/decisiones.md)
UMBRAL_INTENTOS_MATRICULA = 5
UMBRAL_INTENTOS_IP        = 50
VENTANA_BLOQUEO_SEGUNDOS  = 15 * 60
DURACION_BLOQUEO_SEGUNDOS = 15 * 60
VIGENCIA_SESION_SEGUNDOS  = 8 * 60 * 60
# Minimo recomendado por NIST SP 800-63B para contrasenas elegidas por el
# usuario (no aplica el mismo criterio que el codigo inicial aleatorio de
# sembrar_identidad.py, que usa alfabeto amplio) [PENDIENTE: citas]
LONGITUD_MINIMA_PASSWORD  = 12
# Hash señuelo: se verifica contra este aunque la matricula no exista, para que una
# matricula inexistente no responda mas rapido que una con password incorrecto.
DUMMY_PASSWORD_HASH = generate_password_hash(secrets.token_hex(32))

with driver.session() as session:
    session.execute_write(identidad.asegurar_esquema_identidad)







# neo4j functions
def create_token_record(tx, token):
    query = (
        "CREATE (t:Token {token: $token, used: false, warnings: 0}) "
        "RETURN t.token"
    )
    tx.run(query, token=token)

def get_token_status(tx, token):
    query = (
        "MATCH (t:Token {token: $token}) "
        "RETURN t.used AS used, t.warnings AS warnings"
    )
    result = tx.run(query, token=token)
    record = result.single()
    return record if record else None

def update_token_used(tx, token, data):
    query = (
        "MATCH (t:Token {token: $token}) "
        "SET t.used  = true, "
        "t.nombre    = $nombre, "
        "t.matricula = $matricula, "
        "t.ip        = $ip, "
        "t.date      = $date, "
        "t.cookie    = $cookie, "
        "t.warnings  = 0 "
        "RETURN t"
    )
    tx.run(query, token=token, **data)

def increment_token_warnings(tx, token):
    query = (
        "MATCH (t:Token {token: $token}) "
        "SET t.warnings = t.warnings + 1 "
        "RETURN t.warnings AS warnings"
    )
    result = tx.run(query, token=token)
    record = result.single()
    return record['warnings'] if record else 0




# routes
'''@app.route('/get_token', methods=['GET']) # accessed by a local PC1
def get_new_token():
    token = uuid.uuid4().hex[:32]
    with driver.session() as session:
        session.execute_write(create_token_record, token)
    return jsonify({"token": token}), 200'''
@app.route('/get_token', methods=['GET'])
def get_new_token():
    timestamp = request.headers.get("X-TIMESTAMP")
    signature = request.headers.get("X-SIGNATURE")
    secret    = os.getenv("API_SECRET")

    if not timestamp or not signature:
        return jsonify({"error": "Missing security headers"}), 401

    try:
        timestamp = int(timestamp)
    except ValueError:
        return jsonify({"error": "Invalid timestamp"}), 401

    now = int(time.time())
    if abs(now - timestamp) > 30:
        return jsonify({"error": "Expired request"}), 401

    message = f"{timestamp}/get_token".encode()
    expected_signature = hmac.new(
        secret.encode(),
        message,
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(signature, expected_signature):
        return jsonify({"error": "Invalid signature"}), 401
    token = uuid.uuid4().hex[:32]
    with driver.session() as session:
        session.execute_write(create_token_record, token)

    return jsonify({"token": token}), 200


@app.route('/login', methods=['POST'])
def login():
    data      = request.get_json(silent=True) or {}
    matricula = data.get("matricula")
    password  = data.get("password")

    if not matricula or not password:
        return jsonify({"error": "Faltan matricula o password"}), 400

    ahora           = time.time()
    ip_address      = request.remote_addr
    clave_matricula = f"matricula:{matricula}"
    clave_ip        = f"ip:{ip_address}"

    with driver.session() as session:
        bloqueado_matricula = session.execute_read(identidad.esta_bloqueado, clave_matricula, ahora)
        bloqueado_ip        = session.execute_read(identidad.esta_bloqueado, clave_ip, ahora)
        if bloqueado_matricula or bloqueado_ip:
            return jsonify({"error": "Demasiados intentos. Intenta de nuevo mas tarde."}), 429

        alumno            = session.execute_read(identidad.obtener_alumno, matricula)
        tiene_dispositivo = session.execute_read(identidad.tiene_dispositivo_activo, matricula)

        password_hash          = alumno["password_hash"] if alumno else DUMMY_PASSWORD_HASH
        credenciales_validas   = alumno is not None and check_password_hash(password_hash, password)

        if not credenciales_validas:
            conteo_matricula = session.execute_write(
                identidad.registrar_intento_fallido, clave_matricula, ahora, VENTANA_BLOQUEO_SEGUNDOS
            )
            if conteo_matricula >= UMBRAL_INTENTOS_MATRICULA:
                session.execute_write(
                    identidad.marcar_bloqueo, clave_matricula, ahora + DURACION_BLOQUEO_SEGUNDOS
                )

            if not tiene_dispositivo:
                conteo_ip = session.execute_write(
                    identidad.registrar_intento_fallido, clave_ip, ahora, VENTANA_BLOQUEO_SEGUNDOS
                )
                if conteo_ip >= UMBRAL_INTENTOS_IP:
                    session.execute_write(
                        identidad.marcar_bloqueo, clave_ip, ahora + DURACION_BLOQUEO_SEGUNDOS
                    )

            return jsonify({"error": "Matricula o password incorrectos"}), 401

        session.execute_write(identidad.limpiar_intentos, clave_matricula)

        debe_cambiar_password = alumno["debe_cambiar_password"]
        alcance                = "cambiar_password" if debe_cambiar_password else "completo"
        expira_en               = ahora + VIGENCIA_SESION_SEGUNDOS

        secret  = os.getenv("API_SECRET")
        payload = f"{matricula}.{alcance}.{expira_en}"
        firma   = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        token   = f"{payload}.{firma}"

        sesion_token_hash = hashlib.sha256(token.encode()).hexdigest()
        session.execute_write(identidad.establecer_sesion, matricula, sesion_token_hash, expira_en)

    return jsonify({
        "token":                  token,
        "alcance":                alcance,
        "expira_en":              expira_en,
        "debe_cambiar_password":  debe_cambiar_password,
        "hora_servidor":          ahora,
    }), 200


def verificar_token_sesion(token, alcance_requerido):
    """Verifica un token de sesion de /login. Devuelve (matricula, None) si es
    valido para alcance_requerido, o (None, (mensaje, status)) si no."""
    if not token:
        return None, ("Falta el token de sesion", 401)

    try:
        payload, firma_recibida = token.rsplit(".", 1)
        matricula, alcance, expira_en_str = payload.split(".", 2)
        expira_en = float(expira_en_str)
    except ValueError:
        return None, ("Token con formato invalido", 401)

    secret = os.getenv("API_SECRET")
    firma_esperada = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(firma_recibida, firma_esperada):
        return None, ("Firma invalida", 401)

    if time.time() > expira_en:
        return None, ("Token expirado", 401)

    if alcance != alcance_requerido:
        return None, ("Alcance insuficiente para este endpoint", 403)

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with driver.session() as session:
        alumno = session.execute_read(identidad.obtener_alumno, matricula)

    if not alumno or alumno.get("sesion_token_hash") != token_hash:
        return None, ("Sesion invalida o revocada", 401)

    return matricula, None


@app.route('/cambiar_password', methods=['POST'])
def cambiar_password():
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return jsonify({"error": "Falta encabezado Authorization Bearer"}), 401
    token = auth_header[len("Bearer "):]

    matricula, error = verificar_token_sesion(token, "cambiar_password")
    if error:
        mensaje, status = error
        return jsonify({"error": mensaje}), status

    data           = request.get_json(silent=True) or {}
    password_nuevo = data.get("password_nuevo")

    if not password_nuevo or len(password_nuevo) < LONGITUD_MINIMA_PASSWORD:
        return jsonify({
            "error": f"La contrasena debe tener al menos {LONGITUD_MINIMA_PASSWORD} caracteres"
        }), 400

    with driver.session() as session:
        alumno = session.execute_read(identidad.obtener_alumno, matricula)
        if check_password_hash(alumno["password_hash"], password_nuevo):
            return jsonify({"error": "La contrasena nueva no puede ser igual a la actual"}), 400

        password_hash = generate_password_hash(password_nuevo)
        session.execute_write(identidad.actualizar_password, matricula, password_hash)
        session.execute_write(identidad.invalidar_sesion, matricula)

    return jsonify({"mensaje": "Contrasena actualizada. Inicia sesion de nuevo."}), 200


@app.route('/', methods=['GET', 'POST'])
def process_checkin():
    token = request.args.get('token')
    if not token:
        return "Error: Token no proporcionado.", 400

    ip_address   = request.remote_addr
    current_date = datetime.now().isoformat()

    # cookie
    user_cookie = request.cookies.get('user_tracker')
    if not user_cookie:
        user_cookie = uuid.uuid4().hex

    # Token status
    with driver.session() as session:
        status_record = session.execute_read(get_token_status, token)
        if not status_record:
            return "Error: Token inválido.", 404
        is_used = status_record['used']

        if is_used:
            # Repeated token warning
            new_warnings = session.execute_write(increment_token_warnings, token)
            response     = make_response(render_template('warning.html', warnings=new_warnings))
            response.set_cookie('user_tracker', user_cookie)
            return response
        # send the forms
        if request.method == 'GET':
            response = make_response(render_template('checkin_form.html', token=token))
            response.set_cookie('user_tracker', user_cookie) 
            return response

        # Process the forms with POST
        elif request.method == 'POST':
            nombre    = request.form.get('nombre')
            matricula = request.form.get('matricula')

            if not nombre or not matricula:
                return "Error: Faltan nombre o matrícula.", 400
            data_to_save = {
                'nombre':    nombre,
                'matricula': matricula,
                'ip':        ip_address,
                'date':      current_date,
                'cookie':    user_cookie
            }
            session.execute_write(update_token_used, token, data_to_save)

            # Send a socket signal to PC1
            socketio.emit('new_token_signal', {'message': 'Registro completado, solicitar nuevo token.'})
            print(f"Señal socket enviada a PC1")
            return render_template('success.html')


@socketio.on('connect')
def handle_connect():
    print(f'Cliente conectado por Socket.IO. SID: {request.sid}')

@socketio.on('disconnect')
def handle_disconnect():
    print(f'Cliente desconectado. SID: {request.sid}')

if __name__ == '__main__':
    socketio.run(app, host=S_IP, port=S_PORT, debug=False)
