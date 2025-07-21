#!/usr/bin/env ash

set -e

# shellcheck disable=SC2046
apk add --no-cache --virtual mybuilddeps $(cat /tmp/alpine_apk_list.build)
# shellcheck disable=SC2046
apk add --no-cache $(cat /tmp/alpine_apk_list.runtime)
cp -v /usr/share/zoneinfo/Europe/Berlin /etc/localtime
echo "Europe/Berlin" > /etc/timezone
# Disable getty's
sed -i 's/^\(tty\d\:\:\)/#\1/g' /etc/inittab

# Change subsystem type to "docker"
# Allow all variables through
# Start crashed services
# Define extra dependencies for services
sed -i \
    -e 's/#rc_sys=".*"/rc_sys="docker"/g' \
    -e 's/#rc_env_allow=".*"/rc_env_allow="\*"/g' \
    -e 's/#rc_crashed_stop=.*/rc_crashed_stop=NO/g' \
    -e 's/#rc_crashed_start=.*/rc_crashed_start=YES/g' \
    -e 's/#rc_provide=".*"/rc_provide="loopback net"/g' \
    /etc/rc.conf
# Remove unnecessary services
rm -fv /etc/init.d/hwdrivers \
    /etc/init.d/hwclock \
    /etc/init.d/modules \
    /etc/init.d/modules-load \
    /etc/init.d/modloop
# Can't do cgroups
sed -i 's/\tcgroup_add_service/\t#cgroup_add_service/g' /lib/rc/sh/openrc-run.sh
sed -i 's/VSERVER/DOCKER/Ig' /lib/rc/sh/init.sh
mkdir -pv /kelvin/openapi-generator/build /kelvin/openapi-generator/jar
mv /tmp/openapi-generator-cli-*.jar /kelvin/openapi-generator/jar
# work around PEP 668 - Marking Python base environments as "externally managed" \
# TODO: we should use a virtualenv
rm -fv /usr/lib/python*/EXTERNALLY-MANAGED
python3 -m pip install --no-cache-dir --compile --upgrade pip wheel
# Install already, since it would fetch old versions from test.pypi.org in a later step.
python3 -m pip install --no-cache-dir --compile aiohttp certifi
# python-debian for UCR
python3 -m pip install --no-cache-dir --compile python-debian
# install dependencies of "openapi-client-udm" (next line), so they don't get pulled from test.pypi.org
python3 -m pip install --no-cache-dir --compile 'urllib3>=1.25.3' 'six>=1.10' python-dateutil 'aiohttp>=3.0.0'
# install pre-build openapi-client-udm package, not yet built against app host
python3 -m pip install --no-cache-dir --compile --extra-index-url https://test.pypi.org/simple/ 'openapi-client-udm>=1.0.2'
# install most current udm_rest_client package (instead of the one from pypi)
python3 -m pip install --no-cache-dir --compile git+https://github.com/univention/python-udm-rest-api-client.git
# install uldap3 from the GitLab registry
python3 -m pip install --no-cache-dir --compile --index-url https://git.knut.univention.de/api/v4/projects/701/packages/pypi/simple "uldap3>=1.1.0"
# install all remaining Python requirements
python3 -m pip install --no-cache-dir --compile --extra-index-url https://git.knut.univention.de/api/v4/projects/701/packages/pypi/simple -r /tmp/requirements_all.txt

ln -sv /usr/bin/univention-config-registry /usr/bin/ucr
mkdir -p /etc/univention
python3 -m pip install --no-cache-dir --compile /tmp/univention-lib-slim
python3 -m pip install --no-cache-dir --compile /tmp/univention-directory-manager-modules-slim
mkdir -p /var/cache/univention-config

mv -v /tmp/ucsschool-kelvin-rest-api.initd /etc/init.d/ucsschool-kelvin-rest-api
apk add --no-cache logrotate
rc-update add ucsschool-kelvin-rest-api default
rc-update add crond default
cp -v /kelvin/ucs-school-import/modules/ucsschool/lib/create_ou.py /kelvin/ucs-school-lib/modules/ucsschool/lib/
python3 -m pip install --no-cache-dir --editable /kelvin/ucs-school-lib/modules
python3 -m pip install --no-cache-dir --editable /kelvin/ucs-school-import/modules
cp -r /kelvin/ucs-school-import/usr/share/ucs-school-import /usr/share/
cp kelvin-api/usr/share/ucs-school-import/configs/kelvin_defaults.json /usr/share/ucs-school-import/configs/
cp kelvin-api/usr/share/ucs-school-import/checks/*.py /usr/share/ucs-school-import/checks/
mkdir -pv /usr/share/ucs-school-import/pyhooks
mkdir -pv /var/lib/ucs-school-import/configs
mkdir -pv /var/lib/ucs-school-lib/kelvin-hooks
for FILE in global user_import user_import_legacy user_import_http-api; do
  if ! [ -e /var/lib/ucs-school-import/configs/${FILE}.json ]; then
    echo '{}' > /var/lib/ucs-school-import/configs/${FILE}.json;
  fi;
done
python3 /kelvin/kelvin-api/setup.py build_html
python3 -m pip install --no-cache-dir --editable "/kelvin/kelvin-api[development]"
rm -rf /root/.cache/
