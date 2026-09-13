import os
import re
import io
import hmac
import uuid
import qrcode
import hashlib
import secrets
import unicodedata
from datetime import datetime
from functools import wraps

from dotenv import load_dotenv
from flask import (
    Flask,
    request,
    session,
    redirect,
    url_for,
    send_file,
    render_template_string,
    abort
)
from werkzeug.security import check_password_hash
from neo4j import GraphDatabase

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image
)
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth


load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "")
NEO4J_USER = os.getenv("NEO4J_USER", "")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(48))
SERVER_SIGNING_SECRET = os.getenv("SERVER_SIGNING_SECRET", "")
USER_SIGNING_SECRET = os.getenv("USER_SIGNING_SECRET", "")

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", "")
ADMIN_LOGIN_PATH = os.getenv("ADMIN_LOGIN_PATH", "/admin-firma-oculta")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:45001").rstrip("/")

LOGO_PATH = os.getenv("LOGO_PATH", "static/logo.png")

S_IP = "0.0.0.0"
S_PORT = 45001

DATA_DIR = "data_firmas"
PDF_DIR = os.path.join(DATA_DIR, "certificados")
QR_DIR = os.path.join(DATA_DIR, "qr")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(PDF_DIR, exist_ok=True)
os.makedirs(QR_DIR, exist_ok=True)
os.makedirs("static", exist_ok=True)

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

driver = GraphDatabase.driver(
    NEO4J_URI,
    auth=(NEO4J_USER, NEO4J_PASSWORD)
)


BASE_CSS = """
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
        max-width: 980px;
        margin: 42px auto;
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
        background: #000;
        border: 1px solid #fff0;
        border-radius: 16px;
        padding: 26px;
        margin-bottom: 26px;
    }

    h1 {
        margin: 0;
        color: #fff;
        font-size: 34px;
        letter-spacing: -.5px;
    }

    h2 {
        color: #fff1c8;
        margin-top: 28px;
    }

    .sub {
        color: #fff;
        margin-top: 10px;
        line-height: 1.5;
    }

    label {
        display: block;
        margin-top: 17px;
        color: #efe6d0;
        font-weight: bold;
    }

    input[type=text],
    input[type=password],
    input[type=number] {
        width: 100%;
        margin-top: 8px;
        padding: 14px;
        border-radius: 12px;
        border: 1px solid #4a40;
        background: #0c0c0c;
        color: #fff;
        font-size: 15px;
    }

    .check {
        margin-top: 18px;
        background: #0c0c0c;
        border: 1px solid #302a1e;
        border-radius: 12px;
        padding: 14px;
        color: #d9d0be;
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
        background: #fff;
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

    .bad {
        color: #ff8c8c;
        font-weight: bold;
        margin-top: 18px;
    }

    .ok {
        color: #88ffb5;
        font-weight: bold;
        margin-top: 18px;
    }

    .muted {
        color: #a9a092;
        font-size: 14px;
    }

    table {
        width: 100%;
        border-collapse: collapse;
        margin-top: 20px;
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

    code {
        color: #f2d27a;
        word-break: break-all;
    }
</style>
"""


INDEX_HTML = """
<!doctype html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <title>Firma de calificaciones</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    """ + BASE_CSS + """
</head>
<body>
<div class="wrap">
        <div class="banner">
            <h1>Firma digital de calificación</h1>
            <div class="sub">
                Instrucciones: Ingresa tu nombre completo empezando por nombre y luego apellidos, y la matrícula para generar un certificado de conformidad.
            </div>
        </div>

        {% if error %}
            <p class="bad">{{ error }}</p>
        {% endif %}

        <form method="post" action="/registrar">
            <input type="hidden" name="csrf_token" value="{{ csrf_token }}">

            <label>Nombre completo</label>
            <input type="text" name="nombre" required maxlength="160" autocomplete="name">

            <label>Matrícula</label>
            <input type="text" name="matricula" required maxlength="40" autocomplete="off">

            <button type="submit">Continuar</button>
        </form>
</div>
</body>
</html>
"""


DECLARACION_HTML = """
<!doctype html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <title>Declaratoria de conformidad</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    """ + BASE_CSS + """
</head>
<body>
<div class="wrap">
    <div class="card">
        <div class="banner">
            <h1>Declaratoria de conformidad</h1>
            <div class="sub">
                Ingresa la calificación con la que manifiestas tu conformidad.
            </div>
        </div>

        <p><b>Estudiante:</b> {{ nombre }}</p>
        <p><b>Matrícula:</b> {{ matricula }}</p>

        {% if error %}
            <p class="bad">{{ error }}</p>
        {% endif %}

        <form method="post" action="/firmar">
            <input type="hidden" name="csrf_token" value="{{ csrf_token }}">

            <label>Calificación</label>
            <input type="text" name="calificacion" required maxlength="20" autocomplete="off">

            <div class="check">
                <input type="checkbox" name="acepto" value="1" required>
                Declaro voluntariamente que estoy conforme con la calificación capturada.
            </div>

            <button type="submit">Firmar declaratoria</button>
        </form>
    </div>
</div>
</body>
</html>
"""


RESULTADO_HTML = """
<!doctype html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <title>Certificado generado</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    """ + BASE_CSS + """
</head>
<body>
<div class="wrap">
    <div class="card">
        <div class="banner">
            <h1>Certificado generado</h1>
            <div class="sub">
                La declaratoria fue firmada correctamente.
            </div>
        </div>

        <p class="ok">Firma registrada.</p>

        <p><b>Folio:</b> <code>{{ folio }}</code></p>
        <p><b>Firma del estudiante:</b> <code>{{ firma_usuario }}</code></p>
        <p><b>Firma del servidor:</b> <code>{{ firma_servidor }}</code></p>

        <a class="btn" href="/certificado/{{ folio }}">Descargar certificado PDF</a>
        <a class="btn" href="/validar/{{ folio }}">Validar certificado</a>
    </div>
</div>
</body>
</html>
"""


VALIDAR_HTML = """
<!doctype html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <title>Validación de certificado</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    """ + BASE_CSS + """
</head>
<body>
<div class="wrap">
    <div class="card">
        <div class="banner">
            <h1>Validación de certificado</h1>
            <div class="sub">
                Resultado de verificación criptográfica del certificado.
            </div>
        </div>

        {% if valido %}
            <p class="ok">Certificado válido. Las firmas coinciden.</p>
        {% else %}
            <p class="bad">Certificado inválido o alterado.</p>
        {% endif %}

        {% if registro %}
            <p><b>Folio:</b> <code>{{ registro.folio }}</code></p>
            <p><b>Estudiante:</b> {{ registro.nombre }}</p>
            <p><b>Matrícula:</b> {{ registro.matricula }}</p>
            <p><b>Calificación:</b> {{ registro.calificacion }}</p>
            <p><b>Fecha:</b> {{ registro.fecha_legible }}</p>
            <p><b>Firma del estudiante:</b> <code>{{ registro.firma_usuario }}</code></p>
            <p><b>Firma del servidor:</b> <code>{{ registro.firma_servidor }}</code></p>
        {% endif %}
    </div>
</div>
</body>
</html>
"""


ADMIN_LOGIN_HTML = """
<!doctype html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <title>Administración</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    """ + BASE_CSS + """
</head>
<body>
<div class="wrap">
    <div class="card">
        <div class="banner">
            <h1>Acceso administrativo</h1>
            <div class="sub">Panel privado de revisión de firmas.</div>
        </div>

        {% if error %}
            <p class="bad">{{ error }}</p>
        {% endif %}

        <form method="post">
            <input type="hidden" name="csrf_token" value="{{ csrf_token }}">

            <label>Usuario</label>
            <input type="text" name="usuario" required autocomplete="username">

            <label>Contraseña</label>
            <input type="password" name="password" required autocomplete="current-password">

            <button type="submit">Entrar</button>
        </form>
    </div>
</div>
</body>
</html>
"""


ADMIN_PANEL_HTML = """
<!doctype html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <title>Panel de firmas</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    """ + BASE_CSS + """
</head>
<body>
<div class="wrap">
    <div class="card">
        <div class="banner">
            <h1>Panel de firmas</h1>
            <div class="sub">
                Resumen de estudiantes que han firmado su conformidad.
            </div>
        </div>

        <p><b>Total de firmas:</b> {{ total }}</p>
        <a class="btn" href="/admin/logout">Cerrar sesión</a>

        <table>
            <thead>
                <tr>
                    <th>No.</th>
                    <th>Fecha</th>
                    <th>Nombre</th>
                    <th>Matrícula</th>
                    <th>Calificación</th>
                    <th>Folio</th>
                    <th>PDF</th>
                </tr>
            </thead>
            <tbody>
            {% for r in registros %}
                <tr>
                    <td>{{ loop.index }}</td>
                    <td>{{ r.fecha_legible }}</td>
                    <td>{{ r.nombre }}</td>
                    <td>{{ r.matricula }}</td>
                    <td>{{ r.calificacion }}</td>
                    <td><code>{{ r.folio }}</code></td>
                    <td><a class="btn" href="/certificado/{{ r.folio }}">PDF</a></td>
                </tr>
            {% endfor %}
            </tbody>
        </table>
    </div>
</div>
</body>
</html>
"""


def normalizar_texto(valor):
    valor = str(valor or "").strip()
    valor = unicodedata.normalize("NFD", valor)
    valor = "".join(c for c in valor if unicodedata.category(c) != "Mn")
    valor = re.sub(r"\s+", " ", valor)
    return valor


def normalizar_matricula(valor):
    valor = str(valor or "").strip()
    valor = re.sub(r"[^0-9A-Za-z]", "", valor)
    return valor.upper()


def limpiar_nombre(valor):
    valor = normalizar_texto(valor)
    valor = re.sub(r"[^A-Za-zÁÉÍÓÚáéíóúÑñÜü .'-]", "", valor)
    valor = re.sub(r"\s+", " ", valor).strip()
    return valor


def limpiar_calificacion(valor):
    valor = str(valor or "").strip()
    valor = re.sub(r"[^0-9A-Za-z., -]", "", valor)
    valor = re.sub(r"\s+", " ", valor).strip()
    return valor[:20]


def csrf_token():
    token = secrets.token_urlsafe(32)
    session["csrf_token"] = token
    return token


def validar_csrf():
    enviado = request.form.get("csrf_token", "")
    guardado = session.get("csrf_token", "")
    if not enviado or not guardado or not hmac.compare_digest(enviado, guardado):
        abort(403)


def crear_hmac(secret, mensaje):
    return hmac.new(
        secret.encode("utf-8"),
        mensaje.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()


def hash_certificado(datos):
    texto = "|".join([
        datos["folio"],
        datos["nombre"],
        datos["matricula"],
        datos["calificacion"],
        datos["fecha_iso"],
        datos["firma_usuario"],
        datos["firma_servidor"]
    ])

    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def construir_firmas(folio, nombre, matricula, calificacion, fecha_iso):
    mensaje_usuario = "|".join([
        "FIRMA_USUARIO",
        folio,
        nombre,
        matricula,
        calificacion,
        fecha_iso
    ])

    firma_usuario = crear_hmac(USER_SIGNING_SECRET, mensaje_usuario)

    mensaje_servidor = "|".join([
        "FIRMA_SERVIDOR",
        folio,
        nombre,
        matricula,
        calificacion,
        fecha_iso,
        firma_usuario
    ])

    firma_servidor = crear_hmac(SERVER_SIGNING_SECRET, mensaje_servidor)

    return firma_usuario, firma_servidor


def verificar_firmas(registro):
    firma_usuario_calc, firma_servidor_calc = construir_firmas(
        registro["folio"],
        registro["nombre"],
        registro["matricula"],
        registro["calificacion"],
        registro["fecha_iso"]
    )

    return (
        hmac.compare_digest(firma_usuario_calc, registro["firma_usuario"]) and
        hmac.compare_digest(firma_servidor_calc, registro["firma_servidor"])
    )


def fecha_larga(fecha_iso):
    meses = {
        1: "enero",
        2: "febrero",
        3: "marzo",
        4: "abril",
        5: "mayo",
        6: "junio",
        7: "julio",
        8: "agosto",
        9: "septiembre",
        10: "octubre",
        11: "noviembre",
        12: "diciembre"
    }

    dt = datetime.fromisoformat(fecha_iso)
    return "{} de {} del año {}".format(dt.day, meses[dt.month], dt.year)


def fecha_corta(fecha_iso):
    dt = datetime.fromisoformat(fecha_iso)
    return dt.strftime("%d/%m/%Y %H:%M:%S")


def validar_matricula_en_neo4j(matricula):
    query = """
    MATCH (n)
    WHERE n.matricula IS NOT NULL
      AND toUpper(replace(toString(n.matricula), " ", "")) = $matricula
    RETURN n.matricula AS matricula
    LIMIT 1
    """

    with driver.session() as db:
        row = db.run(query, matricula=matricula).single()

    return row is not None


def guardar_firma_neo4j(datos):
    query = """
    CREATE (f:FirmaCalificacion {
        folio: $folio,
        nombre: $nombre,
        matricula: $matricula,
        calificacion: $calificacion,
        fecha_iso: $fecha_iso,
        fecha_legible: $fecha_legible,
        firma_usuario: $firma_usuario,
        firma_servidor: $firma_servidor,
        hash_certificado: $hash_certificado,
        ip: $ip,
        user_agent: $user_agent
    })
    RETURN f.folio AS folio
    """

    with driver.session() as db:
        db.run(query, **datos).single()


def obtener_firma_por_folio(folio):
    query = """
    MATCH (f:FirmaCalificacion {folio: $folio})
    RETURN
        f.folio AS folio,
        f.nombre AS nombre,
        f.matricula AS matricula,
        f.calificacion AS calificacion,
        f.fecha_iso AS fecha_iso,
        f.fecha_legible AS fecha_legible,
        f.firma_usuario AS firma_usuario,
        f.firma_servidor AS firma_servidor,
        f.hash_certificado AS hash_certificado,
        f.ip AS ip,
        f.user_agent AS user_agent
    LIMIT 1
    """

    with driver.session() as db:
        row = db.run(query, folio=folio).single()

    if row is None:
        return None

    return dict(row)


def listar_firmas():
    query = """
    MATCH (f:FirmaCalificacion)
    RETURN
        f.folio AS folio,
        f.nombre AS nombre,
        f.matricula AS matricula,
        f.calificacion AS calificacion,
        f.fecha_iso AS fecha_iso,
        f.fecha_legible AS fecha_legible,
        f.firma_usuario AS firma_usuario,
        f.firma_servidor AS firma_servidor
    ORDER BY f.fecha_iso DESC
    """

    registros = []

    with driver.session() as db:
        result = db.run(query)

        for row in result:
            registros.append(dict(row))

    return registros


def generar_qr(texto, ruta):
    img = qrcode.make(texto)
    img.save(ruta)


def cortar_texto(c, texto, max_width, font_name, font_size):
    texto = str(texto)

    if stringWidth(texto, font_name, font_size) <= max_width:
        return texto

    puntos = "..."

    while texto and stringWidth(texto + puntos, font_name, font_size) > max_width:
        texto = texto[:-1]

    return texto + puntos


def dibujar_banner(c, doc, mostrar_logo):
    width, height = letter

    c.saveState()

    c.setFillColor(colors.HexColor("#050505"))
    c.rect(0, height - 4.0 * cm, width, 4.0 * cm, fill=1, stroke=0)


    c.setFillColor(colors.HexColor("#1b160f"))
    c.rect(0, height - 4.0 * cm, width, 0.10 * cm, fill=1, stroke=0)

    if mostrar_logo and os.path.exists(LOGO_PATH):
        try:
            c.drawImage(
                LOGO_PATH,
                1.0 * cm,
                height - 3.15 * cm,
                width=2.1 * cm,
                height=2.1 * cm,
                preserveAspectRatio=True,
                mask="auto"
            )
        except Exception:
            c.setFillColor(colors.HexColor("#d0a84f"))
            c.circle(2.0 * cm, height - 2.1 * cm, 0.65 * cm, fill=1, stroke=0)
    elif mostrar_logo:
        c.setFillColor(colors.HexColor("#d0a84f"))
        c.circle(2.0 * cm, height - 2.1 * cm, 0.65 * cm, fill=1, stroke=0)

    text_x = 3.6 * cm if mostrar_logo else 1.25 * cm

    c.setFillColor(colors.HexColor("#ffffff"))
    c.setFont("Helvetica-Bold", 21)
    c.drawString(text_x, height - 1.45 * cm, "Certificado de firma de calificaciones")

    c.setFillColor(colors.HexColor("#d9c18b"))
    c.setFont("Helvetica", 9)
    c.drawString(text_x, height - 2.05 * cm, "Certificado generado por https://calificaciones.almxlvx.com")

    c.setFillColor(colors.HexColor("#6f654f"))
    c.setFont("Helvetica", 8)
    c.drawRightString(width - 1.2 * cm, 0.85 * cm, "Pagina {}".format(doc.page))

    c.restoreState()


def generar_pdf_certificado(datos, mostrar_logo=True):
    folio = datos["folio"]

    pdf_path = os.path.join(PDF_DIR, "{}.pdf".format(folio))
    qr_usuario_path = os.path.join(QR_DIR, "{}_usuario.png".format(folio))
    qr_servidor_path = os.path.join(QR_DIR, "{}_servidor.png".format(folio))

    url_validacion = "{}/validar/{}".format("https://calificaciones.almxlvx.com", folio)

    qr_usuario_texto = "{}?tipo=usuario&firma={}".format(
        url_validacion,
        datos["firma_usuario"]
    )

    qr_servidor_texto = "{}?tipo=servidor&firma={}".format(
        url_validacion,
        datos["firma_servidor"]
    )

    generar_qr(qr_usuario_texto, qr_usuario_path)
    generar_qr(qr_servidor_texto, qr_servidor_path)

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=letter,
        rightMargin=1.35 * cm,
        leftMargin=1.35 * cm,
        topMargin=4.55 * cm,
        bottomMargin=1.5 * cm
    )

    styles = getSampleStyleSheet()

    titulo_style = ParagraphStyle(
        "Titulo",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        textColor=colors.HexColor("#151515"),
        spaceAfter=12
    )

    normal_style = ParagraphStyle(
        "NormalCert",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10.2,
        leading=15,
        textColor=colors.HexColor("#222222"),
        spaceAfter=8
    )

    firma_style = ParagraphStyle(
        "Firma",
        parent=styles["Normal"],
        fontName="Courier",
        fontSize=6.7,
        leading=8.4,
        textColor=colors.HexColor("#222222"),
        wordWrap="CJK"
    )

    story = []

    story.append(Paragraph("Constancia de conformidad", titulo_style))

    texto = """
    Este certificado, expedido el dia <b>{fecha_larga}</b>, muestra que el estudiante
    <b>{nombre}</b>, con matricula <b>{matricula}</b>, esta conforme con su calificacion
    de <b>{calificacion}</b> y ha decidido voluntariamente firmar la presente declaratoria
    mediante una firma digital generada para este acto.
    """.format(
        fecha_larga=fecha_larga(datos["fecha_iso"]),
        nombre=datos["nombre"],
        matricula=datos["matricula"],
        calificacion=datos["calificacion"]
    )

    story.append(Paragraph(texto, normal_style))

    story.append(Spacer(1, 0.15 * cm))

    info = [
        ["Folio", datos["folio"]],
        ["Fecha", datos["fecha_legible"]],
        ["Estudiante", datos["nombre"]],
        ["Matricula", datos["matricula"]],
        ["Calificacion", datos["calificacion"]],
        ["Hash del certificado", datos["hash_certificado"]]
    ]

    table = Table(info, colWidths=[4.0 * cm, 13.2 * cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#151515")),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#f3dfad")),
        ("BACKGROUND", (1, 0), (1, -1), colors.HexColor("#faf7ef")),
        ("TEXTCOLOR", (1, 0), (1, -1), colors.HexColor("#111111")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.2),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#b8ad96")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6)
    ]))
    story.append(table)

    story.append(Spacer(1, 0.45 * cm))

    story.append(Paragraph("<b>Firma digital del estudiante</b>", normal_style))
    story.append(Paragraph(datos["firma_usuario"], firma_style))

    story.append(Spacer(1, 0.2 * cm))

    story.append(Paragraph("<b>Firma digital del servidor</b>", normal_style))
    story.append(Paragraph(datos["firma_servidor"], firma_style))

    story.append(Spacer(1, 0.4 * cm))

    qr_table = Table(
        [
            [
                Image(qr_usuario_path, width=3.1 * cm, height=3.1 * cm),
                Image(qr_servidor_path, width=3.1 * cm, height=3.1 * cm)
            ],
            [
                Paragraph("QR de firma del estudiante", normal_style),
                Paragraph("QR de firma del servidor", normal_style)
            ]
        ],
        colWidths=[8.5 * cm, 8.5 * cm]
    )

    qr_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6)
    ]))

    story.append(qr_table)

    story.append(Spacer(1, 0.25 * cm))

    story.append(Paragraph(
        "La validez de este documento puede comprobarse escaneando los codigos QR o consultando el folio en la ruta de validacion correspondiente.",
        normal_style
    ))

    def first_page(c, d):
        dibujar_banner(c, d, mostrar_logo)

    def later_pages(c, d):
        dibujar_banner(c, d, mostrar_logo)

    doc.build(story, onFirstPage=first_page, onLaterPages=later_pages)

    return pdf_path


def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not session.get("admin_ok"):
            return redirect(ADMIN_LOGIN_PATH)
        return func(*args, **kwargs)
    return wrapper


@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/", methods=["GET"])
def index():
    return render_template_string(
        INDEX_HTML,
        csrf_token=csrf_token()
    )


@app.route("/registrar", methods=["POST"])
def registrar():
    validar_csrf()

    nombre = limpiar_nombre(request.form.get("nombre"))
    matricula = normalizar_matricula(request.form.get("matricula"))

    if len(nombre) < 5:
        return render_template_string(
            INDEX_HTML,
            csrf_token=csrf_token(),
            error="El nombre no es valido."
        )

    if len(matricula) < 4:
        return render_template_string(
            INDEX_HTML,
            csrf_token=csrf_token(),
            error="La matricula no es valida."
        )

    if not validar_matricula_en_neo4j(matricula):
        return render_template_string(
            INDEX_HTML,
            csrf_token=csrf_token(),
            error="La matricula no se encuentra registrada."
        )

    session["firma_nombre"] = nombre
    session["firma_matricula"] = matricula

    return render_template_string(
        DECLARACION_HTML,
        csrf_token=csrf_token(),
        nombre=nombre,
        matricula=matricula
    )


@app.route("/firmar", methods=["POST"])
def firmar():
    validar_csrf()

    nombre = session.get("firma_nombre")
    matricula = session.get("firma_matricula")

    if not nombre or not matricula:
        return redirect(url_for("index"))

    calificacion = limpiar_calificacion(request.form.get("calificacion"))
    acepto = request.form.get("acepto") == "1"
    mostrar_logo = request.form.get("mostrar_logo") == "1"

    if not acepto:
        return render_template_string(
            DECLARACION_HTML,
            csrf_token=csrf_token(),
            nombre=nombre,
            matricula=matricula,
            error="Debes aceptar la declaratoria."
        )

    if not calificacion:
        return render_template_string(
            DECLARACION_HTML,
            csrf_token=csrf_token(),
            nombre=nombre,
            matricula=matricula,
            error="La calificacion no es valida."
        )

    if not validar_matricula_en_neo4j(matricula):
        abort(403)

    folio = uuid.uuid4().hex
    fecha_iso = datetime.now().isoformat(timespec="seconds")
    fecha_legible = fecha_corta(fecha_iso)

    firma_usuario, firma_servidor = construir_firmas(
        folio,
        nombre,
        matricula,
        calificacion,
        fecha_iso
    )

    datos = {
        "folio": folio,
        "nombre": nombre,
        "matricula": matricula,
        "calificacion": calificacion,
        "fecha_iso": fecha_iso,
        "fecha_legible": fecha_legible,
        "firma_usuario": firma_usuario,
        "firma_servidor": firma_servidor,
        "ip": request.remote_addr or "",
        "user_agent": request.headers.get("User-Agent", "")
    }

    datos["hash_certificado"] = hash_certificado(datos)

    guardar_firma_neo4j(datos)
    generar_pdf_certificado(datos, mostrar_logo=mostrar_logo)

    session.pop("firma_nombre", None)
    session.pop("firma_matricula", None)

    return render_template_string(
        RESULTADO_HTML,
        folio=folio,
        firma_usuario=firma_usuario,
        firma_servidor=firma_servidor
    )


@app.route("/certificado/<folio>", methods=["GET"])
def certificado(folio):
    folio = re.sub(r"[^a-fA-F0-9]", "", folio)

    if len(folio) != 32:
        abort(404)

    registro = obtener_firma_por_folio(folio)

    if registro is None:
        abort(404)

    pdf_path = os.path.join(PDF_DIR, "{}.pdf".format(folio))

    if not os.path.exists(pdf_path):
        generar_pdf_certificado(registro, mostrar_logo=True)

    return send_file(
        pdf_path,
        as_attachment=True,
        download_name="certificado_{}.pdf".format(folio)
    )


@app.route("/validar/<folio>", methods=["GET"])
def validar(folio):
    folio = re.sub(r"[^a-fA-F0-9]", "", folio)

    if len(folio) != 32:
        abort(404)

    registro = obtener_firma_por_folio(folio)

    if registro is None:
        return render_template_string(
            VALIDAR_HTML,
            valido=False,
            registro=None
        )

    valido = verificar_firmas(registro)

    firma_qr = request.args.get("firma", "")
    tipo = request.args.get("tipo", "")

    if firma_qr:
        if tipo == "usuario":
            valido = valido and hmac.compare_digest(firma_qr, registro["firma_usuario"])
        elif tipo == "servidor":
            valido = valido and hmac.compare_digest(firma_qr, registro["firma_servidor"])
        else:
            valido = False

    return render_template_string(
        VALIDAR_HTML,
        valido=valido,
        registro=registro
    )


@app.route(ADMIN_LOGIN_PATH, methods=["GET", "POST"])
def admin_login():
    if request.method == "GET":
        return render_template_string(
            ADMIN_LOGIN_HTML,
            csrf_token=csrf_token()
        )

    validar_csrf()

    usuario = request.form.get("usuario", "")
    password = request.form.get("password", "")

    if not ADMIN_PASSWORD_HASH:
        return render_template_string(
            ADMIN_LOGIN_HTML,
            csrf_token=csrf_token(),
            error="ADMIN_PASSWORD_HASH no esta configurado."
        )

    ok_user = hmac.compare_digest(usuario, ADMIN_USER)
    ok_pass = check_password_hash(ADMIN_PASSWORD_HASH, password)

    if not ok_user or not ok_pass:
        return render_template_string(
            ADMIN_LOGIN_HTML,
            csrf_token=csrf_token(),
            error="Credenciales invalidas."
        )

    session["admin_ok"] = True

    return redirect("/admin/panel")


@app.route("/admin/panel", methods=["GET"])
@admin_required
def admin_panel():
    registros = listar_firmas()

    return render_template_string(
        ADMIN_PANEL_HTML,
        registros=registros,
        total=len(registros)
    )


@app.route("/admin/logout", methods=["GET"])
def admin_logout():
    session.pop("admin_ok", None)
    return redirect(ADMIN_LOGIN_PATH)


@app.route("/salud", methods=["GET"])
def salud():
    try:
        with driver.session() as db:
            db.run("RETURN 1 AS ok").single()

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
    if not SERVER_SIGNING_SECRET or not USER_SIGNING_SECRET:
        raise RuntimeError("Faltan SERVER_SIGNING_SECRET o USER_SIGNING_SECRET en .env")

    app.run(host=S_IP, port=S_PORT, debug=True)
