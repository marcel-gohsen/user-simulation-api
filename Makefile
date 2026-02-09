SHELL:=/bin/bash

IMAGE_NAME=registry.webis.de/code-lib/public-images/user-simulation-api
VERSION=$(shell poetry version -s)

docker_build:
	docker build -t "${IMAGE_NAME}:${VERSION}" -t "${IMAGE_NAME}:latest" .


docker_run:
	docker run -p 8888:8888 -v $(shell pwd)/database:/app/database "${IMAGE_NAME}:${VERSION}"

docker_push:
	docker push -a "${IMAGE_NAME}"