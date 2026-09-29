"""Etapa 1 - ETL de valores cuota y patrimonio (Superintendencia de Pensiones).

El CSV de vcfAFP.php no es una tabla plana: se reinicia con bloques de encabezado,
el conjunto de AFP vigentes cambia en el tiempo (fusiones y entradas) y marca
bloques como 'Confirmados' o 'Provisorios'. Este módulo lo convierte a formato largo.
"""
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

from . import config

RE_ESTADO = re.compile(r"^Valores\s+(Confirmados|Provisorios)", re.I)


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", t).strip().upper()


def _num(s: str) -> float:
    """'95.178,58' -> 95178.58"""
    s = s.strip()
    return np.nan if not s else float(s.replace(".", "").replace(",", "."))


def parsear_archivo(path: Path, fondo: str) -> pd.DataFrame:
    filas, afps, estado = [], [], None
    with path.open(encoding="latin-1") as f:
        for linea in f:
            linea = linea.rstrip("\r\n")
            if not linea.strip():
                continue
            m = RE_ESTADO.match(linea)
            if m:
                estado = "provisorio" if m.group(1).lower().startswith("prov") else "confirmado"
                continue
            if linea.startswith("Fecha;"):
                afps = [_norm(p) for p in linea.split(";")[1:][::2] if p.strip()]
                continue
            if linea.startswith(";"):
                continue
            partes = linea.split(";")
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", partes[0].strip()):
                continue
            vals = partes[1:]
            for i, afp in enumerate(afps):
                vc, pat = (vals[2 * i], vals[2 * i + 1]) if 2 * i + 1 < len(vals) else ("", "")
                filas.append((partes[0].strip(), fondo, afp, _num(vc), _num(pat), estado))
    df = pd.DataFrame(filas, columns=["fecha", "fondo", "afp", "valor_cuota", "patrimonio", "estado"])
    df["fecha"] = pd.to_datetime(df["fecha"])
    return df


def detectar_rebases(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Un salto enorme de cuota el día después de que otra AFP deja de informar es un
    cambio de escala por fusión (ej. PlanVital absorbe a Magíster, 01-03-2004), no rentabilidad."""
    ultima = df.groupby(["fondo", "afp"])["fecha"].max().reset_index(name="ultima")
    sosp = df.loc[df["retorno_diario"].abs() > config.UMBRAL_RETORNO_DIARIO]
    eventos = []
    for r in sosp.itertuples(index=False):
        sal = ultima[(ultima.fondo == r.fondo) & (ultima.ultima == r.fecha - pd.Timedelta(days=1))]
        eventos.append({"fecha": r.fecha, "fondo": r.fondo, "afp": r.afp,
                        "retorno_bruto": r.retorno_diario,
                        "afp_que_desaparece": ", ".join(sal.afp),
                        "diagnostico": "Rebase por fusión" if len(sal) else "Revisar manualmente"})
    eventos = pd.DataFrame(eventos)
    df["retorno_ajustado"] = df["retorno_diario"]
    if len(eventos):
        claves = {(e.fecha, e.fondo, e.afp) for e in eventos.itertuples() if e.afp_que_desaparece}
        mask = [(f, fo, a) in claves for f, fo, a in zip(df.fecha, df.fondo, df.afp)]
        df.loc[mask, "retorno_ajustado"] = 0.0
    return df, eventos


def construir(dir_raw: Path = config.DATA_RAW) -> tuple[pd.DataFrame, pd.DataFrame]:
    partes = []
    for p in sorted(dir_raw.glob("vcf*.csv")):
        fondo = re.search(r"vcf([A-E])", p.name, re.I).group(1).upper()
        partes.append(parsear_archivo(p, fondo))
    df = (pd.concat(partes, ignore_index=True).dropna(subset=["valor_cuota"])
            .sort_values(["fondo", "afp", "fecha"]).reset_index(drop=True))
    g = df.groupby(["fondo", "afp"], sort=False)["valor_cuota"]
    df["retorno_diario"] = g.pct_change()
    df["valor_repetido"] = df["retorno_diario"].eq(0)
    df["dia_habil_efectivo"] = (df.fecha.dt.dayofweek < 5) & ~df["valor_repetido"]
    df["patrimonio"] = df["patrimonio"].replace(0, np.nan)
    df, eventos = detectar_rebases(df)
    return df, eventos


def validar(df: pd.DataFrame) -> pd.DataFrame:
    huecos = sum(len(pd.date_range(d.fecha.min(), d.fecha.max()).difference(d.fecha))
                 for _, d in df.groupby(["fondo", "afp"]))
    return pd.DataFrame([
        ("Duplicados fecha-fondo-AFP", int(df.duplicated(["fecha", "fondo", "afp"]).sum())),
        ("Días calendario faltantes dentro de cada serie", int(huecos)),
        ("Valores cuota nulos", int(df.valor_cuota.isna().sum())),
        (f"Retornos diarios sobre {config.UMBRAL_RETORNO_DIARIO:.0%} (brutos)",
         int((df.retorno_diario.abs() > config.UMBRAL_RETORNO_DIARIO).sum())),
        ("Registros provisorios", int((df.estado == "provisorio").sum())),
    ], columns=["chequeo", "valor"])
