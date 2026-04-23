# -*- coding: utf8 -*-
from pathlib import Path
import os

HOME = str(Path.home())

API_URL_BASE = os.environ['API_URL']

USERDATA_PATH = HOME + "/.dataspine/userdata"
PUBLIC_KEY_PATH = HOME + "/.dataspine/public-key"
KUBE_CONFIG_PATH = HOME + '/.kube/config'

