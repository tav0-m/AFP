"""Descarga series macroeconómicas de Chile desde la API pública de mindicador.cl (sin credenciales).

Uso:
    python scripts/descarga_mindicador.py --desde 2002 --hasta 2026 --salida data/raw

Series (disponibles desde 2002): dolar (observado, diario), ipc (variación mensual %), tpm (tasa de política
monetaria, diaria), imacec (variación anual %). El cobre solo existe desde 2013 y no se usa.
Guarda data/raw/macro_mindicador.csv en formato largo: fecha, indicador, valor.
"""
import argparse
import json
import time
import urllib.request
from pathlib import Path

INDICADORES = ("dolar", "ipc", "tpm", "imacec")


def descargar(indicador: str, anio: int, reintentos: int = 3) -> list[dict]:
    url = f"https://mindicador.cl/api/{indicador}/{anio}"
    for k in range(reintentos):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.load(r).get("serie", [])
        except Exception:
            if k == reintentos - 1:
                raise
            time.sleep(2 * (k + 1))
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--desde", type=int, default=2002)
    ap.add_argument("--hasta", type=int, default=2026)
    ap.add_argument("--salida", default="data/raw")
    a = ap.parse_args()
    filas = []
    for ind in INDICADORES:
        for anio in range(a.desde, a.hasta + 1):
            for obs in descargar(ind, anio):
                filas.append(f"{obs['fecha'][:10]},{ind},{obs['valor']}")
            time.sleep(0.2)                                   # cortesía con la API pública
        print(f"{ind}: {sum(1 for f in filas if f.split(',')[1] == ind)} observaciones")
    salida = Path(a.salida) / "macro_mindicador.csv"
    salida.write_text("fecha,indicador,valor\n" + "\n".join(sorted(filas)) + "\n", encoding="utf-8")
    print(f"Guardado {salida} ({len(filas)} filas)")


if __name__ == "__main__":
    main()
