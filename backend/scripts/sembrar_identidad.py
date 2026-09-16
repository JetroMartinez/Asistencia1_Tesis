import argparse
import json
import os
import secrets
import string
import sys
import uuid
from   datetime import datetime
from   pathlib  import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from   dotenv             import load_dotenv
from   neo4j              import GraphDatabase
from   werkzeug.security  import generate_password_hash

import identidad

load_dotenv(BACKEND_DIR / ".env")

NEO4J_URI      = os.getenv("NEO4J_URI")
NEO4J_USER     = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

ALFABETO_CODIGO = string.ascii_uppercase + string.ascii_lowercase + string.digits


def generar_codigo_inicial(longitud: int = 8) -> str:
    return "".join(secrets.choice(ALFABETO_CODIGO) for _ in range(longitud))


def sembrar(cantidad: int) -> list[dict]:
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    codigos = []
    nuevos = 0
    ya_existian = 0
    con_dispositivo = 0

    try:
        with driver.session() as session:
            session.execute_write(identidad.asegurar_esquema_identidad)

            for i in range(1, cantidad + 1):
                matricula = f"SIM{i:04d}"
                nombre    = f"Alumno Sintetico {i:02d}"
                codigo    = generar_codigo_inicial()
                password_hash = generate_password_hash(codigo)

                recien_creado = session.execute_write(
                    identidad.crear_alumno, matricula, nombre, password_hash,
                )
                nuevos += int(recien_creado)
                ya_existian += int(not recien_creado)

                codigos.append({
                    "matricula": matricula,
                    "nombre": nombre,
                    "codigo_inicial": codigo,
                })

                # La mitad de los alumnos sinteticos (indices pares) ya tienen un
                # dispositivo enrolado, para que el conjunto de prueba distinga
                # matriculas con y sin dispositivo activo (ver docs/decisiones.md,
                # filtro del limite de intentos de login por IP).
                if i % 2 == 0:
                    llave_publica_sintetica      = "SINTETICA-" + uuid.uuid4().hex
                    huella_dispositivo_sintetica = "SINTETICA-" + uuid.uuid4().hex
                    session.execute_write(
                        identidad.registrar_dispositivo, matricula,
                        llave_publica_sintetica, huella_dispositivo_sintetica,
                    )
                    con_dispositivo += 1
    finally:
        driver.close()

    print(f"Alumnos sinteticos procesados: {cantidad}")
    print(f"  nuevos: {nuevos}")
    print(f"  ya existian: {ya_existian}")
    print(f"  con dispositivo activo sintetico: {con_dispositivo}")
    return codigos


def escribir_codigos(codigos: list[dict]) -> Path:
    fecha = datetime.now().strftime("%Y-%m-%d")
    salida = Path(__file__).resolve().parent / f"siembra_identidad_{fecha}.jsonl"
    with salida.open("w", encoding="utf-8") as f:
        for fila in codigos:
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
    return salida


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Siembra alumnos, dispositivos y esquema de identidad con datos sinteticos en Neo4j."
    )
    parser.add_argument("--cantidad", type=int, default=12,
                         help="Cuantos alumnos sinteticos crear (por defecto 12).")
    args = parser.parse_args()

    codigos = sembrar(args.cantidad)
    salida = escribir_codigos(codigos)
    print(f"Codigos iniciales escritos en: {salida}")


if __name__ == "__main__":
    main()
