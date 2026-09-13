import os
import json
from datetime import datetime
from collections import defaultdict
from dotenv import load_dotenv
from flask import Flask, request, render_template_string
from neo4j import GraphDatabase


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
            max-width: 1200px;
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

        button {
            padding: 15px 26px;
            font-size: 18px;
            font-weight: bold;
            border-radius: 14px;
            border: none;
            cursor: pointer;
            background: white;
            color: #0f172a;
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

        .small-note {
            opacity: 0.72;
            font-size: 14px;
            margin-top: 8px;
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
                Consulta una matrícula para ver estadísticas personales y revisa también el reporte general del sistema.
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

                    <div class="cards">
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
        fecha = datetime.fromisoformat(fecha_guardada)
        return fecha
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
        "grafica_horas_values": json.dumps(grafica_horas_values)
    }

    return reporte


@app.route("/", methods=["GET", "POST"])
def index():
    matricula = ""
    busqueda_realizada = False

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

    return render_template_string(
        HTML,
        matricula=matricula,
        busqueda_realizada=busqueda_realizada,
        general=general,
        personal=personal
    )


if __name__ == "__main__":
    app.run(
        host=HOST,
        port=PORT,
        debug=False
    )
