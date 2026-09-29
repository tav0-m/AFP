.PHONY: instalar datos pipeline pruebas app todo limpiar

instalar:
	pip install -r requirements.txt

datos:            ## actualiza la UF (requiere BCCH_USER y BCCH_PASS en el entorno)
	python scripts/descarga_bcentral.py --salida data/raw

pipeline:
	python run_pipeline.py

pruebas:
	python -m unittest discover -s tests -v

app:
	python app/build_app.py

todo: pruebas pipeline

limpiar:
	rm -rf data/processed/* reports/figuras/* reports/*.xlsx app/index.html app/resultados.json
