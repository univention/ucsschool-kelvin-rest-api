import json
import os
import sys
from urllib.parse import urlparse

from univention.appcenter.app_cache import Apps
from univention.config_registry import ConfigRegistry
from univention.udm import UDM
from univention.udm.binary_props import Base64Bzip2BinaryProperty
from univention.udm.exceptions import NoObject

ucr = ConfigRegistry().load()
fqdn = f'{ucr.get("hostname")}.{ucr.get("domainname")}'
ldap_base = ucr.get("ldap/base")
superordinate = f"cn=univention,{ldap_base}"
app_name = "ucsschool-kelvin-rest-api"
mod = UDM.admin().version(2).get("settings/data")
with open("/etc/postgresql-kelvin.secret", "r") as fd:
    default_password = fd.read().strip()


default_url = f"postgresql://{fqdn}:5432/ucsschool-kelvin-rest-api?sslmode=require"
kelvin_db_uri = None
kelvin_db_username = None
kelvin_db_password_file = None

app = Apps().find("ucsschool-kelvin-rest-api")
for setting in app.get_settings():
    if setting.name == "ucsschool/kelvin/db/uri":
        kelvin_db_uri = setting.get_value(app)
    if setting.name == "ucsschool/kelvin/db/username":
        kelvin_db_username = setting.get_value(app)
    if setting.name == "ucsschool/kelvin/db/password":
        kelvin_db_password_file = setting.filename
        if not os.path.exists(kelvin_db_password_file):
            with open(kelvin_db_password_file, "w") as f:
                f.write(default_password)

try:
    obj = mod.get(f"cn={app_name},cn=data,{superordinate}")

    data = json.loads(obj.props.data.raw)

    kelvin_db_uri = data["database-uri"] or kelvin_db_uri
    kelvin_db_username = data["database-user"] or kelvin_db_username
    kelvin_db_password_host = data["database-password-host"] or fqdn
    kelvin_db_password_file = data["database-password-path"] or kelvin_db_password_file
    if fqdn not in data["installations"]:
        data["installations"].append(fqdn)

except NoObject:
    kelvin_db_uri = kelvin_db_uri or default_url
    kelvin_db_password_host = fqdn
    kelvin_db_username = kelvin_db_username or app_name
    cfg = urlparse(kelvin_db_uri)
    obj = mod.new(superordinate)
    obj.position = f"cn=data,{superordinate}"
    obj.props.name = app_name
    obj.props.data_type = "string"
    data = {
        "database-uri": kelvin_db_uri,
        "database-user": kelvin_db_username,
        "database-password-host": kelvin_db_password_host,
        "database-password-path": kelvin_db_password_file,
        "installations": [fqdn],
    }

if kelvin_db_uri is None:
    print(f"ERROR: {kelvin_db_uri=} could not be determined.", file=sys.stderr)
if kelvin_db_username is None:
    print(f"ERROR: {kelvin_db_username=} could not be determined.", file=sys.stderr)
if kelvin_db_password_host is None:
    print(f"ERROR: {kelvin_db_password_host=} could not be determined", file=sys.stderr)
if kelvin_db_password_file is None:
    print(f"ERROR: {kelvin_db_password_file=} could not be determined", file=sys.stderr)

raw_value = json.dumps(data).encode("ascii")
obj.props.data = Base64Bzip2BinaryProperty("data", raw_value=raw_value)
obj.save()

print(kelvin_db_uri)
print(kelvin_db_username)
print(kelvin_db_password_host)
print(kelvin_db_password_file)
