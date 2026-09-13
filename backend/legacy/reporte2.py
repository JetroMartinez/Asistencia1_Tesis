import os
import io
import json
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
from reportlab.lib.units import inch


load_dotenv()

NEO4J_URI      = os.getenv("NEO4J_URI")
NEO4J_USER     = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

HOST = "0.0.0.0"
PORT = 5560

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
                Consulta una matrícula para ver estadísticas personales, calendario de asistencia y descargar el reporte PDF vectorizado.
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
                        Descargar PDF personal
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

    c.setFillColor(HexColor("#0f172a"))
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x + 12, y + h - 25, str(value))

    c.setFillColor(HexColor("#64748b"))
    c.setFont("Helvetica", 8)
    c.drawString(x + 12, y + 12, str(title))


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


def generar_pdf_personal(matricula, personal):
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
    box_h = 55
    gap = 18

    draw_metric_box(c, 50, y, box_w, box_h, "Matrícula", personal["matricula"])
    draw_metric_box(c, 50 + box_w + gap, y, box_w, box_h, "Nombre", personal["nombre"])
    draw_metric_box(c, 50 + 2 * (box_w + gap), y, box_w, box_h, "Total de ingresos", personal["total_ingresos"])

    y -= 78

    draw_metric_box(c, 50, y, box_w, box_h, "Días asistidos", personal["total_dias"])
    draw_metric_box(c, 50 + box_w + gap, y, box_w, box_h, "Primer acceso", personal["primer_ingreso"])
    draw_metric_box(c, 50 + 2 * (box_w + gap), y, box_w, box_h, "Último acceso", personal["ultimo_ingreso"])

    y -= 78

    draw_metric_box(c, 50, y, box_w, box_h, "Hora más frecuente", personal["hora_mas_frecuente"])
    draw_metric_box(c, 50 + box_w + gap, y, box_w, box_h, "Día más frecuente", personal["dia_mas_frecuente"])

    y -= 235

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
        height - 370,
        width - 100,
        250,
        labels_horas,
        values_horas,
        "Distribución de accesos por hora"
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

    pdf_buffer = generar_pdf_personal(
        matricula,
        personal
    )

    filename = "reporte_asistencia_" + matricula + ".pdf"

    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename
    )


if __name__ == "__main__":
    app.run(
        host=HOST,
        port=PORT,
        debug=True
    )
