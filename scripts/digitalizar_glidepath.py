"""Digitaliza la trayectoria de inversión (exposición máxima a activos de crecimiento) desde el gráfico
de la minuta de consulta pública de la SP (jul-2026), para auditar config.GLIDEPATH["curva_consulta"].

Uso:
    python scripts/digitalizar_glidepath.py minuta.pdf
    (minuta: spensiones.cl/portal/institucional/594/articles-11315_nt_561_minuta.pdf, página 4)

Método: se extrae la imagen del gráfico, se ubican los ejes con la grilla (100% y 80%) y en cada edad
entera se toma el centro vertical de los píxeles azules de la línea. Requiere pymupdf, numpy y pillow.
"""
import io
import sys

import numpy as np
import pymupdf
from PIL import Image

# Calibración del gráfico original (1209 x 582 px): x de las edades 18 y 74, y de las líneas 100% y 0%.
X18, X74, Y100, Y0 = 85, 1187, 12, 561.5
AZUL = np.array([31, 119, 180])


def digitalizar(pdf: str, pagina: int = 4) -> dict[int, float]:
    doc = pymupdf.open(pdf)
    xref = doc[pagina - 1].get_images()[0][0]
    img = np.asarray(Image.open(io.BytesIO(doc.extract_image(xref)["image"])).convert("RGB")).astype(int)
    azul = (np.abs(img - AZUL) < 30).all(axis=2)
    dx = (X74 - X18) / (74 - 18)
    out = {}
    for edad in range(18, 76):
        x = min(int(round(X18 + (edad - 18) * dx)), img.shape[1] - 2)
        filas = np.where(azul[:, max(x - 1, 0):x + 2].any(axis=1))[0]
        out[edad] = (Y0 - filas.mean()) / (Y0 - Y100)
    return out


if __name__ == "__main__":
    for edad, g in digitalizar(sys.argv[1]).items():
        print(f"{edad},{g:.3f}")
