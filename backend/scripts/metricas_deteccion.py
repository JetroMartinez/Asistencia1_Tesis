"""Tasa de deteccion y de falsos positivos a partir de (:IntentoRechazado).

Seccion 9 de CLAUDE.md, metrica 2. Los rechazos por si solos no bastan: hace falta
saber cuantas peticiones se mandaron y cuales eran ataque. Eso lo aporta el
manifiesto JSONL que escribe el banco de ataques, una linea por peticion:

    {"id_prueba": "<hex, <=64>", "escenario": "reuso_token",
     "clase": "ataque" | "legitimo", "motivo_esperado": "token_reutilizado" | null}

Cada peticion del banco manda el mismo id en el encabezado X-Id-Prueba; el servidor
lo guarda como etiqueta en el nodo y nunca lo usa para decidir. Una peticion del
manifiesto con nodo IntentoRechazado se considera rechazada; sin nodo, aceptada.

- Deteccion (por escenario y global): ataques rechazados / ataques enviados.
- Falsos positivos (por motivo y global): legitimas rechazadas / legitimas enviadas.

Sin --manifiesto solo se reportan conteos descriptivos por motivo y endpoint, sin
tasas. Las salidas van a docs/evidencias/ con fecha y hora en el nombre.

Uso (desde backend/):
    python scripts/metricas_deteccion.py --manifiesto ruta/manifiesto.jsonl
    python scripts/metricas_deteccion.py --desde 2026-10-04 --hasta 2026-10-05
"""
import argparse
import json
import math
import os
import sys
from   collections import Counter, defaultdict
from   datetime    import datetime
from   pathlib     import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from   dotenv      import load_dotenv
from   neo4j       import GraphDatabase

import rechazos

load_dotenv(BACKEND_DIR / ".env")

EVIDENCIAS = BACKEND_DIR.parent / "docs" / "evidencias"
# "informativo": peticiones que se cuentan aparte y nunca entran en la tasa de
# deteccion ni en la de falsos positivos (p. ej. el intento mal tecleado que
# precede a un login correcto; ver docs/decisiones.md, decision 3 del banco).
CLASES     = ("ataque", "legitimo", "informativo")


def wilson(exitos: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """Intervalo de confianza de Wilson al 95 % para una proporcion. Con n
    pequeno (el banco de ataques no manda miles de peticiones) se comporta mejor
    que la aproximacion normal simple."""
    if n == 0:
        return None
    p = exitos / n
    centro = (p + z * z / (2 * n)) / (1 + z * z / n)
    margen = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centro - margen), min(1.0, centro + margen)


def tasa(exitos: int, n: int) -> dict:
    ic = wilson(exitos, n)
    return {"exitos": exitos, "n": n, "tasa": exitos / n if n else None,
            "ic95": list(ic) if ic else None}


def leer_manifiesto(ruta: Path) -> list[dict]:
    entradas, vistos = [], set()
    for num, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1):
        if not linea.strip():
            continue
        e = json.loads(linea)
        id_prueba = rechazos.id_prueba_valido(e.get("id_prueba"))
        if id_prueba is None:
            sys.exit(f"Linea {num}: id_prueba invalido (hex minusculas, <=64): {e.get('id_prueba')!r}")
        if id_prueba in vistos:
            sys.exit(f"Linea {num}: id_prueba repetido {id_prueba}")
        if e.get("clase") not in CLASES:
            sys.exit(f"Linea {num}: clase debe ser una de {CLASES}")
        esperado = e.get("motivo_esperado")
        if esperado is not None and esperado not in rechazos.MOTIVOS:
            sys.exit(f"Linea {num}: motivo_esperado fuera del catalogo: {esperado!r}")
        vistos.add(id_prueba)
        entradas.append({"id_prueba": id_prueba, "escenario": str(e.get("escenario", "")),
                         "clase": e["clase"], "motivo_esperado": esperado})
    return entradas


def rechazos_por_id(driver, ids: list[str]) -> dict[str, dict]:
    with driver.session() as s:
        filas = s.run(
            "MATCH (r:IntentoRechazado) WHERE r.id_prueba IN $ids "
            "RETURN r.id_prueba AS id_prueba, r.motivo AS motivo, "
            "r.endpoint AS endpoint, r.status_http AS status_http", ids=ids).data()
    # El servidor registra a lo mas un rechazo por peticion
    return {f["id_prueba"]: f for f in filas}


def calcular(entradas: list[dict], encontrados: dict[str, dict]) -> dict:
    por_escenario = defaultdict(lambda: {"clase": None, "n": 0, "rechazadas": 0,
                                         "motivos": Counter(), "con_motivo_esperado": 0,
                                         "n_con_esperado": 0})
    por_motivo = defaultdict(lambda: {"ataques_detenidos": 0, "legitimas_rechazadas": 0})
    totales = Counter()

    for e in entradas:
        r = encontrados.get(e["id_prueba"])
        esc = por_escenario[e["escenario"]]
        if esc["clase"] not in (None, e["clase"]):
            sys.exit(f"Escenario {e['escenario']!r} mezcla clases ataque y legitimo")
        esc["clase"] = e["clase"]
        esc["n"] += 1
        # "informativo" se cuenta por escenario (descriptivo) pero no alimenta
        # los totales globales de deteccion/falsos positivos.
        if e["clase"] != "informativo":
            totales[e["clase"]] += 1
        if e["motivo_esperado"] is not None:
            esc["n_con_esperado"] += 1
        if r is None:
            continue
        esc["rechazadas"] += 1
        esc["motivos"][r["motivo"]] += 1
        if e["motivo_esperado"] == r["motivo"]:
            esc["con_motivo_esperado"] += 1
        if e["clase"] == "ataque":
            totales["ataque_rechazadas"] += 1
            por_motivo[r["motivo"]]["ataques_detenidos"] += 1
        elif e["clase"] == "legitimo":
            totales["legitimo_rechazadas"] += 1
            por_motivo[r["motivo"]]["legitimas_rechazadas"] += 1
        # "informativo" rechazado: ya quedo en esc["motivos"], fuera de por_motivo

    n_legitimas = totales["legitimo"]
    return {
        "global": {
            "deteccion": tasa(totales["ataque_rechazadas"], totales["ataque"]),
            "falsos_positivos": tasa(totales["legitimo_rechazadas"], n_legitimas),
        },
        "por_escenario": {
            nombre: {
                "clase": d["clase"],
                # Para ataques es deteccion; para legitimos, falsos positivos
                "rechazo": tasa(d["rechazadas"], d["n"]),
                "motivos": dict(d["motivos"]),
                "motivo_esperado_coincide": tasa(d["con_motivo_esperado"], d["n_con_esperado"]),
            }
            for nombre, d in sorted(por_escenario.items())
        },
        "por_motivo": {
            motivo: {**d, "tasa_falsos_positivos": tasa(d["legitimas_rechazadas"], n_legitimas)}
            for motivo, d in sorted(por_motivo.items())
        },
    }


def descriptivo(driver, desde: float | None, hasta: float | None) -> dict:
    with driver.session() as s:
        filas = s.run(
            "MATCH (r:IntentoRechazado) "
            "WHERE ($desde IS NULL OR r.marca_tiempo >= $desde) "
            "AND ($hasta IS NULL OR r.marca_tiempo < $hasta) "
            "RETURN r.motivo AS motivo, r.endpoint AS endpoint, count(*) AS n "
            "ORDER BY motivo, endpoint", desde=desde, hasta=hasta).data()
    return {"conteos": filas, "total": sum(f["n"] for f in filas)}


def fmt(t: dict) -> str:
    if t["n"] == 0:
        return "n=0 (sin datos)"
    lo, hi = t["ic95"]
    return f"{t['exitos']}/{t['n']} = {t['tasa']:.3f} (IC95 {lo:.3f}-{hi:.3f})"


def a_texto(resultado: dict) -> str:
    lineas = [f"# Metricas de deteccion — {resultado['generado_en']}",
              f"# Fuente: {resultado['fuente']}", ""]
    if "conteos" in resultado:
        lineas += ["SIN MANIFIESTO: conteos descriptivos, no hay tasas de deteccion ni de",
                   "falsos positivos porque no se sabe que peticiones eran ataque.", "",
                   f"{'motivo':<28}{'endpoint':<26}{'n':>6}"]
        lineas += [f"{f['motivo']:<28}{f['endpoint']:<26}{f['n']:>6}" for f in resultado["conteos"]]
        lineas.append(f"\nTotal: {resultado['total']}")
        return "\n".join(lineas) + "\n"

    g = resultado["global"]
    lineas += [f"Deteccion global:         {fmt(g['deteccion'])}",
               f"Falsos positivos global:  {fmt(g['falsos_positivos'])}", "",
               "Por escenario (ataque: tasa de deteccion; legitimo: tasa de falsos",
               "positivos; informativo: descriptivo, no entra en ninguna tasa global)"]
    for nombre, d in resultado["por_escenario"].items():
        lineas.append(f"  [{d['clase']}] {nombre}: {fmt(d['rechazo'])}")
        if d["motivos"]:
            lineas.append(f"      motivos: {d['motivos']}")
        if d["motivo_esperado_coincide"]["n"]:
            lineas.append(f"      motivo esperado: {fmt(d['motivo_esperado_coincide'])}")
    lineas += ["", "Por motivo",
               f"  {'motivo':<28}{'ataques':>9}{'legitimas':>11}  tasa FP"]
    for motivo, d in resultado["por_motivo"].items():
        lineas.append(f"  {motivo:<28}{d['ataques_detenidos']:>9}{d['legitimas_rechazadas']:>11}"
                      f"  {fmt(d['tasa_falsos_positivos'])}")
    return "\n".join(lineas) + "\n"


def epoch(texto: str | None) -> float | None:
    return datetime.fromisoformat(texto).timestamp() if texto else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--manifiesto", type=Path, help="JSONL del banco de ataques")
    parser.add_argument("--desde", help="ISO 8601; solo en modo descriptivo")
    parser.add_argument("--hasta", help="ISO 8601; solo en modo descriptivo")
    parser.add_argument("--salida", type=Path, default=EVIDENCIAS)
    args = parser.parse_args()

    driver = GraphDatabase.driver(os.getenv("NEO4J_URI"),
                                  auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD")))
    ahora = datetime.now()
    try:
        if args.manifiesto:
            entradas = leer_manifiesto(args.manifiesto)
            resultado = calcular(entradas, rechazos_por_id(driver, [e["id_prueba"] for e in entradas]))
            fuente = f"manifiesto {args.manifiesto.name} ({len(entradas)} peticiones)"
        else:
            resultado = descriptivo(driver, epoch(args.desde), epoch(args.hasta))
            fuente = f"IntentoRechazado desde={args.desde} hasta={args.hasta}"
    finally:
        driver.close()

    resultado = {"generado_en": ahora.isoformat(timespec="seconds"), "fuente": fuente, **resultado}
    texto = a_texto(resultado)

    args.salida.mkdir(parents=True, exist_ok=True)
    base = args.salida / f"metricas_deteccion_{ahora:%Y-%m-%d_%H%M%S}"
    base.with_suffix(".json").write_text(json.dumps(resultado, indent=2, ensure_ascii=False),
                                         encoding="utf-8")
    base.with_suffix(".txt").write_text(texto, encoding="utf-8")
    print(texto)
    print(f"Guardado en {base}.txt y .json")


if __name__ == "__main__":
    main()
