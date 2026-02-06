FROM nvidia/cuda:13.1.1-cudnn-devel-ubuntu24.04
LABEL authors="Marcel Gohsen"

SHELL ["/bin/bash", "-c"]

RUN set -x \
    && apt update \
    && apt install -y python3 python3-pip python-is-python3 \
    && rm -rf /var/lib/apt/lists/*

RUN set -x \
    && python3 -m pip config set global.break-system-packages true \
    && python3 -m pip install poetry

COPY pyproject.toml poetry.lock README.md /app/
WORKDIR /app/

RUN set -x \
    && python3 -m poetry config virtualenvs.create false \
    && python3 -m poetry --no-root --no-interaction --no-ansi install \
    && python3 -m pip install --no-build-isolation flash-attn

COPY . /app/

RUN python3 -m poetry --no-interaction --no-ansi install

ENV ADMIN_NAME=""\
    ADMIN_PASSWORD=""\
    SHARED_TASK="dummy"

EXPOSE 8888

CMD python3 -m poetry run serve --admin-name ${ADMIN_NAME} --admin-password ${ADMIN_PASSWORD} --shared-task ${SHARED_TASK}