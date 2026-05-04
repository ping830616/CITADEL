.PHONY: install sample smoke test reproduce-smoke clean

PYTHON ?= python
SEED ?= 123
THREADS ?= 1
SAMPLE_ROWS ?= 600

install:
	$(PYTHON) -m pip install -U pip
	$(PYTHON) -m pip install -e ".[dev,notebook]"

sample:
	$(PYTHON) scripts/generate_sample_data.py --out-root data/sample --rows $(SAMPLE_ROWS) --seed $(SEED)

smoke:
	$(PYTHON) scripts/run_tcad_ablation.py --data-root data/sample --out-root results/tcad_smoke --preset smoke --seed $(SEED) --threads $(THREADS) --generate-sample-if-missing

test:
	$(PYTHON) -m pytest

reproduce-smoke: sample smoke test

clean:
	rm -rf .pytest_cache data/sample results/tcad_smoke
