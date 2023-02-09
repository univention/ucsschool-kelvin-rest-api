# add this dir to the Python path to allow local imports

import os
import sys

this_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(this_dir))
