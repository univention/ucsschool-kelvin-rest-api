# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

FROM gitregistry.knut.univention.de/univention/dev/projects/ucs-base-image/ucs-base-python-527:0.24.4@sha256:ce6f7576cd5dd832b3be89ac83e83b9624ca9ea3560f6158bb8c4189c3409660

ENV PYTHONUNBUFFERED=1
ENV UV_SYSTEM_PYTHON=1
ENV PIPX_HOME="/opt/pipx"
ENV PIPX_BIN_DIR="/usr/local/bin"

ARG UID=1000
ARG GID=1000
ARG BASEDPYRIGHT_VERSION=1.39.8

RUN apt-get update && \
    apt-get install -y \
      build-essential \
      python3-dev \
      xz-utils \
      pipx \
      git \
      libldap2-dev \
      libsasl2-dev && \
    pipx install uv && \
    pipx install "basedpyright==${BASEDPYRIGHT_VERSION}" && \
    getent group "${GID}" >/dev/null || groupadd --gid "${GID}" precommit && \
    useradd --create-home --shell /bin/bash --uid "${UID}" --gid "${GID}" precommit

USER precommit
WORKDIR /src
