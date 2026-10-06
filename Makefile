PYTHON ?= python3.11
PYTHONPATH := packages/contracts/src:packages/asset-store/src
PYTHON_QUALITY_FILES := packages/contracts/src/skillweave_contracts/asset_types.py packages/asset-store/src/a2flow_asset_store/records.py

.PHONY: quality-python typecheck-python lint-python format-check-python

quality-python: typecheck-python lint-python format-check-python

typecheck-python:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m mypy

lint-python:
	$(PYTHON) -m ruff check $(PYTHON_QUALITY_FILES)

format-check-python:
	$(PYTHON) -m ruff format --check $(PYTHON_QUALITY_FILES)
