import threading
import time
import requests
import socketio
from   flask import Flask, render_template
import hmac
import hashlib
import time
import os
from   dotenv         import load_dotenv



S_SERVER_URL   = "https://prueba.almxlvx.com"
S_SOCKETIO_URL = "https://prueba.almxlvx.com"
PC1_IP         = "0.0.0.0"
PC1_PORT       = 5555
app            = Flask(__name__)
sio            = socketio.Client()
current_token  = None
load_dotenv()
API_SECRET = os.getenv("API_SECRET")


# socket routes
@sio.event
def connect():
    print(' Conectado al Servido')

@sio.event
def disconnect():
    print('Desconectado del Servidor')

@sio.on('new_token_signal') # handle the server signal
def on_new_token_signal(data):
    global current_token
    print(f"New token signal received: {data.get('message')}")
    current_token = None

def start_socketio_client():
    while True:
        try:
            sio.connect(S_SOCKETIO_URL)
            sio.wait()
        except Exception as e:
            print(f"Connection error: {e}. Retry in 5 seconds...")
            time.sleep(5)




# flask routes
@app.route('/')
def index():
    global current_token
    '''if current_token is None:
        try:
            print("Requesting a new token...")
            response      = requests.get(f"{S_SERVER_URL}/get_token")
            response.raise_for_status()
            data          = response.json()
            current_token = data.get('token')'''
    if current_token is None:
        try:
            print("Requesting a new token...")
            # --- generar timestamp y firma HMAC ---
            timestamp = str(int(time.time()))
            message   = f"{timestamp}/get_token".encode()
            signature = hmac.new(
                API_SECRET.encode(),
                message,
                hashlib.sha256
            ).hexdigest()
            # --- hacer la petición al servidor con headers seguros ---
            response = requests.get(
                f"{S_SERVER_URL}/get_token",
                headers={
                    "X-TIMESTAMP": timestamp,
                    "X-SIGNATURE": signature
                }
            )
            response.raise_for_status()
            data          = response.json()
            current_token = data.get('token')

        except requests.exceptions.RequestException as e:
            return f"Connection error: {e}.", 500
    # generate the final ul
    qr_url = f"{S_SERVER_URL}?token={current_token}"
    return render_template('qr_display.html', token=current_token, qr_url=qr_url)




if __name__ == '__main__':
    sio_thread = threading.Thread(target=start_socketio_client, daemon=True)
    sio_thread.start()
    print(f"PC1 Server (Web) corriendo en http://{PC1_IP}:{PC1_PORT}")
    app.run(host=PC1_IP, port=PC1_PORT, debug=True, use_reloader=False)
