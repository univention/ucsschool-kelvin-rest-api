# SPDX-FileCopyrightText: 2020-2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

# The CCF image the Kelvin connector is built on (target connector-prod); a
# global ARG, as it names a FROM image and fills the base.name label.
ARG CCF_BASE_IMAGE=gitregistry.knut.univention.de/dwiesent/common-connector-framework/ccf-python-postgres:0.1.1

FROM gitregistry.knut.univention.de/univention/dev/projects/ucs-base-image/ucs-base-python-527:0.24.4@sha256:ce6f7576cd5dd832b3be89ac83e83b9624ca9ea3560f6158bb8c4189c3409660 AS base

ARG OPENAPI_CLIENT_GENERATOR_VERSION="5.4.0"
ARG OPENAPI_CLIENT_GENERATOR_JAR="openapi-generator-cli-$OPENAPI_CLIENT_GENERATOR_VERSION.jar"
ARG OPENAPI_CLIENT_GENERATOR_JAR_URL="https://repo1.maven.org/maven2/org/openapitools/openapi-generator-cli/$OPENAPI_CLIENT_GENERATOR_VERSION/$OPENAPI_CLIENT_GENERATOR_JAR"

ENV PYTHONUNBUFFERED=1
ENV VIRTUAL_ENV="/venv"

ADD $OPENAPI_CLIENT_GENERATOR_JAR_URL /kelvin/openapi-generator/jar/

WORKDIR /kelvin

FROM base AS builder

ENV UV_SYSTEM_PYTHON=1
ENV UV_PROJECT_ENVIRONMENT="/venv"
ENV UV_VERSION=0.8.0
ENV PIPX_BIN_DIR="/usr/local/bin"
RUN apt-get install -y build-essential python3-dev xz-utils pipx git libldap2-dev libsasl2-dev
RUN pipx install uv=="$UV_VERSION"

COPY uv.lock .
COPY pyproject.toml .
COPY kelvin-api ./kelvin-api
COPY ucs-school-import ./ucs-school-import
COPY ucs-school-lib ./ucs-school-lib
COPY univention-directory-manager-modules-slim ./univention-directory-manager-modules-slim
COPY univention-lib-slim ./univention-lib-slim
COPY ucsschool-objects ./ucsschool-objects
COPY kelvin-connector ./kelvin-connector
COPY openapi-client-udm-1.0.2.tar.gz ccf-0.1.1.tar.gz ./
COPY ucs-test-ucsschool-kelvin ./ucs-test-ucsschool-kelvin

ARG KELVIN_BUILD_VERSION="999.0.0"
RUN KELVIN_BUILD_VERSION=$KELVIN_BUILD_VERSION uv sync --locked --all-packages --group dev
RUN cd ucs-test-ucsschool-kelvin && apt-get build-dep -y . && dpkg-buildpackage


# Render readme.rst and changelog.rst into the static HTML served by the API.
# Reuses the documentation image so the Univention Sphinx roles resolve without
# mirroring the doc toolchain into this project (build_docs.py explains why).
FROM gitregistry.knut.univention.de/univention/dev/docs/sphinx-docker/base@sha256:5d6aac4c1f8d7af49db226d07984f01c3f6c0e99e78d671942a9ffd32cb60639 AS docs-builder
WORKDIR /kelvin
RUN pip install --no-cache-dir lxml
COPY build_docs.py .
COPY kelvin-api/changelog.rst kelvin-api/readme.rst ./kelvin-api/
RUN python3 build_docs.py


FROM base AS kelvin-prod

RUN apt-get install -y libldap-2.5-0 openjdk-17-jre-headless procps libmagic1
RUN mkdir -pv /etc/univention/kelvin
RUN mkdir -pv /var/lib/ucs-school-import/kelvin-hooks
RUN mkdir -pv /var/lib/ucs-school-lib/kelvin-hooks
RUN mkdir -pv /var/cache/univention-config/
COPY --from=builder $VIRTUAL_ENV $VIRTUAL_ENV
COPY --from=builder /kelvin/ucs-test-ucsschool-kelvin*deb ./
COPY uv.lock .
COPY pyproject.toml .
COPY docker/start-kelvin.sh .
COPY kelvin-api ./kelvin-api
COPY --from=docs-builder /kelvin/kelvin-api/static/changelog.html /kelvin/kelvin-api/static/readme.html ./kelvin-api/static/
COPY alembic ./alembic
COPY pyproject.toml .
COPY ucs-school-import ./ucs-school-import
COPY ucs-school-lib ./ucs-school-lib
COPY univention-directory-manager-modules-slim ./univention-directory-manager-modules-slim
COPY univention-lib-slim ./univention-lib-slim
COPY ucsschool-objects ./ucsschool-objects
COPY kelvin-connector ./kelvin-connector
COPY openapi-client-udm-1.0.2.tar.gz ccf-0.1.1.tar.gz ./
COPY ucs-school-import/usr/share/ucs-school-import/configs/ /usr/share/ucs-school-import/configs/
COPY ucs-school-import/modules/ucsschool/lib/create_ou.py ucs-school-lib/modules/ucsschool/lib/create_ou.py
COPY kelvin-api/usr/share/ucs-school-import/checks/*.py /usr/share/ucs-school-import/checks/
COPY kelvin-api/empty_configs /var/lib/ucs-school-import/configs
COPY kelvin-api/usr/share/ucs-school-import/configs/kelvin_defaults.json /usr/share/ucs-school-import/configs/

ENV PATH="$VIRTUAL_ENV/bin:$PATH"
HEALTHCHECK --interval=5s --timeout=3s --start-period=60s --retries=5 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8911/health')" || exit 1
ENTRYPOINT ["/kelvin/start-kelvin.sh"]
EXPOSE 8911

ARG app_id
ARG commit
ARG date
ARG version

LABEL "description"="Image of UCS app 'UCS@school Kelvin REST API' ('$app_id')." \
    "url"="https://www.univention.com/products/univention-app-center/app-catalog/$app_id/" \
    "version"="$version" \
    "release date"="$date" \
    "commit"="$commit" \
    "APP_NAME"="ucsschool-kelvin-rest-api"


# The Kelvin connector is a Common Connector Framework (CCF) image plus the
# Kelvin callback (kelvin-connector and ucsschool-objects). The CCF image runs
# Debian trixie's Python 3.13 on distroless Debian trixie, so the callback's
# dependencies are installed for exactly that interpreter, as plain
# directories on the callback path. The builder is the UCS 5.3 base image:
# UCS 5.3 is based on trixie (same Python 3.13 and glibc 2.41) and comes from
# Univention's registry instead of Docker Hub. python-ldap has no wheels: it
# is compiled here against libldap, which the image then gets (see /app/lib).
FROM gitregistry.knut.univention.de/univention/dev/projects/ucs-base-image/ucs-base-python-530:0.25.1@sha256:25e5e183b1b4f75c64e0c697d5795a8e9c15b935453c2a64406d7d1ab40b2214 AS connector-builder

COPY --from=ghcr.io/astral-sh/uv:0.10.10 /uv /usr/local/bin/uv
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        libldap-dev \
        libsasl2-dev \
        python3 \
        python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
# The whole workspace: uv checks the lockfile against all members.
COPY uv.lock pyproject.toml openapi-client-udm-1.0.2.tar.gz ccf-0.1.1.tar.gz ./
COPY kelvin-api ./kelvin-api
COPY ucs-school-import ./ucs-school-import
COPY ucs-school-lib ./ucs-school-lib
COPY univention-directory-manager-modules-slim ./univention-directory-manager-modules-slim
COPY univention-lib-slim ./univention-lib-slim
COPY ucsschool-objects ./ucsschool-objects
COPY kelvin-connector ./kelvin-connector
COPY ucs-test-ucsschool-kelvin ./ucs-test-ucsschool-kelvin
# Third-party dependencies only: the workspace packages are copied as source
# (see connector-prod), so a dev setup can sync them into a running container.
# The exported requirements pin every version and hash from uv.lock, and
# --require-hashes enforces them. Only wheels are installed, so no setup
# script runs, except for python-ldap, which has no wheels (see above).
RUN uv export --frozen --package kelvin-connector --no-dev --no-emit-workspace --output-file requirements.txt \
    && uv pip install --python /usr/bin/python3 --target /app/site-packages \
        --require-hashes --only-binary :all: --no-binary python-ldap \
        --requirement requirements.txt
# The shared libraries the compiled dependencies link against (libldap,
# liblber, libsasl2, ...), minus glibc, which the CCF image has, and minus
# the libraries wheels vendor next to their modules.
RUN mkdir -p /app/lib \
    && find /app/site-packages -name "*.so" -exec ldd {} + \
        | awk '$2 == "=>" && $3 ~ /^\// {print $3}' | sort -u \
        | grep -v '^/app/' \
        | grep -vE '/(libc|libm|libpthread|libdl|librt|ld-linux-x86-64)\.so' \
        | xargs -I{} cp -L {} /app/lib/
# The CCF binary under the connector's name (it names itself after argv[0]);
# a symlink, as the distroless CCF image has no shell to rename it.
RUN mkdir -p /app/bin && ln -s ccf /app/bin/kelvin-connector


FROM ${CCF_BASE_IMAGE} AS connector-prod

COPY --from=connector-builder /app/site-packages /app/site-packages
COPY --from=connector-builder /app/lib /usr/lib/x86_64-linux-gnu/
COPY --from=connector-builder /app/bin/ /usr/local/bin/
COPY ucsschool-objects/src /app/ucsschool-objects/src
COPY kelvin-connector/src /app/kelvin-connector/src

# The CCF configuration that belongs to the image. The deployment provides
# the rest: PROVISIONING_HOSTNAME, PROVISIONING_NAME, PROVISIONING_PASSWORD,
# DATABASE_URL (the Kelvin DB with `options=-csearch_path=ccf`),
# UNIQUE_OWNER_ID (the host name in the App), and for the
# callback LDAP_SERVER_TYPE and the UCSSCHOOL_KELVIN_DB_* settings.
ENV PYTHON_CALLBACK=kelvin_connector.ccf_callback \
    PYTHON_CALLBACK_PATH=/app/kelvin-connector/src:/app/ucsschool-objects/src:/app/site-packages \
    CCF_TEMPLATES_DIR=/app/kelvin-connector/src/kelvin_connector/ccf_templates \
    MAX_ALLOWED_ERRORS=3

ARG app_id
ARG commit
ARG date
ARG version
ARG KELVIN_BUILD_VERSION="999.0.0"
ARG CCF_BASE_IMAGE

# The first two lines of `ccf --help` and `ccf --version`. The CCF reads them
# from the environment (a container cannot read its labels); the OCI labels
# below take them from there.
ENV CCF_TITLE="UCS@school Kelvin connector" \
    CCF_DESCRIPTION="Keeps the Kelvin DB in sync with the Nubus Provisioning events and manages its task queue." \
    CCF_VERSION="$KELVIN_BUILD_VERSION"

# The org.opencontainers.image.* labels inherited from the CCF image describe
# the CCF build; the ones that differ for this image are overwritten.
LABEL "description"="Image of the Kelvin connector of UCS app 'UCS@school Kelvin REST API' ('$app_id')." \
    "version"="$version" \
    "release date"="$date" \
    "commit"="$commit" \
    "APP_NAME"="ucsschool-kelvin-rest-api" \
    org.opencontainers.image.title="$CCF_TITLE" \
    org.opencontainers.image.description="$CCF_DESCRIPTION" \
    org.opencontainers.image.version="$CCF_VERSION" \
    org.opencontainers.image.created="$date" \
    org.opencontainers.image.revision="$commit" \
    org.opencontainers.image.source="https://git.knut.univention.de/univention/dev/education/ucsschool-kelvin-rest-api" \
    org.opencontainers.image.base.name="$CCF_BASE_IMAGE"

# The CCF image's CMD and HEALTHCHECK use the name `ccf`.
CMD ["kelvin-connector", "run"]
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s CMD ["kelvin-connector", "healthcheck"]
