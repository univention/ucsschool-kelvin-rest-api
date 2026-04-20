import os
import sys
import time


def connector():
    LDAP_SERVER_TYPE = os.environ.get("LDAP_SERVER_TYPE", None)
    if LDAP_SERVER_TYPE is None:
        print(f"Connector cannot run on {LDAP_SERVER_TYPE=}.")
        sys.exit(1)

    while True:
        time.sleep(2)
        print("Hello from kelvin-connector!")
