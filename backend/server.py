import os
import uuid
from   datetime       import datetime
from   dotenv         import load_dotenv
from   flask          import Flask, jsonify, request, render_template, make_response
from   flask_socketio import SocketIO
from   neo4j          import GraphDatabase
import eventlet
import hmac
import hashlib
import time



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
