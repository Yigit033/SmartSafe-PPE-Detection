"""SmartSafe core package.

This file exists to make `core.*` imports work reliably across environments
(local runs, Docker, and production process managers).
"""

import os
import sys
from pathlib import Path

# Proje kök dizinini sys.path'e ekle (importların çalışması için)
CORE_DIR = Path(__file__).parent.absolute()
if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

# Sabitleri (Constants) yükle ve os.environ'a enjekte et
try:
    from configs import constants
    for key, value in constants.__dict__.items():
        if key.isupper() and not key.startswith("_"):
            # Eğer .env içinde tanımlanmamışsa (os.environ), constants.py'daki değeri kullan
            if key not in os.environ:
                # String'e çevir çünkü os.environ sadece string kabul eder
                os.environ[key] = str(value)
except ImportError:
    pass
