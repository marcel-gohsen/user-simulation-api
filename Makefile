SHELL:=/bin/bash

IMAGE_NAME=registry.webis.de/code-lib/public-images/user-simulation-api
VERSION=$(shell poetry version -s)

build:
	docker build -t "${IMAGE_NAME}:${VERSION}" -t "${IMAGE_NAME}:latest" .

push:
	docker push -a "${IMAGE_NAME}"