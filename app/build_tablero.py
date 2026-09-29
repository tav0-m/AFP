"""Construye app/tablero.html (autocontenido): tablero de resultados con los datos del pipeline.
Solo embebe lo que el tablero usa (sin tablas de mortalidad ni retornos crudos)."""
import json
from pathlib import Path

AQUI = Path(__file__).resolve().parent
CLAVES = ["generado", "rango", "uf", "uf_fecha", "hallazgos", "rentabilidad", "indice_mensual", "regimen",
          "glidepath", "edad_legal", "montecarlo", "escenarios_mercado", "escenarios_pensiones",
          "incertidumbre", "robustez", "bandas"]
todo = json.loads((AQUI / "resultados.json").read_text(encoding="utf-8"))
datos = json.dumps({k: todo[k] for k in CLAVES if k in todo}, ensure_ascii=False).replace("</", "<\\/")
html = (AQUI / "tablero_plantilla.html").read_text(encoding="utf-8").replace("__DATOS__", datos)
(AQUI / "tablero.html").write_text(html, encoding="utf-8")
print(f"app/tablero.html: {len(html) / 1024:.0f} KB")
