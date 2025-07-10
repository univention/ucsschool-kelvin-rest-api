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

EXPOSE 7890

CMD ["/sbin/init"]


# package and Python dependency installation, base system configuration,
# and uninstallation - all in one step to keep image small
COPY docker/alpine_apk_list.* kelvin-api/requirements_all.txt /tmp/
ADD $OPENAPI_CLIENT_GENERATOR_JAR_URL /tmp/
RUN apk add --no-cache --virtual mybuilddeps $(cat /tmp/alpine_apk_list.build)
RUN apk add --no-cache $(cat /tmp/alpine_apk_list.runtime)
RUN cp -v /usr/share/zoneinfo/Europe/Berlin /etc/localtime
RUN echo "Europe/Berlin" > /etc/timezone
    # Disable getty's
RUN sed -i 's/^\(tty\d\:\:\)/#\1/g' /etc/inittab
RUN sed -i \
        # Change subsystem type to "docker"
        -e 's/#rc_sys=".*"/rc_sys="docker"/g' \
        # Allow all variables through
        -e 's/#rc_env_allow=".*"/rc_env_allow="\*"/g' \
        # Start crashed services
        -e 's/#rc_crashed_stop=.*/rc_crashed_stop=NO/g' \
        -e 's/#rc_crashed_start=.*/rc_crashed_start=YES/g' \
        # Define extra dependencies for services
        -e 's/#rc_provide=".*"/rc_provide="loopback net"/g' \
        /etc/rc.conf
    # Remove unnecessary services
RUN rm -fv /etc/init.d/hwdrivers \
        /etc/init.d/hwclock \
        /etc/init.d/modules \
        /etc/init.d/modules-load \
        /etc/init.d/modloop
    # Can't do cgroups
RUN sed -i 's/\tcgroup_add_service/\t#cgroup_add_service/g' /lib/rc/sh/openrc-run.sh
RUN sed -i 's/VSERVER/DOCKER/Ig' /lib/rc/sh/init.sh
RUN mkdir -pv /kelvin/openapi-generator/build /kelvin/openapi-generator/jar
RUN mv /tmp/openapi-generator-cli-*.jar /kelvin/openapi-generator/jar
    # work around PEP 668 - Marking Python base environments as "externally managed" \
    # TODO: we should use a virtualenv
RUN rm -fv /usr/lib/python*/EXTERNALLY-MANAGED
RUN python3 -m pip install --no-cache-dir --compile --upgrade pip wheel
	# Install already, since it would fetch old versions from test.pypi.org in a later step.
RUN python3 -m pip install --no-cache-dir --compile aiohttp certifi
	# python-debian for UCR
RUN python3 -m pip install --no-cache-dir --compile python-debian
    # install dependencies of "openapi-client-udm" (next line), so they don't get pulled from test.pypi.org
RUN python3 -m pip install --no-cache-dir --compile 'urllib3>=1.25.3' 'six>=1.10' python-dateutil 'aiohttp>=3.0.0'
	# install pre-build openapi-client-udm package, not yet built against app host
RUN python3 -m pip install --no-cache-dir --compile --extra-index-url https://test.pypi.org/simple/ 'openapi-client-udm>=1.0.2'
	# install most current udm_rest_client package (instead of the one from pypi)
RUN python3 -m pip install --no-cache-dir --compile git+https://github.com/univention/python-udm-rest-api-client.git
	# install uldap3 from the GitLab registry
RUN python3 -m pip install --no-cache-dir --compile --index-url https://git.knut.univention.de/api/v4/projects/701/packages/pypi/simple "uldap3>=1.1.0"
	# install all remaining Python requirements
RUN python3 -m pip install --no-cache-dir --compile --extra-index-url https://git.knut.univention.de/api/v4/projects/701/packages/pypi/simple -r /tmp/requirements_all.txt

# install univention libraries
COPY univention-lib-slim/ /tmp/univention-lib-slim
COPY univention-directory-manager-modules-slim/ /tmp/univention-directory-manager-modules-slim
RUN ln -sv /usr/bin/univention-config-registry /usr/bin/ucr && \
    mkdir -p /etc/univention && \
	python3 -m pip install --no-cache-dir --compile /tmp/univention-lib-slim && \
	python3 -m pip install --no-cache-dir --compile /tmp/univention-directory-manager-modules-slim && \
	mkdir -p /var/cache/univention-config

# copy and install project - separate last step for fast image rebuilds
# install packages 'editable', so we can work directly on them
COPY ucs-school-lib/ /kelvin/ucs-school-lib
COPY ucs-school-import/ /kelvin/ucs-school-import
COPY docker/ucsschool-kelvin-rest-api.initd /tmp/
COPY kelvin-api/ /kelvin/kelvin-api
RUN	mv -v /tmp/ucsschool-kelvin-rest-api.initd /etc/init.d/ucsschool-kelvin-rest-api
RUN apk add --no-cache logrotate
RUN rc-update add ucsschool-kelvin-rest-api default
RUN rc-update add crond default
RUN cp -v /kelvin/ucs-school-import/modules/ucsschool/lib/create_ou.py /kelvin/ucs-school-lib/modules/ucsschool/lib/
RUN python3 -m pip install --no-cache-dir --editable /kelvin/ucs-school-lib/modules
RUN python3 -m pip install --no-cache-dir --editable /kelvin/ucs-school-import/modules
RUN cp -r /kelvin/ucs-school-import/usr/share/ucs-school-import /usr/share/
RUN cp kelvin-api/usr/share/ucs-school-import/configs/kelvin_defaults.json /usr/share/ucs-school-import/configs/
RUN 	cp kelvin-api/usr/share/ucs-school-import/checks/*.py /usr/share/ucs-school-import/checks/
RUN 	mkdir -pv /usr/share/ucs-school-import/pyhooks
RUN 	mkdir -pv /var/lib/ucs-school-import/configs
RUN 	mkdir -pv /var/lib/ucs-school-lib/kelvin-hooks
RUN for FILE in global user_import user_import_legacy user_import_http-api; do \
      if ! [ -e /var/lib/ucs-school-import/configs/${FILE}.json ]; then \
        echo '{}' > /var/lib/ucs-school-import/configs/${FILE}.json; \
      fi; \
    done
RUN 	python3 /kelvin/kelvin-api/setup.py build_html
RUN 	python3 -m pip install --no-cache-dir --editable /kelvin/kelvin-api[development]
RUN rm -rf /root/.cache/
COPY ./fix_nt_acl_on_shares /kelvin/fix_nt_acl_on_shares

ARG app_id
ARG commit
ARG date
ARG version

LABEL "description"="Image of UCS app 'UCS@school Kelvin REST API' ('$app_id')." \
    "url"="https://www.univention.com/products/univention-app-center/app-catalog/$app_id/" \
    "version"="$version" \
    "release date"="$date" \
    "commit"="$commit"
