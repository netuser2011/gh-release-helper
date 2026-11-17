# -*- coding: utf-8 -*-
"""测试包的入口：把项目根目录加进 sys.path，这样 `python -m unittest discover -s tests` 能 import 到各模块。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
