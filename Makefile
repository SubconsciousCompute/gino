MYPY_OPTS:=--ignore-missing-imports --install-types --non-interactive

export PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring

all : build

build: wheel

wheel: pyproject.toml 
	poetry install
	poetry build 

lint check:
	poetry install 
	poetry run ruff gino tests
	poetry run pylint -E gino
	poetry run mypy $(MYPY_OPTS) --cache-dir=/tmp/ -m gino

fix:
	poetry run black gino/*.py tests/*.py

test: build 
	poetry install
	poetry run pytest -s tests/*.py

run:
	poetry run gino run-once

ci: build test
