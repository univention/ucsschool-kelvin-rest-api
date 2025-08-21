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

# TODO: set to specific alpine version (>=3.18?) that includes Python 3.11 or migarte to Debian image
ARG DOCKER_PROXY

FROM ${DOCKER_PROXY}alpine:3.18.9

ARG OPENAPI_CLIENT_GENERATOR_VERSION="5.4.0"
ARG OPENAPI_CLIENT_GENERATOR_JAR="openapi-generator-cli-$OPENAPI_CLIENT_GENERATOR_VERSION.jar"
ARG OPENAPI_CLIENT_GENERATOR_JAR_URL="https://repo1.maven.org/maven2/org/openapitools/openapi-generator-cli/$OPENAPI_CLIENT_GENERATOR_VERSION/$OPENAPI_CLIENT_GENERATOR_JAR"

VOLUME /var/log

WORKDIR /kelvin

EXPOSE 8911

CMD ["/kelvin/start-kelvin.sh"]


# package and Python dependency installation, base system configuration,
# and uninstallation - all in one step to keep image small
COPY docker/build.sh /tmp/
COPY docker/alpine_apk_list.* kelvin-api/requirements_all.txt /tmp/
ADD $OPENAPI_CLIENT_GENERATOR_JAR_URL /tmp/

# install univention libraries
COPY univention-lib-slim/ /tmp/univention-lib-slim
COPY univention-directory-manager-modules-slim/ /tmp/univention-directory-manager-modules-slim

# copy and install project - separate last step for fast image rebuilds
# install packages 'editable', so we can work directly on them
COPY ucs-school-lib/ /kelvin/ucs-school-lib
COPY ucs-school-import/ /kelvin/ucs-school-import
COPY docker/start-kelvin.sh /kelvin/
COPY kelvin-api/ /kelvin/kelvin-api
COPY ./fix_nt_acl_on_shares /kelvin/fix_nt_acl_on_shares

RUN /tmp/build.sh

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
