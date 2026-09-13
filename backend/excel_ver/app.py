import os
import re
import uuid
import unicodedata
import difflib
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv
from flask import Flask, request, render_template_string, send_file
from werkzeug.utils import secure_filename
from neo4j import GraphDatabase

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.pdfbase.pdfmetrics import stringWidth


load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

S_IP = "0.0.0.0"
S_PORT = 45002

UPLOAD_DIR = "uploads_excel"
RESULT_DIR = "resultados_excel"
LOGO_DIR = "logos_pdf"

DOMAIN_NAME = "almxlvx.com"
FUZZY_LIMIT = 0.82

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(RESULT_DIR, exist_ok=True)
os.makedirs(LOGO_DIR, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024

driver = GraphDatabase.driver(
    NEO4J_URI,
    auth=(NEO4J_USER, NEO4J_PASSWORD)
)


HTML = """
<!doctype html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <title>Firma de calificaciones</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">

    <style>
        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            background: #080808;
            color: #f4efe4;
            font-family: Arial, sans-serif;
        }

        .wrap {
            max-width: 1220px;
            margin: 38px auto;
            padding: 24px;
        }

        .card {
            background: #141414;
            border: 1px solid #2e2a22;
            border-radius: 16px;
            padding: 28px;
            box-shadow: 0 24px 70px rgba(0,0,0,.5);
        }

        .banner {
            background: linear-gradient(135deg, #000000, #141414, #231d12);
            border: 1px solid #4b3f28;
            border-radius: 16px;
            padding: 26px;
            margin-bottom: 26px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 18px;
        }

        h1 {
            margin: 0;
            font-size: 34px;
            letter-spacing: -.5px;
            color: #fff5d8;
        }

        h2 {
            color: #fff1c8;
            margin-top: 32px;
        }

        .sub {
            color: #bdb5a5;
            margin-top: 8px;
            line-height: 1.5;
        }

        .domain {
            color: #d2ad59;
            font-weight: bold;
            letter-spacing: .5px;
            white-space: nowrap;
        }

        label {
            display: block;
            margin-top: 17px;
            color: #efe6d0;
            font-weight: bold;
        }

        input[type=text],
        input[type=file] {
            width: 100%;
            margin-top: 8px;
            padding: 14px;
            border-radius: 12px;
            border: 1px solid #4a402d;
            background: #0c0c0c;
            color: #efe7d4;
            font-size: 15px;
        }

        input[type=file] {
            border-style: dashed;
        }

        .form-grid {
            display: grid;
            grid-template-columns: 1fr 180px;
            gap: 16px;
        }

        .checks {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 14px;
            margin-top: 22px;
        }

        .check {
            background: #0c0c0c;
            border: 1px solid #302a1e;
            border-radius: 12px;
            padding: 14px;
            color: #d9d0be;
            line-height: 1.4;
        }

        .check input {
            transform: scale(1.2);
            margin-right: 8px;
        }

        button,
        .btn {
            display: inline-block;
            margin-top: 20px;
            border: 0;
            border-radius: 10px;
            background: #d0a84f;
            color: #0d0d0d;
            font-weight: bold;
            padding: 13px 20px;
            cursor: pointer;
            text-decoration: none;
        }

        button:hover,
        .btn:hover {
            background: #efca6b;
        }

        .btn + .btn {
            margin-left: 10px;
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 14px;
            margin: 24px 0;
        }

        .stat {
            background: #0c0c0c;
            border: 1px solid #332d21;
            border-radius: 12px;
            padding: 16px;
        }

        .num {
            font-size: 31px;
            font-weight: bold;
            color: #f2d27a;
        }

        .label {
            color: #aaa397;
            font-size: 14px;
        }

        .bad {
            color: #ff8c8c;
            font-weight: bold;
            margin-top: 20px;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 22px;
            font-size: 14px;
        }

        th,
        td {
            padding: 10px;
            border-bottom: 1px solid #312b20;
            text-align: left;
            vertical-align: top;
        }

        th {
            background: #211d16;
            color: #fff2ca;
        }

        tr:hover {
            background: #191714;
        }

        .ok {
            color: #7dffb0;
            font-weight: bold;
        }

        .no {
            color: #ff8c8c;
            font-weight: bold;
        }

        .small {
            color: #a9a092;
            font-size: 13px;
        }

        @media(max-width: 900px) {
            .grid,
            .checks,
            .form-grid {
                grid-template-columns: 1fr;
            }

            .banner {
                display: block;
            }

            .domain {
                margin-top: 12px;
            }
        }
    </style>
</head>

<body>
<div class="wrap">
    <div class="card">
        <div class="banner">
            <div>
                <h1>Firma de calificaciones</h1>
                <div class="sub">
                    Sube el Excel del grupo. El sistema busca nombres o matrículas,
                    cuenta cuántas veces pasaron lista y genera el PDF para firma.
                </div>
            </div>
            <div class="domain">almxlvx.com</div>
        </div>

        <form method="post" enctype="multipart/form-data">
            <label>Información del curso</label>
            <input type="text" name="curso" value="{{ curso_default }}">

            <div class="form-grid">
                <div>
                    <label>Profesor</label>
                    <input type="text" name="profesor" value="{{ profesor_default }}">
                </div>

                <div>
                    <label>NRC</label>
                    <input type="text" name="nrc" value="{{ nrc_default }}">
                </div>
            </div>

            <label>Adscripción</label>
            <input type="text" name="adscripcion" value="{{ adscripcion_default }}">

            <label>Excel con alumnos</label>
            <input type="file" name="archivo" accept=".xlsx,.xls" required>

            <label>Logo opcional para el PDF</label>
            <input type="file" name="logo" accept=".png,.jpg,.jpeg">

            <div class="checks">
                <div class="check">
                    <input type="checkbox" name="imprimir_asistencias" value="1" checked>
                    Imprimir número de asistencias en la tabla del PDF
                </div>

                <div class="check">
                    <input type="checkbox" name="mostrar_dominio" value="1" checked>
                    Mostrar almxlvx.com en el banner del PDF
                </div>

                <div class="check">
                    <input type="checkbox" name="mostrar_logo" value="1" checked>
                    Mostrar logo en el banner del PDF
                </div>

                <div class="check">
                    <input type="checkbox" name="mostrar_contenido_excel" value="1" checked>
                    Colocar el contenido del Excel en el PDF
                </div>

                <div class="check">
                    <input type="checkbox" name="mostrar_encontrados" value="1" checked>
                    Mostrar número de encontrados en el resumen del PDF
                </div>

                <div class="check">
                    <input type="checkbox" name="mostrar_asistencias_totales" value="1" checked>
                    Mostrar asistencias totales en el resumen del PDF
                </div>
            </div>

            <button type="submit">Generar concentrado y PDF</button>
        </form>

        {% if error %}
            <p class="bad">{{ error }}</p>
        {% endif %}

        {% if resumen %}
            <div class="grid">
                <div class="stat">
                    <div class="num">{{ resumen.total_excel }}</div>
                    <div class="label">Alumnos en Excel</div>
                </div>

                <div class="stat">
                    <div class="num">{{ resumen.total_neo4j }}</div>
                    <div class="label">Registros encontrados</div>
                </div>

                <div class="stat">
                    <div class="num">{{ resumen.encontrados }}</div>
                    <div class="label">Alumnos encontrados</div>
                </div>

                <div class="stat">
                    <div class="num">{{ resumen.total_asistencias }}</div>
                    <div class="label">Total de pases de lista</div>
                </div>
            </div>

            <a class="btn" href="/descargar/{{ pdf_nombre }}">Descargar PDF</a>
            <a class="btn" href="/descargar/{{ excel_nombre }}">Descargar Excel</a>

            <h2>Concentrado</h2>

            <table>
                <thead>
                    <tr>
                        <th>No.</th>
                        <th>Matrícula</th>
                        <th>Nombre</th>
                        <th>Asistencias</th>
                        <th>Estado</th>
                        <th>Coincidencia</th>
                        <th>Mejor nombre encontrado</th>
                    </tr>
                </thead>

                <tbody>
                {% for r in concentrado %}
                    <tr>
                        <td>{{ loop.index }}</td>
                        <td>{{ r.matricula_excel }}</td>
                        <td>{{ r.nombre_excel }}</td>
                        <td>{{ r.asistencias }}</td>

                        {% if r.estado == "ENCONTRADO" %}
                            <td class="ok">{{ r.estado }}</td>
                        {% else %}
                            <td class="no">{{ r.estado }}</td>
                        {% endif %}

                        <td>{{ r.metodo }}</td>
                        <td>{{ r.mejor_nombre_neo4j }}</td>
                    </tr>
                {% endfor %}
                </tbody>
            </table>
        {% endif %}
    </div>
</div>
</body>
</html>
"""


def render_page(**kwargs):
    defaults = {
        "curso_default": "Introducción a los Sistemas Programables - ICSA 004 001",
        "nrc_default": "46081",
        "profesor_default": "Dr. Carlos Leopoldo Carreón Díaz de León",
        "adscripcion_default": "FCC BUAP"
    }

    defaults.update(kwargs)

    return render_template_string(HTML, **defaults)


def quitar_acentos(texto):
    texto = str(texto)
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return texto


def normalizar_nombre(nombre):
    if pd.isna(nombre):
        return ""

    nombre = quitar_acentos(nombre)
    nombre = nombre.upper()
    nombre = re.sub(r"[^A-ZÑ ]", " ", nombre)
    nombre = re.sub(r"\s+", " ", nombre).strip()

    partes = nombre.split()
    partes = [p for p in partes if len(p) > 1]

    return " ".join(partes)


def normalizar_nombre_tokens(nombre):
    nombre = normalizar_nombre(nombre)
    tokens = nombre.split()
    tokens = sorted(set(tokens))
    return " ".join(tokens)


def normalizar_matricula(valor):
    if pd.isna(valor):
        return ""

    texto = str(valor).strip()

    if texto.endswith(".0"):
        texto = texto[:-2]

    texto = re.sub(r"\D", "", texto)

    return texto


def similitud(a, b):
    if not a or not b:
        return 0.0

    directa = difflib.SequenceMatcher(None, a, b).ratio()

    ta = " ".join(sorted(set(a.split())))
    tb = " ".join(sorted(set(b.split())))

    por_tokens = difflib.SequenceMatcher(None, ta, tb).ratio()

    return max(directa, por_tokens)


def detectar_columnas_excel(df):
    mejor_nombre = None
    mejor_matricula = None
    mejor_score_nombre = -1
    mejor_score_matricula = -1

    for col in df.columns:
        serie = df[col].dropna().astype(str).head(140)

        score_nombre = 0
        score_matricula = 0

        col_norm = normalizar_nombre(col)

        if "NOMBRE" in col_norm or "ALUMNO" in col_norm or "ESTUDIANTE" in col_norm:
            score_nombre += 100

        if "MATRICULA" in col_norm or "CONTROL" in col_norm or "ID" == col_norm:
            score_matricula += 100

        for valor in serie:
            nombre = normalizar_nombre(valor)
            matricula = normalizar_matricula(valor)

            if len(nombre.split()) >= 2 and not nombre.isdigit():
                score_nombre += 1

            if len(matricula) >= 5:
                score_matricula += 1

        if score_nombre > mejor_score_nombre:
            mejor_score_nombre = score_nombre
            mejor_nombre = col

        if score_matricula > mejor_score_matricula:
            mejor_score_matricula = score_matricula
            mejor_matricula = col

    if mejor_nombre is None or mejor_matricula is None:
        raise ValueError("No pude detectar las columnas de nombre y matrícula en el Excel.")

    return mejor_nombre, mejor_matricula


def leer_excel(ruta):
    df_raw = pd.read_excel(ruta, header=None, dtype=str)

    fila_header = None

    for i in range(min(15, len(df_raw))):
        fila = " ".join(df_raw.iloc[i].dropna().astype(str).tolist()).upper()

        if "NOMBRE" in fila or "MATRICULA" in fila or "MATRÍCULA" in fila or "CONTROL" in fila:
            fila_header = i
            break

    if fila_header is not None:
        df = pd.read_excel(ruta, header=fila_header, dtype=str)
    else:
        df = pd.read_excel(ruta, dtype=str)

    df = df.dropna(how="all").copy()

    col_nombre, col_matricula = detectar_columnas_excel(df)

    limpio = pd.DataFrame()
    limpio["nombre_excel"] = df[col_nombre].astype(str).fillna("")
    limpio["matricula_excel_original"] = df[col_matricula].astype(str).fillna("")
    limpio["matricula_excel"] = limpio["matricula_excel_original"].apply(normalizar_matricula)
    limpio["nombre_norm"] = limpio["nombre_excel"].apply(normalizar_nombre)
    limpio["nombre_tokens"] = limpio["nombre_excel"].apply(normalizar_nombre_tokens)

    limpio = limpio[
        (limpio["nombre_norm"] != "") |
        (limpio["matricula_excel"] != "")
    ].copy()

    limpio = limpio.drop_duplicates(
        subset=["nombre_norm", "matricula_excel"],
        keep="first"
    )

    return limpio


def obtener_registros_neo4j():
    query = """
    MATCH (t:Token)
    WHERE t.nombre IS NOT NULL OR t.matricula IS NOT NULL
    RETURN
        t.token AS token,
        t.nombre AS nombre,
        t.matricula AS matricula,
        t.date AS fecha,
        t.used AS used,
        t.ip AS ip,
        t.cookie AS cookie
    ORDER BY t.date DESC
    """

    registros = []

    with driver.session() as session:
        result = session.run(query)

        for row in result:
            nombre = row.get("nombre") or ""
            matricula = row.get("matricula") or ""

            registros.append({
                "token": row.get("token") or "",
                "nombre_neo4j": nombre,
                "matricula_neo4j": matricula,
                "fecha_neo4j": row.get("fecha") or "",
                "used": row.get("used"),
                "ip": row.get("ip") or "",
                "cookie": row.get("cookie") or "",
                "nombre_norm": normalizar_nombre(nombre),
                "nombre_tokens": normalizar_nombre_tokens(nombre),
                "matricula_norm": normalizar_matricula(matricula)
            })

    return registros


def contar_por_matricula(matricula_excel, registros_neo4j):
    if not matricula_excel:
        return []

    encontrados = []

    for r in registros_neo4j:
        if r["matricula_norm"] and r["matricula_norm"] == matricula_excel:
            encontrados.append(r)

    return encontrados


def contar_por_nombre(nombre_norm, nombre_tokens, registros_neo4j):
    coincidencias = []
    mejor = None
    mejor_score = 0.0

    for r in registros_neo4j:
        score_1 = similitud(nombre_norm, r["nombre_norm"])
        score_2 = similitud(nombre_tokens, r["nombre_tokens"])
        score = max(score_1, score_2)

        if score > mejor_score:
            mejor_score = score
            mejor = r

        if score >= FUZZY_LIMIT:
            item = dict(r)
            item["score"] = score
            coincidencias.append(item)

    return coincidencias, mejor, mejor_score


def generar_concentrado(df_excel, registros_neo4j):
    concentrado = []

    for _, row in df_excel.iterrows():
        nombre_excel = row["nombre_excel"]
        matricula_excel = row["matricula_excel"]
        nombre_norm = row["nombre_norm"]
        nombre_tokens = row["nombre_tokens"]

        coincidencias = contar_por_matricula(matricula_excel, registros_neo4j)
        metodo = ""
        mejor_nombre = ""
        mejor_score = 0.0

        if coincidencias:
            metodo = "MATRICULA"
            mejor_nombre = coincidencias[0]["nombre_neo4j"]
            mejor_score = similitud(nombre_norm, coincidencias[0]["nombre_norm"])
        else:
            coincidencias, mejor, mejor_score = contar_por_nombre(
                nombre_norm,
                nombre_tokens,
                registros_neo4j
            )

            if coincidencias:
                metodo = "NOMBRE PARECIDO"
                mejor_nombre = coincidencias[0]["nombre_neo4j"]
            elif mejor is not None:
                mejor_nombre = mejor["nombre_neo4j"]

        asistencias = len(coincidencias)

        if asistencias > 0:
            estado = "ENCONTRADO"
        else:
            estado = "NO ENCONTRADO"

        fechas = []
        ips = []
        tokens = []
        cookies = []

        for c in coincidencias:
            if c.get("fecha_neo4j"):
                fechas.append(str(c.get("fecha_neo4j")))

            if c.get("ip"):
                ips.append(str(c.get("ip")))

            if c.get("token"):
                tokens.append(str(c.get("token")))

            if c.get("cookie"):
                cookies.append(str(c.get("cookie")))

        concentrado.append({
            "matricula_excel": matricula_excel,
            "nombre_excel": nombre_excel,
            "asistencias": asistencias,
            "estado": estado,
            "metodo": metodo,
            "mejor_nombre_neo4j": mejor_nombre,
            "similitud": round(mejor_score, 3),
            "fechas_neo4j": " | ".join(fechas),
            "ips_neo4j": " | ".join(ips),
            "tokens_neo4j": " | ".join(tokens),
            "cookies_neo4j": " | ".join(cookies)
        })

    concentrado = sorted(
        concentrado,
        key=lambda x: (
            str(x["nombre_excel"]).upper(),
            str(x["matricula_excel"])
        )
    )

    return concentrado


def cortar_texto_canvas(c, texto, max_width, font_name, font_size):
    texto = str(texto)

    if stringWidth(texto, font_name, font_size) <= max_width:
        return texto

    puntos = "..."

    while texto and stringWidth(texto + puntos, font_name, font_size) > max_width:
        texto = texto[:-1]

    return texto + puntos


def dibujar_banner_pdf(canvas_obj, doc, curso, nrc, profesor, adscripcion, mostrar_dominio, mostrar_logo, logo_path):
    width, height = letter

    canvas_obj.saveState()

    canvas_obj.setFillColor(colors.HexColor("#050505"))
    canvas_obj.rect(0, height - 3.35 * cm, width, 3.35 * cm, fill=1, stroke=0)

    canvas_obj.setFillColor(colors.HexColor("#19150e"))
    canvas_obj.rect(0, height - 3.35 * cm, width, 0.12 * cm, fill=1, stroke=0)

    canvas_obj.setFillColor(colors.HexColor("#d0a84f"))
    canvas_obj.rect(0, height - 0.12 * cm, width, 0.12 * cm, fill=1, stroke=0)

    logo_x = 0.85 * cm
    logo_y = height - 2.45 * cm

    if mostrar_logo and logo_path and os.path.exists(logo_path):
        try:
            canvas_obj.drawImage(
                logo_path,
                logo_x,
                logo_y,
                width=1.2 * cm,
                height=1.2 * cm,
                preserveAspectRatio=True,
                mask="auto"
            )
        except Exception:
            canvas_obj.setFillColor(colors.HexColor("#d0a84f"))
            canvas_obj.circle(1.45 * cm, height - 1.85 * cm, 0.42 * cm, fill=1, stroke=0)
    elif mostrar_logo:
        canvas_obj.setFillColor(colors.HexColor("#d0a84f"))
        canvas_obj.circle(1.45 * cm, height - 1.85 * cm, 0.42 * cm, fill=1, stroke=0)

    text_x = 2.4 * cm

    canvas_obj.setFillColor(colors.HexColor("#fff2cd"))
    canvas_obj.setFont("Helvetica-Bold", 20)
    canvas_obj.drawString(text_x, height - 1.08 * cm, "Firma de calificaciones")

    canvas_obj.setFillColor(colors.HexColor("#d9c18b"))
    canvas_obj.setFont("Helvetica-Bold", 8.5)
    curso_linea = "{} | NRC: {}".format(curso, nrc)
    curso_linea = cortar_texto_canvas(canvas_obj, curso_linea, 13.8 * cm, "Helvetica-Bold", 8.5)
    canvas_obj.drawString(text_x, height - 1.62 * cm, curso_linea)

    canvas_obj.setFillColor(colors.HexColor("#c6bda8"))
    canvas_obj.setFont("Helvetica", 8.2)
    profesor_linea = "{} | {}".format(profesor, adscripcion)
    profesor_linea = cortar_texto_canvas(canvas_obj, profesor_linea, 13.8 * cm, "Helvetica", 8.2)
    canvas_obj.drawString(text_x, height - 2.08 * cm, profesor_linea)

    canvas_obj.setFillColor(colors.HexColor("#9f9685"))
    canvas_obj.setFont("Helvetica", 7.8)
    canvas_obj.drawString(text_x, height - 2.52 * cm, "Concentrado para firma de calificaciones")

    if mostrar_dominio:
        canvas_obj.setFillColor(colors.HexColor("#d7bb72"))
        canvas_obj.setFont("Helvetica-Bold", 10)
        canvas_obj.drawRightString(width - 1.25 * cm, height - 1.48 * cm, DOMAIN_NAME)

    canvas_obj.setFillColor(colors.HexColor("#6f654f"))
    canvas_obj.setFont("Helvetica", 8)
    canvas_obj.drawRightString(width - 1.25 * cm, 0.85 * cm, "Página {}".format(doc.page))

    canvas_obj.restoreState()


def generar_pdf(
    concentrado,
    ruta_pdf,
    curso,
    nrc,
    profesor,
    adscripcion,
    imprimir_asistencias=True,
    mostrar_dominio=True,
    mostrar_logo=True,
    logo_path=None,
    mostrar_contenido_excel=True,
    mostrar_encontrados=True,
    mostrar_asistencias_totales=True
):
    doc = SimpleDocTemplate(
        ruta_pdf,
        pagesize=letter,
        rightMargin=0.9 * cm,
        leftMargin=0.9 * cm,
        topMargin=3.95 * cm,
        bottomMargin=1.45 * cm
    )

    styles = getSampleStyleSheet()

    titulo_style = ParagraphStyle(
        "TituloDocumento",
        parent=styles["Title"],
        textColor=colors.HexColor("#181818"),
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=17,
        spaceAfter=8
    )

    normal_style = ParagraphStyle(
        "NormalDocumento",
        parent=styles["Normal"],
        textColor=colors.HexColor("#2b2b2b"),
        fontName="Helvetica",
        fontSize=8.8,
        leading=11
    )

    small_style = ParagraphStyle(
        "SmallDocumento",
        parent=styles["Normal"],
        textColor=colors.HexColor("#333333"),
        fontName="Helvetica",
        fontSize=6.8,
        leading=8.0
    )

    story = []

    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")

    total_excel = len(concentrado)
    total_encontrados = len([x for x in concentrado if x["asistencias"] > 0])
    total_no_encontrados = len([x for x in concentrado if x["asistencias"] == 0])
    total_asistencias = sum([x["asistencias"] for x in concentrado])

    story.append(Paragraph("Concentrado para firma", titulo_style))
    story.append(Paragraph("Fecha de generación: {}".format(fecha), normal_style))
    story.append(Spacer(1, 0.18 * cm))

    resumen_header = []
    resumen_values = []

    resumen_header.append("Alumnos del Excel")
    resumen_values.append(str(total_excel))

    if mostrar_encontrados:
        resumen_header.append("Encontrados")
        resumen_values.append(str(total_encontrados))

    resumen_header.append("No encontrados")
    resumen_values.append(str(total_no_encontrados))

    if mostrar_asistencias_totales:
        resumen_header.append("Asistencias totales")
        resumen_values.append(str(total_asistencias))

    ancho_resumen = 18.9 * cm / len(resumen_header)

    resumen_table = Table(
        [resumen_header, resumen_values],
        colWidths=[ancho_resumen for _ in resumen_header]
    )

    resumen_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#151515")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#f3dfad")),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#f8f4ea")),
        ("TEXTCOLOR", (0, 1), (-1, 1), colors.HexColor("#111111")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b7aa8a")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7)
    ]))

    story.append(resumen_table)
    story.append(Spacer(1, 0.28 * cm))

    if mostrar_contenido_excel:
        if imprimir_asistencias:
            encabezado = ["No.", "Matrícula", "Nombre", "Asist.", "Calificación", "Firma"]
            col_widths = [
                0.75 * cm,
                2.25 * cm,
                6.2 * cm,
                1.15 * cm,
                2.3 * cm,
                6.25 * cm
            ]
        else:
            encabezado = ["No.", "Matrícula", "Nombre", "Calificación", "Firma"]
            col_widths = [
                0.75 * cm,
                2.35 * cm,
                7.25 * cm,
                2.4 * cm,
                6.15 * cm
            ]

        data = [encabezado]

        for i, r in enumerate(concentrado, start=1):
            nombre = Paragraph(str(r["nombre_excel"]), small_style)
            matricula = str(r["matricula_excel"])

            if imprimir_asistencias:
                data.append([
                    str(i),
                    matricula,
                    nombre,
                    str(r["asistencias"]),
                    "",
                    ""
                ])
            else:
                data.append([
                    str(i),
                    matricula,
                    nombre,
                    "",
                    ""
                ])

        table = Table(data, colWidths=col_widths, repeatRows=1)

        table_style = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111111")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#f3dfad")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 7.0),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("ALIGN", (0, 1), (1, -1), "CENTER"),
            ("ALIGN", (3, 1), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#b8ad96")),
            ("FONTSIZE", (0, 1), (-1, -1), 6.8),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("BACKGROUND", (0, 1), (-1, -1), colors.white)
        ]

        for row_index in range(1, len(data)):
            if row_index % 2 == 0:
                table_style.append(
                    ("BACKGROUND", (0, row_index), (-1, row_index), colors.HexColor("#faf7ef"))
                )

        table.setStyle(TableStyle(table_style))
        story.append(table)
    else:
        story.append(Paragraph(
            "La tabla del contenido del Excel fue omitida por configuración.",
            normal_style
        ))

    def first_page(canvas_obj, doc_obj):
        dibujar_banner_pdf(
            canvas_obj,
            doc_obj,
            curso,
            nrc,
            profesor,
            adscripcion,
            mostrar_dominio,
            mostrar_logo,
            logo_path
        )

    def later_pages(canvas_obj, doc_obj):
        dibujar_banner_pdf(
            canvas_obj,
            doc_obj,
            curso,
            nrc,
            profesor,
            adscripcion,
            mostrar_dominio,
            mostrar_logo,
            logo_path
        )

    doc.build(story, onFirstPage=first_page, onLaterPages=later_pages)


def guardar_excel(concentrado, ruta_excel):
    df = pd.DataFrame(concentrado)
    df.to_excel(ruta_excel, index=False, sheet_name="concentrado")


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return render_page()

    if "archivo" not in request.files:
        return render_page(error="No se recibió ningún Excel.")

    archivo = request.files["archivo"]

    if archivo.filename == "":
        return render_page(error="No seleccionaste ningún Excel.")

    curso = request.form.get("curso", "").strip()
    nrc = request.form.get("nrc", "").strip()
    profesor = request.form.get("profesor", "").strip()
    adscripcion = request.form.get("adscripcion", "").strip()

    if not curso:
        curso = "Introducción a los Sistemas Programables - ICSA 004 001"

    if not nrc:
        nrc = "46081"

    if not profesor:
        profesor = "Dr. Carlos Leopoldo Carreón Díaz de León"

    if not adscripcion:
        adscripcion = "FCC BUAP"

    imprimir_asistencias = request.form.get("imprimir_asistencias") == "1"
    mostrar_dominio = request.form.get("mostrar_dominio") == "1"
    mostrar_logo = request.form.get("mostrar_logo") == "1"
    mostrar_contenido_excel = request.form.get("mostrar_contenido_excel") == "1"
    mostrar_encontrados = request.form.get("mostrar_encontrados") == "1"
    mostrar_asistencias_totales = request.form.get("mostrar_asistencias_totales") == "1"

    filename = secure_filename(archivo.filename)
    unique_name = "{}_{}".format(uuid.uuid4().hex[:10], filename)
    ruta_excel_subido = os.path.join(UPLOAD_DIR, unique_name)
    archivo.save(ruta_excel_subido)

    logo_path = None

    if "logo" in request.files:
        logo = request.files["logo"]

        if logo and logo.filename:
            logo_name = secure_filename(logo.filename)
            logo_unique = "{}_{}".format(uuid.uuid4().hex[:10], logo_name)
            logo_path = os.path.join(LOGO_DIR, logo_unique)
            logo.save(logo_path)

    try:
        df_excel = leer_excel(ruta_excel_subido)
        registros_neo4j = obtener_registros_neo4j()

        if len(registros_neo4j) == 0:
            return render_page(
                error="La base respondió, pero no encontré registros con nombre o matrícula.",
                curso_default=curso,
                nrc_default=nrc,
                profesor_default=profesor,
                adscripcion_default=adscripcion
            )

        concentrado = generar_concentrado(df_excel, registros_neo4j)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        pdf_nombre = "firma_calificaciones_{}.pdf".format(timestamp)
        excel_nombre = "concentrado_asistencia_{}.xlsx".format(timestamp)

        ruta_pdf = os.path.join(RESULT_DIR, pdf_nombre)
        ruta_excel_resultado = os.path.join(RESULT_DIR, excel_nombre)

        generar_pdf(
            concentrado,
            ruta_pdf,
            curso=curso,
            nrc=nrc,
            profesor=profesor,
            adscripcion=adscripcion,
            imprimir_asistencias=imprimir_asistencias,
            mostrar_dominio=mostrar_dominio,
            mostrar_logo=mostrar_logo,
            logo_path=logo_path,
            mostrar_contenido_excel=mostrar_contenido_excel,
            mostrar_encontrados=mostrar_encontrados,
            mostrar_asistencias_totales=mostrar_asistencias_totales
        )

        guardar_excel(concentrado, ruta_excel_resultado)

        resumen = {
            "total_excel": len(df_excel),
            "total_neo4j": len(registros_neo4j),
            "encontrados": len([x for x in concentrado if x["asistencias"] > 0]),
            "total_asistencias": sum([x["asistencias"] for x in concentrado])
        }

        return render_page(
            resumen=resumen,
            concentrado=concentrado,
            pdf_nombre=pdf_nombre,
            excel_nombre=excel_nombre,
            curso_default=curso,
            nrc_default=nrc,
            profesor_default=profesor,
            adscripcion_default=adscripcion
        )

    except Exception as e:
        return render_page(
            error="Error al procesar: {}".format(str(e)),
            curso_default=curso,
            nrc_default=nrc,
            profesor_default=profesor,
            adscripcion_default=adscripcion
        )


@app.route("/descargar/<nombre>")
def descargar(nombre):
    nombre = secure_filename(nombre)
    ruta = os.path.join(RESULT_DIR, nombre)

    if not os.path.exists(ruta):
        return "Archivo no encontrado", 404

    return send_file(ruta, as_attachment=True)


@app.route("/salud")
def salud():
    try:
        with driver.session() as session:
            session.run("RETURN 1 AS ok").single()

        return {
            "status": "ok",
            "base": "conectada"
        }

    except Exception as e:
        return {
            "status": "error",
            "base": str(e)
        }, 500


if __name__ == "__main__":
    app.run(host=S_IP, port=S_PORT, debug=False)
