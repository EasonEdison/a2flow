PYTHON ?= python3.11
PYTHONPATH := packages/contracts/src:packages/asset-store/src:services/management-api/src
PYTHON_QUALITY_FILES := \
	packages/contracts/src/skillweave_contracts/asset_types.py \
	packages/asset-store/src/a2flow_asset_store/records.py \
	services/management-api/src/a2flow_management/contracts.py \
	services/management-api/src/a2flow_management/db_types.py \
	services/management-api/src/a2flow_management/http_models.py \
	services/management-api/src/a2flow_management/relations.py \
	services/management-api/src/a2flow_management/repositories.py \
	services/management-api/src/a2flow_management/publication.py \
	services/management-api/src/a2flow_management/releases.py
PYTHON_QUALITY_TESTS := \
	services/management-api/tests/test_asset_kernel_types.py \
	services/management-api/tests/test_relations.py

.PHONY: quality-python typecheck-python lint-python format-check-python

quality-python: typecheck-python lint-python format-check-python

typecheck-python:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m mypy

lint-python:
	$(PYTHON) -m ruff check $(PYTHON_QUALITY_FILES) $(PYTHON_QUALITY_TESTS)

format-check-python:
	$(PYTHON) -m ruff format --check $(PYTHON_QUALITY_FILES) $(PYTHON_QUALITY_TESTS)
