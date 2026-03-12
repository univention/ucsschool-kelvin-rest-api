import json

from univention.config_registry import ConfigRegistry
from univention.udm import UDM
from univention.udm.binary_props import Base64Bzip2BinaryProperty
from univention.udm.exceptions import NoObject

ucr = ConfigRegistry().load()
fqdn = f'{ucr.get("hostname")}.{ucr.get("domainname")}'
ldap_base = ucr.get("ldap/base")
mod = UDM.admin().version(2).get("settings/data")
app_name = "ucsschool-kelvin-rest-api"

try:
    obj = mod.get(f"cn={app_name},cn=data,cn=univention,{ldap_base}")

    data = json.loads(obj.props.data.raw)
    data["installations"].remove(fqdn)
    if data["installations"]:
        raw_value = json.dumps(data).encode("ascii")
        obj.props.data = Base64Bzip2BinaryProperty("data", raw_value=raw_value)
        obj.save()
    else:
        obj.delete()
except NoObject:
    pass
