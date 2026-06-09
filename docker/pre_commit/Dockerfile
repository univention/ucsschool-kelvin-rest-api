FROM gitregistry.knut.univention.de/univention/dev/projects/ucs-base-image/ucs-base-python-524@sha256:d3641b6ba16d00a5f600942a8483f0338357d4dcc8240c4a5fe91befa95541b1

ENV PYTHONUNBUFFERED=1
ENV UV_SYSTEM_PYTHON=1
ENV PIPX_HOME="/opt/pipx"
ENV PIPX_BIN_DIR="/usr/local/bin"

ARG UID=1000
ARG GID=1000

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
    groupadd --gid "${GID}" precommit && \
    useradd --create-home --shell /bin/bash --uid "${UID}" --gid "${GID}" precommit

USER precommit
WORKDIR /src
