PY ?= python3
.PHONY: test lint eval ui-test serve ext docs tour concepts
test:
	PYTHONPATH=src $(PY) -m unittest discover -s tests -t . -q
lint:
	ruff check . && mypy src
eval:
	rx eval --oracle
serve:
	rx serve
ext:
	cd vscode-extension && npm install && npm run compile
docs:
	PYTHONPATH=src $(PY) scripts/gen_protocol_doc.py > docs/PROTOCOL.md
tour:
	$(PY) scripts/tour.py --pause
concepts:
	$(PY) scripts/concepts/run_all.py
