"""
Descarga de series del Banco Central de Chile (Base de Datos Estadísticos)
==========================================================================
Descarga la UF diaria y series macro auxiliares para el proyecto AFP.

Credenciales: NUNCA en el código. El script las lee de variables de entorno.

    Windows (PowerShell):
        $env:BCCH_USER="tu_usuario"
        $env:BCCH_PASS="tu_password"
    Linux / macOS:
        export BCCH_USER="tu_usuario"
        export BCCH_PASS="tu_password"

Uso:
    python descarga_bcentral.py                 # descarga UF + opcionales
    python descarga_bcentral.py --buscar uf     # busca el ID de una serie por nombre
    python descarga_bcentral.py --desde 2002-01-01 --salida ./datos

Requisitos: pip install requests pandas
"""
import argparse
import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import requests

BASE = "https://si3.bcentral.cl/SieteRestWS/SieteRestWS.ashx"

# Series objetivo. Si alguna cambia de código, el script lo reporta y sigue con el resto.
SERIES = {
    "uf":            ("F073.UFF.PRE.Z.D",           True,  "Unidad de Fomento, diaria"),
    "dolar_obs":     ("F073.TCO.PRE.Z.D",           False, "Dólar observado, diario"),
    "tpm":           ("F022.TPM.TIN.D001.NO.Z.D",   False, "Tasa de política monetaria"),
    "ipc":           ("F074.IPC.IND.Z.EP23.C.M",    False, "IPC índice, mensual"),
}


def llamar(params: dict) -> dict:
    usuario, clave = os.getenv("BCCH_USER"), os.getenv("BCCH_PASS")
    if not usuario or not clave:
        sys.exit("Faltan credenciales: define BCCH_USER y BCCH_PASS como variables de entorno.")
    p = {"user": usuario, "pass": clave, **params}
    r = requests.get(BASE, params=p, timeout=60)
    r.raise_for_status()
    return r.json()


def buscar(texto: str, frecuencia: str = "DAILY"):
    """Lista series cuyo nombre contenga el texto. Útil si un código dejó de existir."""
    js = llamar({"function": "SearchSeries", "frequency": frecuencia})
    filas = [(s.get("seriesId"), s.get("spanishTitle", "")) for s in js.get("SeriesInfos", [])]
    hit = [f for f in filas if texto.lower() in (f[1] or "").lower()]
    print(f"{len(hit)} coincidencias de '{texto}' en frecuencia {frecuencia}:")
    for sid, titulo in hit[:40]:
        print(f"  {sid:<32} {titulo}")


def descargar(series_id: str, desde: str, hasta: str) -> pd.DataFrame:
    js = llamar({"function": "GetSeries", "timeseries": series_id,
                 "firstdate": desde, "lastdate": hasta})
    if js.get("Codigo", 0) != 0:
        raise RuntimeError(f"{series_id}: {js.get('Descripcion')}")
    obs = js["Series"]["Obs"]
    df = pd.DataFrame(obs)
    df["fecha"] = pd.to_datetime(df["indexDateString"], format="%d-%m-%Y")
    df["valor"] = pd.to_numeric(df["value"], errors="coerce")   # 'NaN' en días sin dato
    df = df.loc[df["valor"].notna(), ["fecha", "valor"]].sort_values("fecha").reset_index(drop=True)
    return df


def control(nombre: str, df: pd.DataFrame, diaria: bool):
    print(f"  {nombre:<12} {len(df):>7,} obs  {df['fecha'].min():%Y-%m-%d} a {df['fecha'].max():%Y-%m-%d}"
          f"  min={df['valor'].min():,.2f}  max={df['valor'].max():,.2f}")
    if diaria:
        rango = pd.date_range(df["fecha"].min(), df["fecha"].max(), freq="D")
        faltan = len(rango.difference(df["fecha"]))
        print(f"               días calendario faltantes: {faltan}"
              f"{'  <-- revisar' if faltan else ''}")
    if (df["valor"] <= 0).any():
        print("               ALERTA: hay valores no positivos")
    saltos = df["valor"].pct_change().abs()
    if diaria and (saltos > 0.05).any():
        print(f"               ALERTA: {int((saltos > 0.05).sum())} saltos diarios sobre 5%")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--desde", default="2002-01-01")
    ap.add_argument("--hasta", default=date.today().isoformat())
    ap.add_argument("--salida", default="./datos_bcentral")
    ap.add_argument("--buscar", help="Busca el ID de una serie por nombre y termina")
    ap.add_argument("--frecuencia", default="DAILY", choices=["DAILY", "MONTHLY", "QUARTERLY", "ANNUAL"])
    a = ap.parse_args()

    if a.buscar:
        buscar(a.buscar, a.frecuencia)
        return

    salida = Path(a.salida); salida.mkdir(parents=True, exist_ok=True)
    print(f"Descargando desde {a.desde} hasta {a.hasta}\n")
    for nombre, (sid, obligatoria, desc) in SERIES.items():
        try:
            df = descargar(sid, a.desde, a.hasta)
            df.rename(columns={"valor": nombre}).to_csv(salida / f"{nombre}.csv", index=False,
                                                        float_format="%.6f")
            control(nombre, df, diaria=sid.endswith(".D"))
        except Exception as e:
            msg = f"  {nombre:<12} ERROR: {e}"
            if obligatoria:
                print(msg)
                sys.exit("\nLa serie obligatoria falló. Usa --buscar para encontrar el ID correcto:\n"
                         "    python descarga_bcentral.py --buscar \"unidad de fomento\"")
            print(msg + "  (opcional, se omite)")
    print(f"\nListo. Archivos en: {salida.resolve()}")


if __name__ == "__main__":
    main()
