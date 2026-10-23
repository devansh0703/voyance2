PY = .venv/bin/python

data:           ## download raw AIS days + build voyages + weather join
	bash pipeline/fetch_data.sh
	$(PY) pipeline/build_voyages.py --month 2024-01 --days 08-14
	$(PY) pipeline/build_voyages.py --month 2024-04 --days 08-14
	$(PY) pipeline/build_voyages.py --month 2024-07 --days 08-14
	$(PY) pipeline/weather.py 2024-01
	$(PY) pipeline/weather.py 2024-04
	$(PY) pipeline/weather.py 2024-07

train:
	$(PY) pipeline/train.py

drift:
	$(PY) pipeline/drift.py

web-data:
	$(PY) pipeline/export_web_data.py

web:
	cd web && bun run build

api:
	.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000

.PHONY: data train drift web-data web api

dev2:
	@(.venv/bin/uvicorn backend.main:app --port 8000 &) ; cd web && bun run dev
.PHONY: dev2
