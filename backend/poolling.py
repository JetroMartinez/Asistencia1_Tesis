import os
import time
from datetime import datetime
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

NEO4J_URI      = os.getenv("NEO4J_URI")
NEO4J_USER     = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

if not all([NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
    raise SystemExit("Faltan NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD en el .env")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

Q_LATEST = """
MATCH (t:Token)
WHERE t.used = true
RETURN t.token AS token, t.nombre AS nombre, t.matricula AS matricula,
       t.ip AS ip, t.date AS date, coalesce(t.warnings,0) AS warnings
ORDER BY t.date DESC
LIMIT 1
"""

Q_WARNINGS = """
MATCH (t:Token)
WHERE coalesce(t.warnings,0) > 0
RETURN t.token AS token, coalesce(t.warnings,0) AS warnings, t.ip AS ip, t.date AS date
ORDER BY t.warnings DESC, t.date DESC
LIMIT 20
"""

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def fetch_one(session, query):
    r = session.run(query).single()
    return dict(r) if r else None

def fetch_many(session, query):
    return [dict(r) for r in session.run(query)]

def main(poll_seconds=1.0):
    last_seen_token = None
    last_seen_date  = ""
    last_warnings = {}  # token -> warnings

    print(f"[{now_str()}] Vigilando Neo4j en {NEO4J_URI}")
    print(f"[{now_str()}] Poll cada {poll_seconds:.1f}s. Ctrl+C para salir.\n")

    try:
        while True:
            with driver.session() as session:
                latest = fetch_one(session, Q_LATEST)
                warns  = fetch_many(session, Q_WARNINGS)

            # 1) Nuevas asistencias (cuando cambia el último registro)
            if latest:
                token = latest.get("token")
                date  = latest.get("date") or ""
                if (token != last_seen_token) or (date != last_seen_date):
                    last_seen_token = token
                    last_seen_date  = date
                    print(f"[{now_str()}] NUEVA ASISTENCIA")
                    print(f"  fecha:      {latest.get('date')}")
                    print(f"  nombre:     {latest.get('nombre')}")
                    print(f"  matricula:  {latest.get('matricula')}")
                    print(f"  ip:         {latest.get('ip')}")
                    print(f"  token:      {latest.get('token')}")
                    print(f"  warnings:   {latest.get('warnings')}\n")

            # 2) Cambios en warnings (reuso de token)
            for w in warns:
                t = w.get("token")
                n = int(w.get("warnings") or 0)
                prev = last_warnings.get(t, 0)
                if n != prev:
                    last_warnings[t] = n
                    print(f"[{now_str()}] WARNING TOKEN REUSADO")
                    print(f"  token:    {t}")
                    print(f"  warnings: {n} (antes {prev})")
                    print(f"  fecha:    {w.get('date')}")
                    print(f"  ip:       {w.get('ip')}\n")

            time.sleep(poll_seconds)

    except KeyboardInterrupt:
        print(f"\n[{now_str()}] Saliendo...")
    finally:
        driver.close()

if __name__ == "__main__":
    main(poll_seconds=2)
