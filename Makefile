MYPY_OPTS:=--ignore-missing-imports --install-types --non-interactive

export PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring

all : build

build:
	poetry run maturin develop


wheel: pyproject.toml 
	poetry install
	poetry run maturin build
	unzip -l ./target/wheels/cmo-*-cp39-*.whl

build_in_docker: build_image
	podman run \
		-v $(PWD):/app \
		subcom/cmo 

build_image:
	podman build -f .ci/Dockerfile  -t subcom/cmo


bmors build_ext:
	poetry run maturin develop


lint check:
	poetry install 
	poetry run ruff cmo tests
	poetry run pylint -E cmo
	poetry run mypy $(MYPY_OPTS) --cache-dir=/tmp/ -m cmo
	poetry run pylint -E cmo

fix:
	poetry run black cmo/*.py tests/*.py

test: build 
	poetry install
	poetry run pytest -s tests/*.py

run:
	poetry run cmo run-once

image:
	docker build -t subcomdocker/cmo .

deploy:
	docker compose up -d --build 

ci: build test
