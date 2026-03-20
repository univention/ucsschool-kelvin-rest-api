import re
import sys
from argparse import ArgumentParser
from pathlib import Path

import ucsschool_objects.database_models
from eralchemy import render_er

parser = ArgumentParser()
parser.add_argument("filepath")

args = parser.parse_args()

path = Path(args.filepath)

if not path.parent.exists():
    print(f"Directory {path.parent} does not exist")
    sys.exit(1)

render_er(ucsschool_objects.database_models.Base, str(path.absolute()))

with open(path, "r") as f:
    match = re.search(r"<!--(.*?)-->", f.read(), re.DOTALL)
    if match is None:
        print(f"Unexpected format of file {path}")
        sys.exit(1)
    out = match.group(1).strip()

with open(path, "w") as f:
    f.write(out)
