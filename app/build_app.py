"""Construye app/index.html (autocontenido) insertando resultados.json en la plantilla."""
from pathlib import Path

AQUI = Path(__file__).resolve().parent
datos = (AQUI / "resultados.json").read_text(encoding="utf-8").replace("</", "<\\/")
html = (AQUI / "plantilla.html").read_text(encoding="utf-8").replace("__DATOS__", datos)
(AQUI / "index.html").write_text(html, encoding="utf-8")
print(f"app/index.html: {len(html) / 1024:.0f} KB")
