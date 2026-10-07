"""norm(): idéntica a la de recursos/validar_extraccion.py.

La prueba tests/unitarias/test_normalizacion.py compara ambas sobre 50 cadenas.
Si el validador cambia su norm(), esta debe cambiar igual.
"""

import re
import unicodedata


def norm(t: str) -> str:
    t = unicodedata.normalize("NFKC", t)
    t = t.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    t = t.replace("–", "-").replace("—", "-").replace("-\n", "")
    return re.sub(r"\s+", " ", t).strip().lower()
