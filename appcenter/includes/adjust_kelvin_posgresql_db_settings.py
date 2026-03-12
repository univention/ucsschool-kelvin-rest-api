import json

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

kelvin_db_uri = None
kelvin_db_username = None
kelvin_db_password_file = None

app = Apps().find("ucsschool-kelvin-rest-api")

for setting in app.get_settings():
    if setting.name == "ucsschool/kelvin/db/uri":
        kelvin_db_uri = setting.get_value(app)
    if setting.name == "ucsschool/kelvin/db/username":
        kelvin_db_username = setting.get_value(app)

try:
    obj = mod.get(f"cn={app_name},cn=data,{superordinate}")
    data = json.loads(obj.props.data.raw)

    if len(data["installations"]) == 1:
        data["database-uri"] = kelvin_db_uri or data["database-uri"]
        data["database-user"] = kelvin_db_username or data["database-user"]
        raw_value = json.dumps(data).encode("ascii")
        obj.props.data = Base64Bzip2BinaryProperty("data", raw_value=raw_value)
        obj.save()

except NoObject:
    pass
