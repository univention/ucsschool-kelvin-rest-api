# Copyright 2020-2023 Univention GmbH
#
# http://www.univention.de/
#
# All rights reserved.
#
# The source code of this program is made available
# under the terms of the GNU Affero General Public License version 3
# (GNU AGPL V3) as published by the Free Software Foundation.
#
# Binary versions of this program provided by Univention to you as
# well as other copyrighted, protected or trademarked materials like
# Logos, graphics, fonts, specific documentations and configurations,
# cryptographic keys etc. are subject to a license agreement between
# you and Univention and not subject to the GNU AGPL V3.
#
# In the case you use this program under the terms of the GNU AGPL V3,
# the program is provided in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License with the Debian GNU/Linux or Univention distribution in file
# /usr/share/common-licenses/AGPL-3; if not, see
# <http://www.gnu.org/licenses/>.

FROM gitregistry.knut.univention.de/univention/dev/projects/ucs-base-image/ucs-base-python:5.2.3-build.20251016 AS base

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
COPY openapi-client-udm-1.0.2.tar.gz .

RUN uv sync --locked


FROM base AS prod

RUN apt-get install -y libldap-2.5-0 openjdk-17-jre-headless
RUN mkdir -pv /etc/univention/
RUN mkdir -pv /var/lib/ucs-school-import/kelvin-hooks
RUN mkdir -pv /var/cache/univention-config/
COPY --from=builder $VIRTUAL_ENV $VIRTUAL_ENV
COPY uv.lock .
COPY pyproject.toml .
COPY docker/start-kelvin.sh .
COPY kelvin-api ./kelvin-api
COPY ucs-school-import ./ucs-school-import
COPY ucs-school-lib ./ucs-school-lib
COPY univention-directory-manager-modules-slim ./univention-directory-manager-modules-slim
COPY univention-lib-slim ./univention-lib-slim
COPY openapi-client-udm-1.0.2.tar.gz .
COPY ucs-school-import/usr/share/ucs-school-import/configs/ /usr/share/ucs-school-import/configs/
COPY ucs-school-import/modules/ucsschool/lib/create_ou.py ucs-school-lib/modules/ucsschool/lib/create_ou.py
COPY kelvin-api/usr/share/ucs-school-import/checks/*.py /usr/share/ucs-school-import/checks/
COPY kelvin-api/empty_configs /var/lib/ucs-school-import/configs
COPY kelvin-api/usr/share/ucs-school-import/configs/kelvin_defaults.json /usr/share/ucs-school-import/configs/


ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENTRYPOINT ["/kelvin/start-kelvin.sh"]
VOLUME /var/log
VOLUME /etc/univention
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
