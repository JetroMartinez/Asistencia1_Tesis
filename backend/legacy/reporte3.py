import os
import io
import json
import base64
import hashlib
import uuid
import calendar
from datetime import datetime, date, timedelta
from collections import defaultdict
from dotenv import load_dotenv
from flask import Flask, request, render_template_string, send_file
from neo4j import GraphDatabase

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding


load_dotenv()

NEO4J_URI      = os.getenv("NEO4J_URI")
NEO4J_USER     = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

HOST = "0.0.0.0"
PORT = 5561

KEY_DIR = "firma_digital"
PRIVATE_KEY_PATH = os.path.join(KEY_DIR, "llave_privada_reporte.pem")
PUBLIC_KEY_PATH = os.path.join(KEY_DIR, "llave_publica_reporte.pem")
CERT_PATH = os.path.join(KEY_DIR, "certificado_reporte.pem")
LOG_PATH = os.path.join(KEY_DIR, "firmas_emitidas.jsonl")

CERT_COMMON_NAME = os.getenv("CERT_COMMON_NAME", "Sistema de Reportes de Asistencia")
CERT_ORGANIZATION = os.getenv("CERT_ORGANIZATION", "almxlvx.com")

app = Flask(__name__)

driver = GraphDatabase.driver(
    NEO4J_URI,
    auth=(NEO4J_USER, NEO4J_PASSWORD)
)


HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Reporte de asistencia</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

    <style>
        body {
            margin: 0;
            min-height: 100vh;
            font-family: Arial, sans-serif;
            background: #0f172a;
            color: white;
        }

        .page {
            width: 92%;
            max-width: 1250px;
            margin: 36px auto;
        }

        .box {
            background: rgba(255, 255, 255, 0.07);
            border-radius: 24px;
            padding: 30px;
            box-shadow: 0 22px 70px rgba(0, 0, 0, 0.38);
        }

        h1 {
            margin: 0 0 10px 0;
            font-size: 36px;
        }

        h2 {
            margin-top: 34px;
            font-size: 25px;
        }

        .subtitle {
            opacity: 0.78;
            margin-bottom: 25px;
            line-height: 1.5;
        }

        form {
            display: flex;
            gap: 12px;
            margin-bottom: 28px;
        }

        input {
            flex: 1;
            padding: 15px;
            font-size: 18px;
            border-radius: 14px;
            border: none;
            outline: none;
        }

        button, .pdf-button {
            padding: 15px 26px;
            font-size: 18px;
            font-weight: bold;
            border-radius: 14px;
            border: none;
            cursor: pointer;
            background: white;
            color: #0f172a;
            text-decoration: none;
            display: inline-block;
        }

        .cards {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
            gap: 18px;
            margin-bottom: 25px;
        }

        .card {
            background: rgba(255, 255, 255, 0.09);
            border-radius: 18px;
            padding: 20px;
            min-height: 92px;
        }

        .number {
            font-size: 34px;
            font-weight: bold;
            word-break: break-word;
        }

        .label {
            opacity: 0.78;
            margin-top: 7px;
            font-size: 15px;
        }

        .charts {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
            gap: 22px;
            margin-top: 18px;
        }

        .chart-card {
            background: white;
            color: #0f172a;
            border-radius: 20px;
            padding: 20px;
            min-height: 330px;
        }

        .chart-title {
            font-size: 18px;
            font-weight: bold;
            margin-bottom: 14px;
        }

        .report-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 16px;
            margin-top: 16px;
        }

        .report-item {
            background: rgba(255, 255, 255, 0.08);
            border-radius: 16px;
            padding: 17px;
        }

        .report-label {
            opacity: 0.7;
            font-size: 14px;
            margin-bottom: 6px;
        }

        .report-value {
            font-size: 19px;
            font-weight: bold;
            word-break: break-word;
        }

        .empty {
            padding: 18px;
            background: rgba(255, 255, 255, 0.08);
            border-radius: 16px;
            margin-top: 20px;
        }

        .calendar-wrap {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(310px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }

        .month {
            background: white;
            color: #0f172a;
            border-radius: 20px;
            padding: 18px;
        }

        .month-title {
            font-size: 20px;
            font-weight: bold;
            margin-bottom: 14px;
            text-align: center;
        }

        .weekdays, .days {
            display: grid;
            grid-template-columns: repeat(7, 1fr);
            gap: 6px;
        }

        .weekday {
            text-align: center;
            font-weight: bold;
            font-size: 13px;
            opacity: 0.7;
        }

        .day-cell {
            min-height: 38px;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            font-size: 14px;
            background: #e5e7eb;
            color: #111827;
        }

        .day-empty {
            background: transparent;
        }

        .day-present {
            background: #16a34a;
            color: white;
        }

        .day-absent {
            background: #dc2626;
            color: white;
        }

        .legend {
            display: flex;
            gap: 18px;
            align-items: center;
            margin-top: 14px;
            flex-wrap: wrap;
        }

        .legend-item {
            display: flex;
            gap: 7px;
            align-items: center;
            font-size: 15px;
            opacity: 0.9;
        }

        .legend-box {
            width: 18px;
            height: 18px;
            border-radius: 5px;
        }

        .green {
            background: #16a34a;
        }

        .red {
            background: #dc2626;
        }

        .gray {
            background: #e5e7eb;
        }

        @media (max-width: 700px) {
            form {
                flex-direction: column;
            }

            h1 {
                font-size: 29px;
            }

            .charts {
                grid-template-columns: 1fr;
            }

            .chart-card {
                min-height: 290px;
            }
        }
    </style>
</head>

<body>
    <div class="page">
        <div class="box">
            <h1>Reporte de asistencia</h1>

            <div class="subtitle">
                Consulta una matrícula para ver estadísticas personales, calendario de asistencia y descargar el reporte PDF vectorizado con firma digital y QR de validación.
            </div>

            <form method="POST">
                <input 
                    type="text" 
                    name="matricula" 
                    placeholder="Introduce la matrícula"
                    value="{{ matricula }}"
                >
                <button type="submit">Consultar</button>
            </form>

            <h2>Reporte general</h2>

            <div class="cards">
                <div class="card">
                    <div class="number">{{ general.total_ingresos }}</div>
                    <div class="label">Ingresos totales registrados</div>
                </div>

                <div class="card">
                    <div class="number">{{ general.total_matriculas }}</div>
                    <div class="label">Matrículas diferentes</div>
                </div>

                <div class="card">
                    <div class="number">{{ general.total_dias }}</div>
                    <div class="label">Días con registros</div>
                </div>

                <div class="card">
                    <div class="number">{{ general.total_ips }}</div>
                    <div class="label">IP diferentes detectadas</div>
                </div>
            </div>

            <div class="report-grid">
                <div class="report-item">
                    <div class="report-label">Primer ingreso registrado</div>
                    <div class="report-value">{{ general.primer_ingreso }}</div>
                </div>

                <div class="report-item">
                    <div class="report-label">Último ingreso registrado</div>
                    <div class="report-value">{{ general.ultimo_ingreso }}</div>
                </div>

                <div class="report-item">
                    <div class="report-label">Hora con más accesos</div>
                    <div class="report-value">{{ general.hora_mas_frecuente }}</div>
                </div>

                <div class="report-item">
                    <div class="report-label">Día con más accesos</div>
                    <div class="report-value">{{ general.dia_mas_frecuente }}</div>
                </div>
            </div>

            <div class="charts">
                <div class="chart-card">
                    <div class="chart-title">Distribución general por día</div>
                    <canvas id="chartGeneralDias"></canvas>
                </div>

                <div class="chart-card">
                    <div class="chart-title">Distribución general por hora</div>
                    <canvas id="chartGeneralHoras"></canvas>
                </div>
            </div>

            {% if busqueda_realizada %}
                <h2>Reporte personal por matrícula</h2>

                {% if personal.total_ingresos > 0 %}

                    <a class="pdf-button" href="/reporte_personal_pdf?matricula={{ matricula }}" target="_blank">
                        Descargar PDF personal firmado
                    </a>

                    <div class="cards" style="margin-top: 22px;">
                        <div class="card">
                            <div class="number">{{ personal.total_ingresos }}</div>
                            <div class="label">Ingresos de esta matrícula</div>
                        </div>

                        <div class="card">
                            <div class="number">{{ personal.total_dias }}</div>
                            <div class="label">Días asistidos</div>
                        </div>

                        <div class="card">
                            <div class="number">{{ personal.nombre }}</div>
                            <div class="label">Nombre registrado</div>
                        </div>

                        <div class="card">
                            <div class="number">{{ personal.hora_mas_frecuente }}</div>
                            <div class="label">Hora de acceso más frecuente</div>
                        </div>
                    </div>

                    <div class="report-grid">
                        <div class="report-item">
                            <div class="report-label">Matrícula consultada</div>
                            <div class="report-value">{{ personal.matricula }}</div>
                        </div>

                        <div class="report-item">
                            <div class="report-label">Primer acceso</div>
                            <div class="report-value">{{ personal.primer_ingreso }}</div>
                        </div>

                        <div class="report-item">
                            <div class="report-label">Último acceso</div>
                            <div class="report-value">{{ personal.ultimo_ingreso }}</div>
                        </div>

                        <div class="report-item">
                            <div class="report-label">Día con más accesos</div>
                            <div class="report-value">{{ personal.dia_mas_frecuente }}</div>
                        </div>

                        <div class="report-item">
                            <div class="report-label">IP más frecuente</div>
                            <div class="report-value">{{ personal.ip_mas_frecuente }}</div>
                        </div>

                        <div class="report-item">
                            <div class="report-label">Cookies diferentes detectadas</div>
                            <div class="report-value">{{ personal.total_cookies }}</div>
                        </div>
                    </div>

                    <div class="charts">
                        <div class="chart-card">
                            <div class="chart-title">Asistencia personal por día</div>
                            <canvas id="chartPersonalDias"></canvas>
                        </div>

                        <div class="chart-card">
                            <div class="chart-title">Hora de acceso personal</div>
                            <canvas id="chartPersonalHoras"></canvas>
                        </div>
                    </div>

                    <h2>Calendario de asistencia</h2>

                    <div class="legend">
                        <div class="legend-item">
                            <div class="legend-box green"></div>
                            Día asistido
                        </div>

                        <div class="legend-item">
                            <div class="legend-box red"></div>
                            Día sin asistencia
                        </div>

                        <div class="legend-item">
                            <div class="legend-box gray"></div>
                            Fuera del rango
                        </div>
                    </div>

                    <div class="calendar-wrap">
                        {% for mes in calendario %}
                            <div class="month">
                                <div class="month-title">{{ mes.titulo }}</div>

                                <div class="weekdays">
                                    <div class="weekday">Lun</div>
                                    <div class="weekday">Mar</div>
                                    <div class="weekday">Mié</div>
                                    <div class="weekday">Jue</div>
                                    <div class="weekday">Vie</div>
                                    <div class="weekday">Sáb</div>
                                    <div class="weekday">Dom</div>
                                </div>

                                <div class="days">
                                    {% for d in mes.dias %}
                                        {% if d.numero == "" %}
                                            <div class="day-cell day-empty"></div>
                                        {% else %}
                                            <div class="day-cell {{ d.clase }}">
                                                {{ d.numero }}
                                            </div>
                                        {% endif %}
                                    {% endfor %}
                                </div>
                            </div>
                        {% endfor %}
                    </div>

                {% else %}
                    <div class="empty">
                        No se encontraron ingresos para la matrícula <b>{{ matricula }}</b>.
                    </div>
                {% endif %}
            {% endif %}
        </div>
    </div>

    <script>
        function makeBarChart(canvasId, labels, values, title) {
            const canvas = document.getElementById(canvasId);

            if (!canvas) {
                return;
            }

            new Chart(canvas, {
                type: "bar",
                data: {
                    labels: labels,
                    datasets: [{
                        label: title,
                        data: values
                    }]
                },
                options: {
                    responsive: true,
                    plugins: {
                        legend: {
                            display: true
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: {
                                precision: 0
                            }
                        }
                    }
                }
            });
        }

        function makeLineChart(canvasId, labels, values, title) {
            const canvas = document.getElementById(canvasId);

            if (!canvas) {
                return;
            }

            new Chart(canvas, {
                type: "line",
                data: {
                    labels: labels,
                    datasets: [{
                        label: title,
                        data: values,
                        tension: 0.25
                    }]
                },
                options: {
                    responsive: true,
                    plugins: {
                        legend: {
                            display: true
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: {
                                precision: 0
                            }
                        }
                    }
                }
            });
        }

        const generalDiasLabels = {{ general.grafica_dias_labels | safe }};
        const generalDiasValues = {{ general.grafica_dias_values | safe }};
        const generalHorasLabels = {{ general.grafica_horas_labels | safe }};
        const generalHorasValues = {{ general.grafica_horas_values | safe }};

        makeBarChart(
            "chartGeneralDias",
            generalDiasLabels,
            generalDiasValues,
            "Ingresos por día"
        );

        makeLineChart(
            "chartGeneralHoras",
            generalHorasLabels,
            generalHorasValues,
            "Ingresos por hora"
        );

        {% if busqueda_realizada and personal.total_ingresos > 0 %}
            const personalDiasLabels = {{ personal.grafica_dias_labels | safe }};
            const personalDiasValues = {{ personal.grafica_dias_values | safe }};
            const personalHorasLabels = {{ personal.grafica_horas_labels | safe }};
            const personalHorasValues = {{ personal.grafica_horas_values | safe }};

            makeBarChart(
                "chartPersonalDias",
                personalDiasLabels,
                personalDiasValues,
                "Ingresos personales por día"
            );

            makeLineChart(
                "chartPersonalHoras",
                personalHorasLabels,
                personalHorasValues,
                "Ingresos personales por hora"
            );
        {% endif %}
    </script>
</body>
</html>
"""


VALIDACION_HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Validación de firma digital</title>

    <style>
        * {
            box-sizing: border-box;
        }

        html {
            width: 100%;
            overflow-x: hidden;
        }

        body {
            margin: 0;
            width: 100%;
            min-height: 100vh;
            font-family: Arial, Helvetica, sans-serif;
            background:
                radial-gradient(circle at top left, rgba(255, 168, 150, 0.55), transparent 34%),
                linear-gradient(135deg, #fff7f2 0%, #ffe5dc 42%, #ffd1c4 100%);
            color: #2f1f1c;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 34px 18px;
            overflow-x: hidden;
        }

        .box {
            width: min(100%, 980px);
            background: rgba(255, 255, 255, 0.82);
            backdrop-filter: blur(14px);
            border: 1px solid rgba(255, 255, 255, 0.9);
            border-radius: 32px;
            padding: clamp(18px, 4vw, 34px);
            box-shadow: 0 30px 80px rgba(136, 61, 43, 0.22);
        }

        .header {
            border-radius: 26px;
            padding: clamp(20px, 4vw, 30px);
            color: white;
            box-shadow: 0 18px 40px rgba(255, 128, 103, 0.28);
            margin-bottom: 24px;
        }

        .status {
            display: flex;
            align-items: center;
            gap: 14px;
            font-size: clamp(28px, 6vw, 42px);
            font-weight: 900;
            letter-spacing: -0.8px;
            line-height: 1.05;
        }

        .header-text {
            margin-top: 14px;
            font-size: clamp(17px, 3.8vw, 21px);
            line-height: 1.45;
            opacity: 0.96;
        }

        .ok-badge {
            background: linear-gradient(135deg, #16a34a, #86efac);
        }

        .bad-badge {
            background: linear-gradient(135deg, #dc2626, #fca5a5);
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(min(270px, 100%), 1fr));
            gap: 16px;
        }

        .item {
            min-width: 0;
            background: #fffaf7;
            padding: clamp(16px, 4vw, 22px);
            border-radius: 22px;
            border: 1px solid rgba(255, 172, 150, 0.38);
            box-shadow: 0 12px 26px rgba(136, 61, 43, 0.08);
            overflow: hidden;
        }

        .item.full {
            grid-column: 1 / -1;
        }

        .label {
            color: #9a5a4d;
            font-size: clamp(13px, 3vw, 16px);
            font-weight: 800;
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 0.6px;
            line-height: 1.25;
        }

        .value {
            color: #2f1f1c;
            font-size: clamp(19px, 4.5vw, 24px);
            font-weight: 800;
            line-height: 1.32;
            overflow-wrap: anywhere;
            word-break: break-word;
        }

        .value.mono {
            font-family: Consolas, Monaco, "Courier New", monospace;
            font-size: clamp(13px, 3.4vw, 17px);
            font-weight: 700;
            line-height: 1.55;
            background: #fff1eb;
            border-radius: 16px;
            padding: 14px;
            border: 1px dashed rgba(210, 95, 70, 0.35);
            overflow-wrap: anywhere;
            word-break: break-all;
            max-width: 100%;
        }

        @media (max-width: 700px) {
            body {
                align-items: flex-start;
                padding: 16px 12px;
            }

            .box {
                border-radius: 24px;
                padding: 16px;
            }

            .header {
                border-radius: 22px;
                margin-bottom: 18px;
            }

            .grid {
                grid-template-columns: 1fr;
                gap: 13px;
            }

            .item {
                border-radius: 18px;
            }
        }

        @media (max-width: 380px) {
            body {
                padding: 10px 8px;
            }

            .box {
                padding: 12px;
                border-radius: 20px;
            }

            .header {
                padding: 18px;
                border-radius: 18px;
            }

            .status {
                font-size: 26px;
            }

            .header-text {
                font-size: 16px;
            }

            .value {
                font-size: 18px;
            }

            .value.mono {
                font-size: 12px;
                padding: 12px;
            }
        }
    </style>
</head>

<body>
    <div class="box">
        {% if valido %}
            <div class="header ok-badge">
                <div class="status">
                    <div>Firma válida</div>
                </div>
                <div class="header-text">
                    El reporte fue localizado en el registro de firmas y su contenido coincide con la firma digital emitida.
                </div>
            </div>
        {% else %}
            <div class="header bad-badge">
                <div class="status">
                    <div>Firma no válida</div>
                </div>
                <div class="header-text">
                    No fue posible validar la firma digital del reporte. El archivo o el registro podrían no coincidir.
                </div>
            </div>
        {% endif %}

        <div class="grid">
            <div class="item">
                <div class="label">Matrícula</div>
                <div class="value">{{ registro.matricula }}</div>
            </div>

            <div class="item">
                <div class="label">Nombre</div>
                <div class="value">{{ registro.nombre }}</div>
            </div>

            <div class="item">
                <div class="label">Fecha de emisión</div>
                <div class="value">{{ registro.fecha_emision }}</div>
            </div>

            <div class="item">
                <div class="label">Archivo generado</div>
                <div class="value">{{ registro.archivo_pdf }}</div>
            </div>

            <div class="item full">
                <div class="label">ID de validación</div>
                <div class="value mono">{{ registro.id_validacion }}</div>
            </div>

            <div class="item full">
                <div class="label">Hash SHA-256 del reporte firmado</div>
                <div class="value mono">{{ registro.hash_reporte }}</div>
            </div>

            <div class="item full">
                <div class="label">Huella SHA-256 del certificado</div>
                <div class="value mono">{{ registro.huella_certificado }}</div>
            </div>
        </div>
    </div>
</body>
</html>
"""


def obtener_registros_generales(tx):
    query = """
    MATCH (t:Token)
    WHERE t.used = true
    RETURN
        t.nombre AS nombre,
        t.matricula AS matricula,
        t.date AS date,
        t.ip AS ip,
        t.cookie AS cookie,
        t.warnings AS warnings
    ORDER BY t.date ASC
    """

    result = tx.run(query)
    registros = []

    for record in result:
        registros.append({
            "nombre": record["nombre"],
            "matricula": record["matricula"],
            "date": record["date"],
            "ip": record["ip"],
            "cookie": record["cookie"],
            "warnings": record["warnings"]
        })

    return registros


def obtener_registros_por_matricula(tx, matricula):
    query = """
    MATCH (t:Token)
    WHERE t.used = true AND t.matricula = $matricula
    RETURN
        t.nombre AS nombre,
        t.matricula AS matricula,
        t.date AS date,
        t.ip AS ip,
        t.cookie AS cookie,
        t.warnings AS warnings
    ORDER BY t.date ASC
    """

    result = tx.run(query, matricula=matricula)
    registros = []

    for record in result:
        registros.append({
            "nombre": record["nombre"],
            "matricula": record["matricula"],
            "date": record["date"],
            "ip": record["ip"],
            "cookie": record["cookie"],
            "warnings": record["warnings"]
        })

    return registros


def convertir_fecha(fecha_guardada):
    try:
        return datetime.fromisoformat(fecha_guardada)
    except Exception:
        return None


def valor_mas_frecuente(diccionario):
    if not diccionario:
        return "Sin datos"

    mayor_clave = None
    mayor_valor = -1

    for clave, valor in diccionario.items():
        if valor > mayor_valor:
            mayor_clave = clave
            mayor_valor = valor

    return str(mayor_clave) + " (" + str(mayor_valor) + ")"


def construir_reporte(registros, matricula_consultada=""):
    total_ingresos = len(registros)

    conteo_dias = defaultdict(int)
    conteo_horas = defaultdict(int)
    conteo_ips = defaultdict(int)

    matriculas = set()
    ips = set()
    cookies = set()
    fechas_validas = []
    nombre = ""

    for registro in registros:
        fecha_guardada = registro.get("date", "")
        fecha = convertir_fecha(fecha_guardada)

        if fecha:
            dia = fecha.strftime("%Y-%m-%d")
            hora = fecha.strftime("%H:00")
            conteo_dias[dia] += 1
            conteo_horas[hora] += 1
            fechas_validas.append(fecha)

        matricula = registro.get("matricula")

        if matricula:
            matriculas.add(matricula)

        ip = registro.get("ip")

        if ip:
            ips.add(ip)
            conteo_ips[ip] += 1

        cookie = registro.get("cookie")

        if cookie:
            cookies.add(cookie)

        if not nombre and registro.get("nombre"):
            nombre = registro.get("nombre")

    dias_ordenados = sorted(conteo_dias.keys())
    horas_ordenadas = sorted(conteo_horas.keys())

    grafica_dias_labels = dias_ordenados
    grafica_dias_values = []

    for dia in dias_ordenados:
        grafica_dias_values.append(conteo_dias[dia])

    grafica_horas_labels = horas_ordenadas
    grafica_horas_values = []

    for hora in horas_ordenadas:
        grafica_horas_values.append(conteo_horas[hora])

    if fechas_validas:
        primer_ingreso = min(fechas_validas).strftime("%Y-%m-%d %H:%M:%S")
        ultimo_ingreso = max(fechas_validas).strftime("%Y-%m-%d %H:%M:%S")
    else:
        primer_ingreso = "Sin datos"
        ultimo_ingreso = "Sin datos"

    reporte = {
        "matricula": matricula_consultada,
        "nombre": nombre if nombre else "Sin datos",
        "total_ingresos": total_ingresos,
        "total_matriculas": len(matriculas),
        "total_dias": len(conteo_dias),
        "total_ips": len(ips),
        "total_cookies": len(cookies),
        "primer_ingreso": primer_ingreso,
        "ultimo_ingreso": ultimo_ingreso,
        "hora_mas_frecuente": valor_mas_frecuente(conteo_horas),
        "dia_mas_frecuente": valor_mas_frecuente(conteo_dias),
        "ip_mas_frecuente": valor_mas_frecuente(conteo_ips),
        "grafica_dias_labels": json.dumps(grafica_dias_labels),
        "grafica_dias_values": json.dumps(grafica_dias_values),
        "grafica_horas_labels": json.dumps(grafica_horas_labels),
        "grafica_horas_values": json.dumps(grafica_horas_values),
        "dias_asistidos": set(conteo_dias.keys()),
        "fechas_validas": fechas_validas
    }

    return reporte


def construir_calendario_html(fechas_validas, dias_asistidos):
    calendario = []

    if not fechas_validas:
        return calendario

    fecha_inicio = min(fechas_validas).date()
    fecha_fin = max(fechas_validas).date()

    actual = date(fecha_inicio.year, fecha_inicio.month, 1)
    ultimo = date(fecha_fin.year, fecha_fin.month, 1)

    nombres_meses = [
        "",
        "Enero",
        "Febrero",
        "Marzo",
        "Abril",
        "Mayo",
        "Junio",
        "Julio",
        "Agosto",
        "Septiembre",
        "Octubre",
        "Noviembre",
        "Diciembre"
    ]

    while actual <= ultimo:
        year = actual.year
        month = actual.month
        _, total_dias_mes = calendar.monthrange(year, month)

        primer_dia = date(year, month, 1)
        offset = primer_dia.weekday()

        dias = []

        for _ in range(offset):
            dias.append({
                "numero": "",
                "clase": "day-empty"
            })

        for numero in range(1, total_dias_mes + 1):
            d = date(year, month, numero)

            if d < fecha_inicio or d > fecha_fin:
                clase = ""
            else:
                clave = d.strftime("%Y-%m-%d")

                if clave in dias_asistidos:
                    clase = "day-present"
                else:
                    clase = "day-absent"

            dias.append({
                "numero": numero,
                "clase": clase
            })

        calendario.append({
            "titulo": nombres_meses[month] + " " + str(year),
            "dias": dias
        })

        if month == 12:
            actual = date(year + 1, 1, 1)
        else:
            actual = date(year, month + 1, 1)

    return calendario


def asegurar_material_criptografico():
    os.makedirs(KEY_DIR, exist_ok=True)

    if os.path.exists(PRIVATE_KEY_PATH) and os.path.exists(PUBLIC_KEY_PATH) and os.path.exists(CERT_PATH):
        return

    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=4096
    )

    public_key = private_key.public_key()

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "MX"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, CERT_ORGANIZATION),
        x509.NameAttribute(NameOID.COMMON_NAME, CERT_COMMON_NAME)
    ])

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.utcnow())
        .not_valid_after(datetime.utcnow() + timedelta(days=3650))
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=None),
            critical=True
        )
        .sign(private_key, hashes.SHA256())
    )

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )

    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    cert_pem = cert.public_bytes(serialization.Encoding.PEM)

    with open(PRIVATE_KEY_PATH, "wb") as f:
        f.write(private_pem)

    with open(PUBLIC_KEY_PATH, "wb") as f:
        f.write(public_pem)

    with open(CERT_PATH, "wb") as f:
        f.write(cert_pem)

    try:
        os.chmod(PRIVATE_KEY_PATH, 0o600)
    except Exception:
        pass


def cargar_llave_privada():
    asegurar_material_criptografico()

    with open(PRIVATE_KEY_PATH, "rb") as f:
        return serialization.load_pem_private_key(
            f.read(),
            password=None
        )


def cargar_certificado():
    asegurar_material_criptografico()

    with open(CERT_PATH, "rb") as f:
        return x509.load_pem_x509_certificate(f.read())


def obtener_huella_certificado():
    cert = cargar_certificado()
    fingerprint = cert.fingerprint(hashes.SHA256())
    return fingerprint.hex()


def crear_payload_firma(personal):
    payload = {
        "tipo": "reporte_personal_asistencia",
        "version": "1.0",
        "matricula": personal["matricula"],
        "nombre": personal["nombre"],
        "total_ingresos": personal["total_ingresos"],
        "total_dias": personal["total_dias"],
        "total_ips": personal["total_ips"],
        "total_cookies": personal["total_cookies"],
        "primer_ingreso": personal["primer_ingreso"],
        "ultimo_ingreso": personal["ultimo_ingreso"],
        "hora_mas_frecuente": personal["hora_mas_frecuente"],
        "dia_mas_frecuente": personal["dia_mas_frecuente"],
        "ip_mas_frecuente": personal["ip_mas_frecuente"],
        "grafica_dias_labels": json.loads(personal["grafica_dias_labels"]),
        "grafica_dias_values": json.loads(personal["grafica_dias_values"]),
        "grafica_horas_labels": json.loads(personal["grafica_horas_labels"]),
        "grafica_horas_values": json.loads(personal["grafica_horas_values"]),
        "dias_asistidos": sorted(list(personal["dias_asistidos"]))
    }

    payload_json = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":")
    )

    return payload_json.encode("utf-8")


def firmar_payload(payload_bytes):
    private_key = cargar_llave_privada()

    firma = private_key.sign(
        payload_bytes,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH
        ),
        hashes.SHA256()
    )

    return base64.b64encode(firma).decode("utf-8")


def verificar_firma_payload(payload_bytes, firma_b64):
    cert = cargar_certificado()
    public_key = cert.public_key()
    firma = base64.b64decode(firma_b64.encode("utf-8"))

    public_key.verify(
        firma,
        payload_bytes,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH
        ),
        hashes.SHA256()
    )

    return True


def obtener_base_validacion():
    base = os.getenv("BASE_VALIDATION_URL", "").strip()

    if base:
        return base.rstrip("/")

    return "https://validar.almxlvx.com" #request.host_url.rstrip("/")


def registrar_firma_log(registro):
    os.makedirs(KEY_DIR, exist_ok=True)

    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False, sort_keys=True) + "\n")


def buscar_registro_firma(id_validacion):
    if not os.path.exists(LOG_PATH):
        return None

    with open(LOG_PATH, "r", encoding="utf-8") as f:
        for line in f:
            try:
                registro = json.loads(line)
            except Exception:
                continue

            if registro.get("id_validacion") == id_validacion:
                return registro

    return None


def preparar_firma_reporte(personal, archivo_pdf):
    payload_bytes = crear_payload_firma(personal)
    hash_reporte = hashlib.sha256(payload_bytes).hexdigest()
    firma_b64 = firmar_payload(payload_bytes)

    id_validacion = uuid.uuid4().hex
    fecha_emision = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    huella_certificado = obtener_huella_certificado()

    validation_url = obtener_base_validacion() + "/validar_firma?id=" + id_validacion

    registro = {
        "id_validacion": id_validacion,
        "fecha_emision": fecha_emision,
        "matricula": personal["matricula"],
        "nombre": personal["nombre"],
        "hash_reporte": hash_reporte,
        "firma_b64": firma_b64,
        "huella_certificado": huella_certificado,
        "validation_url": validation_url,
        "archivo_pdf": archivo_pdf,
        "payload_b64": base64.b64encode(payload_bytes).decode("utf-8")
    }

    registrar_firma_log(registro)

    return registro


def wrap_text_by_width(c, text, max_width, font_name, font_size):
    text = str(text)
    words = text.split()
    lines = []
    current_line = ""

    for word in words:
        test_line = word if current_line == "" else current_line + " " + word

        if c.stringWidth(test_line, font_name, font_size) <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)

            if c.stringWidth(word, font_name, font_size) <= max_width:
                current_line = word
            else:
                broken = ""

                for char in word:
                    test_broken = broken + char

                    if c.stringWidth(test_broken, font_name, font_size) <= max_width:
                        broken = test_broken
                    else:
                        lines.append(broken)
                        broken = char

                current_line = broken

    if current_line:
        lines.append(current_line)

    return lines


def draw_text(c, text, x, y, size=10, bold=False, color=colors.black):
    c.setFillColor(color)

    if bold:
        c.setFont("Helvetica-Bold", size)
    else:
        c.setFont("Helvetica", size)

    c.drawString(x, y, str(text))


def draw_title(c, title, subtitle):
    width, height = letter

    c.setFillColor(HexColor("#0f172a"))
    c.rect(0, height - 88, width, 88, fill=1, stroke=0)

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(50, height - 42, title)

    c.setFont("Helvetica", 10)
    c.drawString(50, height - 62, subtitle)


def draw_footer(c, page_num):
    width, height = letter

    c.setFillColor(HexColor("#64748b"))
    c.setFont("Helvetica", 8)
    c.drawRightString(width - 50, 28, "Página " + str(page_num))


def draw_metric_box(c, x, y, w, h, title, value):
    c.setFillColor(HexColor("#f8fafc"))
    c.roundRect(x, y, w, h, 10, fill=1, stroke=0)

    c.setStrokeColor(HexColor("#e2e8f0"))
    c.roundRect(x, y, w, h, 10, fill=0, stroke=1)

    title_font = "Helvetica"
    title_size = 8
    value_font = "Helvetica-Bold"
    value_size = 9
    max_text_width = w - 24

    lines = wrap_text_by_width(
        c,
        value,
        max_text_width,
        value_font,
        value_size
    )

    max_lines = 3
    lines = lines[:max_lines]

    c.setFillColor(HexColor("#0f172a"))
    c.setFont(value_font, value_size)

    start_y = y + h - 19

    for i, line in enumerate(lines):
        c.drawString(x + 12, start_y - (i * 10), line)

    c.setFillColor(HexColor("#64748b"))
    c.setFont(title_font, title_size)
    c.drawString(x + 12, y + 10, str(title))


def draw_bar_chart(c, x, y, w, h, labels, values, title):
    c.setFillColor(HexColor("#ffffff"))
    c.roundRect(x, y, w, h, 10, fill=1, stroke=0)

    c.setStrokeColor(HexColor("#e2e8f0"))
    c.roundRect(x, y, w, h, 10, fill=0, stroke=1)

    c.setFillColor(HexColor("#0f172a"))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x + 14, y + h - 22, title)

    if not labels or not values:
        c.setFillColor(HexColor("#64748b"))
        c.setFont("Helvetica", 9)
        c.drawString(x + 14, y + h / 2, "Sin datos")
        return

    max_value = max(values)

    if max_value <= 0:
        max_value = 1

    chart_x = x + 32
    chart_y = y + 42
    chart_w = w - 55
    chart_h = h - 80

    c.setStrokeColor(HexColor("#cbd5e1"))
    c.line(chart_x, chart_y, chart_x, chart_y + chart_h)
    c.line(chart_x, chart_y, chart_x + chart_w, chart_y)

    total = len(values)
    gap = 4
    bar_w = max(4, (chart_w - gap * (total - 1)) / total)

    for i, value in enumerate(values):
        bx = chart_x + i * (bar_w + gap)
        bh = (value / max_value) * chart_h

        c.setFillColor(HexColor("#2563eb"))
        c.rect(bx, chart_y, bar_w, bh, fill=1, stroke=0)

        c.setFillColor(HexColor("#0f172a"))
        c.setFont("Helvetica", 6)
        c.drawCentredString(bx + bar_w / 2, chart_y + bh + 4, str(value))

        label = str(labels[i])

        if len(label) > 8:
            label = label[-5:]

        c.saveState()
        c.translate(bx + bar_w / 2, chart_y - 8)
        c.rotate(45)
        c.setFont("Helvetica", 5)
        c.drawString(0, 0, label)
        c.restoreState()


def draw_qr_vector(c, data, x, y, size):
    qr = QrCodeWidget(data)
    bounds = qr.getBounds()
    qr_w = bounds[2] - bounds[0]
    qr_h = bounds[3] - bounds[1]

    drawing = Drawing(size, size, transform=[
        size / qr_w,
        0,
        0,
        size / qr_h,
        0,
        0
    ])

    drawing.add(qr)
    renderPDF.draw(drawing, c, x, y)


def draw_signature_block(c, x, y, w, h, registro):
    c.setFillColor(HexColor("#f8fafc"))
    c.roundRect(x, y, w, h, 12, fill=1, stroke=0)

    c.setStrokeColor(HexColor("#cbd5e1"))
    c.roundRect(x, y, w, h, 12, fill=0, stroke=1)

    c.setFillColor(HexColor("#0f172a"))
    c.setFont("Helvetica-Bold", 13)
    c.drawString(x + 16, y + h - 24, "Firma digital del reporte")

    qr_size = 92
    draw_qr_vector(
        c,
        registro["validation_url"],
        x + w - qr_size - 16,
        y + 18,
        qr_size
    )

    c.setFont("Helvetica", 8)
    c.setFillColor(HexColor("#334155"))

    text_x = x + 16
    text_y = y + h - 44

    items = [
        ("ID", registro["id_validacion"]),
        ("Emisión", registro["fecha_emision"]),
        ("Hash SHA-256", registro["hash_reporte"]),
        ("Certificado SHA-256", registro["huella_certificado"]),
        ("Validación", registro["validation_url"])
    ]

    max_width = w - qr_size - 52

    for label, value in items:
        c.setFont("Helvetica-Bold", 7)
        c.drawString(text_x, text_y, label + ":")

        c.setFont("Helvetica", 7)
        lines = wrap_text_by_width(
            c,
            value,
            max_width - 82,
            "Helvetica",
            7
        )

        first = True

        for line in lines[:3]:
            if first:
                c.drawString(text_x + 82, text_y, line)
                first = False
            else:
                text_y -= 9
                c.drawString(text_x + 82, text_y, line)

        text_y -= 11


def draw_calendar_month(c, x, y, year, month, fecha_inicio, fecha_fin, dias_asistidos):
    nombres_meses = [
        "",
        "Enero",
        "Febrero",
        "Marzo",
        "Abril",
        "Mayo",
        "Junio",
        "Julio",
        "Agosto",
        "Septiembre",
        "Octubre",
        "Noviembre",
        "Diciembre"
    ]

    w = 238
    h = 185

    c.setFillColor(HexColor("#ffffff"))
    c.roundRect(x, y, w, h, 10, fill=1, stroke=0)

    c.setStrokeColor(HexColor("#e2e8f0"))
    c.roundRect(x, y, w, h, 10, fill=0, stroke=1)

    c.setFillColor(HexColor("#0f172a"))
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(x + w / 2, y + h - 22, nombres_meses[month] + " " + str(year))

    dias_semana = ["L", "M", "M", "J", "V", "S", "D"]
    cell = 28
    start_x = x + 20
    start_y = y + h - 48

    c.setFillColor(HexColor("#475569"))
    c.setFont("Helvetica-Bold", 7)

    for i, nombre in enumerate(dias_semana):
        c.drawCentredString(start_x + i * cell + cell / 2, start_y, nombre)

    _, total_dias_mes = calendar.monthrange(year, month)
    primer_dia = date(year, month, 1)
    offset = primer_dia.weekday()

    row = 0
    col = offset

    for numero in range(1, total_dias_mes + 1):
        d = date(year, month, numero)
        clave = d.strftime("%Y-%m-%d")

        cx = start_x + col * cell
        cy = start_y - 20 - row * 21

        if d < fecha_inicio or d > fecha_fin:
            fill_color = HexColor("#e5e7eb")
            text_color = HexColor("#111827")
        elif clave in dias_asistidos:
            fill_color = HexColor("#16a34a")
            text_color = colors.white
        else:
            fill_color = HexColor("#dc2626")
            text_color = colors.white

        c.setFillColor(fill_color)
        c.roundRect(cx + 2, cy - 7, 23, 17, 4, fill=1, stroke=0)

        c.setFillColor(text_color)
        c.setFont("Helvetica-Bold", 7)
        c.drawCentredString(cx + 13.5, cy - 2, str(numero))

        col += 1

        if col >= 7:
            col = 0
            row += 1


def obtener_meses_en_rango(fecha_inicio, fecha_fin):
    meses = []
    actual = date(fecha_inicio.year, fecha_inicio.month, 1)
    ultimo = date(fecha_fin.year, fecha_fin.month, 1)

    while actual <= ultimo:
        meses.append((actual.year, actual.month))

        if actual.month == 12:
            actual = date(actual.year + 1, 1, 1)
        else:
            actual = date(actual.year, actual.month + 1, 1)

    return meses


def generar_pdf_personal(matricula, personal, registro_firma):
    buffer = io.BytesIO()

    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    page_num = 1

    draw_title(
        c,
        "Reporte personal de asistencia",
        "Dr. Carlos Leopoldo Carreón Díaz de León"
    )

    draw_footer(c, page_num)

    y = height - 125

    draw_text(c, "Datos personales", 50, y, size=15, bold=True, color=HexColor("#0f172a"))

    y -= 75

    box_w = 160
    box_h = 62
    gap = 18

    draw_metric_box(c, 50, y, box_w, box_h, "Matrícula", personal["matricula"])
    draw_metric_box(c, 50 + box_w + gap, y, box_w, box_h, "Nombre", personal["nombre"])
    draw_metric_box(c, 50 + 2 * (box_w + gap), y, box_w, box_h, "Total de ingresos", personal["total_ingresos"])

    y -= 82

    draw_metric_box(c, 50, y, box_w, box_h, "Días asistidos", personal["total_dias"])
    draw_metric_box(c, 50 + box_w + gap, y, box_w, box_h, "Primer acceso", personal["primer_ingreso"])
    draw_metric_box(c, 50 + 2 * (box_w + gap), y, box_w, box_h, "Último acceso", personal["ultimo_ingreso"])

    y -= 82

    draw_metric_box(c, 50, y, box_w, box_h, "Hora más frecuente", personal["hora_mas_frecuente"])
    draw_metric_box(c, 50 + box_w + gap, y, box_w, box_h, "Día más frecuente", personal["dia_mas_frecuente"])


    y -= 230

    labels_dias = json.loads(personal["grafica_dias_labels"])
    values_dias = json.loads(personal["grafica_dias_values"])

    draw_bar_chart(
        c,
        50,
        y,
        width - 100,
        205,
        labels_dias,
        values_dias,
        "Distribución de asistencia por día"
    )

    c.showPage()
    page_num += 1

    draw_title(
        c,
        "Calendario de asistencia",
        "Verde: día asistido | Rojo: día sin asistencia dentro del rango"
    )

    draw_footer(c, page_num)

    fechas_validas = personal["fechas_validas"]
    dias_asistidos = personal["dias_asistidos"]

    if fechas_validas:
        fecha_inicio = min(fechas_validas).date()
        fecha_fin = max(fechas_validas).date()
        meses = obtener_meses_en_rango(fecha_inicio, fecha_fin)

        x_positions = [50, 324]
        y_current = height - 290
        col = 0

        for year, month in meses:
            if y_current < 85:
                c.showPage()
                page_num += 1

                draw_title(
                    c,
                    "Calendario de asistencia",
                    "Verde: día asistido | Rojo: día sin asistencia dentro del rango"
                )

                draw_footer(c, page_num)
                y_current = height - 290
                col = 0

            draw_calendar_month(
                c,
                x_positions[col],
                y_current,
                year,
                month,
                fecha_inicio,
                fecha_fin,
                dias_asistidos
            )

            col += 1

            if col >= 2:
                col = 0
                y_current -= 215

    else:
        draw_text(c, "Sin datos de calendario.", 50, height - 140, size=12)

    c.showPage()
    page_num += 1

    draw_title(
        c,
        "Distribución por hora",
        "almxlvx.com"
    )

    draw_footer(c, page_num)

    labels_horas = json.loads(personal["grafica_horas_labels"])
    values_horas = json.loads(personal["grafica_horas_values"])

    draw_bar_chart(
        c,
        50,
        height - 345,
        width - 100,
        230,
        labels_horas,
        values_horas,
        "Distribución de accesos por hora"
    )

    draw_signature_block(
        c,
        50,
        82,
        width - 100,
        160,
        registro_firma
    )

    c.save()

    buffer.seek(0)
    return buffer


@app.route("/", methods=["GET", "POST"])
def index():
    matricula = ""
    busqueda_realizada = False
    calendario = []

    with driver.session() as session:
        registros_generales = session.execute_read(obtener_registros_generales)

    general = construir_reporte(registros_generales)
    personal = construir_reporte([], "")

    if request.method == "POST":
        busqueda_realizada = True
        matricula = request.form.get("matricula", "").strip()

        if matricula:
            with driver.session() as session:
                registros_personales = session.execute_read(
                    obtener_registros_por_matricula,
                    matricula
                )

            personal = construir_reporte(
                registros_personales,
                matricula
            )

            calendario = construir_calendario_html(
                personal["fechas_validas"],
                personal["dias_asistidos"]
            )

    return render_template_string(
        HTML,
        matricula=matricula,
        busqueda_realizada=busqueda_realizada,
        general=general,
        personal=personal,
        calendario=calendario
    )


@app.route("/reporte_personal_pdf", methods=["GET"])
def reporte_personal_pdf():
    matricula = request.args.get("matricula", "").strip()

    if not matricula:
        return "Matrícula no proporcionada.", 400

    with driver.session() as session:
        registros_personales = session.execute_read(
            obtener_registros_por_matricula,
            matricula
        )

    if not registros_personales:
        return "No se encontraron registros para esa matrícula.", 404

    personal = construir_reporte(
        registros_personales,
        matricula
    )

    filename = "reporte_asistencia_" + matricula + ".pdf"

    registro_firma = preparar_firma_reporte(
        personal,
        filename
    )

    pdf_buffer = generar_pdf_personal(
        matricula,
        personal,
        registro_firma
    )

    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename
    )


@app.route("/validar_firma", methods=["GET"])
def validar_firma():
    id_validacion = request.args.get("id", "").strip()

    if not id_validacion:
        return "ID de validación no proporcionado.", 400

    registro = buscar_registro_firma(id_validacion)

    if not registro:
        return "No se encontró ese ID de validación.", 404

    valido = False

    try:
        payload_bytes = base64.b64decode(registro["payload_b64"].encode("utf-8"))
        hash_actual = hashlib.sha256(payload_bytes).hexdigest()

        if hash_actual == registro["hash_reporte"]:
            verificar_firma_payload(
                payload_bytes,
                registro["firma_b64"]
            )

            valido = True

    except Exception:
        valido = False

    return render_template_string(
        VALIDACION_HTML,
        valido=valido,
        registro=registro
    )


if __name__ == "__main__":
    asegurar_material_criptografico()

    app.run(
        host=HOST,
        port=PORT,
        debug=True
    )
