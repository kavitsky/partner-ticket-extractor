PYTHON ?= python3
PY := .venv/bin/python

.PHONY: run install report regress clean-cache

run: install
	$(PY) main.py run

install: .venv/.installed

.venv/.installed: requirements.txt
	$(PYTHON) -m venv .venv
	$(PY) -m pip install -q -r requirements.txt
	touch $@

report: install
	$(PY) main.py report

regress: install
	$(PY) main.py regress

clean-cache:
	rm -rf .cache
