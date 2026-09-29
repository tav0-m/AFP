"""Etapa 2 - Retornos reales (UF), ponderación por afiliados e índices del sistema."""
import unicodedata

import numpy as np
import pandas as pd

from . import config


def cargar_uf(path=None) -> pd.DataFrame:
    uf = pd.read_csv(path or config.DATA_RAW / "uf.csv", parse_dates=["fecha"])
    return uf.sort_values("fecha").drop_duplicates("fecha")


def cargar_afiliados(path=None) -> pd.DataFrame:
    """Afiliados por AFP (trimestral). El archivo de la SP trae filas de notas al pie
    y una fila 'SISTEMA' de totales; ambas se descartan."""
    import openpyxl
    wb = openpyxl.load_workbook(path or config.DATA_RAW / "afiliados_edad_afp.xlsx", data_only=True)
    ws = wb[wb.sheetnames[0]]
    filas = [(r[0], r[1], r[15]) for r in ws.iter_rows(min_row=3, values_only=True)]
    af = pd.DataFrame(filas, columns=["fecha", "afp", "n_afiliados"])
    af["fecha"] = pd.to_datetime(af["fecha"], errors="coerce")
    af = af.dropna(subset=["fecha"])
    af["afp"] = (af["afp"].astype(str)
                 .map(lambda t: unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode())
                 .str.upper().str.strip())
    af["n_afiliados"] = pd.to_numeric(af["n_afiliados"], errors="coerce")
    af = af[af.afp != "SISTEMA"]
    return af.groupby(["fecha", "afp"], as_index=False)["n_afiliados"].sum()


def agregar_reales(vc: pd.DataFrame, uf: pd.DataFrame, afil: pd.DataFrame) -> pd.DataFrame:
    df = vc.merge(uf, on="fecha", how="left").sort_values(["fondo", "afp", "fecha"])
    df["uf"] = df.groupby(["fondo", "afp"])["uf"].transform(lambda s: s.ffill().bfill())
    df["valor_cuota_uf"] = df["valor_cuota"] / df["uf"]
    df["retorno_real_diario"] = df.groupby(["fondo", "afp"], sort=False)["valor_cuota_uf"].pct_change()
    # neutraliza los mismos rebases por fusión detectados en nominal
    rebase = df["retorno_ajustado"].eq(0) & (df["retorno_diario"].abs() > config.UMBRAL_RETORNO_DIARIO)
    df["retorno_real_ajustado"] = df["retorno_real_diario"].where(~rebase, 0.0)
    df = pd.merge_asof(df.sort_values("fecha"), afil.sort_values("fecha"),
                       on="fecha", by="afp", direction="backward")
    df["n_afiliados"] = df.groupby("afp")["n_afiliados"].transform(lambda s: s.ffill().bfill())
    return df.sort_values(["fondo", "afp", "fecha"]).reset_index(drop=True)


def indice_sistema(df: pd.DataFrame, col_ret: str = "retorno_real_ajustado",
                   desde: str = config.INICIO_MULTIFONDOS, solo_confirmados: bool = True) -> pd.DataFrame:
    """Retorno diario del sistema por fondo, ponderado por afiliados de cada AFP."""
    d = df[df.fecha >= desde]
    if solo_confirmados:
        d = d[d.estado == "confirmado"]
    d = d.assign(r=d[col_ret].fillna(0), w=d["n_afiliados"].fillna(0))
    d = d.assign(rw=d.r * d.w)
    agg = d.groupby(["fecha", "fondo"]).agg(rw=("rw", "sum"), w=("w", "sum"), rm=("r", "mean"))
    ret = np.where(agg.w > 0, agg.rw / agg.w.replace(0, np.nan), agg.rm)
    out = agg.assign(retorno=ret).reset_index()[["fecha", "fondo", "retorno"]]
    out = out.pivot(index="fecha", columns="fondo", values="retorno").sort_index()
    out.iloc[0] = 0.0     # base 100 el primer día
    return out


def a_mensual(ret_diario: pd.DataFrame) -> pd.DataFrame:
    """Compone retornos diarios a mensuales (fin de mes)."""
    nivel = (1 + ret_diario.fillna(0)).cumprod()
    fin_mes = nivel.resample("ME").last()
    m = fin_mes.pct_change().dropna(how="all")
    # descarta el último mes si está incompleto (menos de 20 días de datos)
    ultimo = ret_diario.index.max()
    if ultimo.day < 20:
        m = m.iloc[:-1]
    return m


def resumen_rentabilidad(ret_diario: pd.DataFrame) -> pd.DataFrame:
    nivel = (1 + ret_diario.fillna(0)).cumprod()
    anios = (nivel.index[-1] - nivel.index[0]).days / 365.25
    return pd.DataFrame({
        "rent_anual": nivel.iloc[-1] ** (1 / anios) - 1,
        "max_caida": (nivel / nivel.cummax() - 1).min(),
    })
