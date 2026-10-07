"""Descarga los modelos del backend pipeline a servicio-mineru/modelos/ sin enlaces simbólicos.

En Windows sin modo desarrollador, la caché de HuggingFace falla al crear symlinks
(WinError 1314). Con local_dir los archivos se copian. Escribe mineru.json con la ruta y el
servicio arranca con MINERU_MODEL_SOURCE=local y MINERU_TOOLS_CONFIG_JSON=<este>/mineru.json.
"""

import json
from pathlib import Path

from huggingface_hub import snapshot_download
from mineru.utils.enum_class import ModelPath

AQUI = Path(__file__).resolve().parent
DESTINO = AQUI / "modelos" / "pipeline"
RUTAS = [ModelPath.pp_doclayout_v2, ModelPath.unimernet_small, ModelPath.pytorch_paddle, ModelPath.slanet_plus,
         ModelPath.unet_structure, ModelPath.paddle_table_cls, ModelPath.pp_formulanet_plus_m]


def main() -> None:
    patrones = []
    for r in RUTAS:
        r = str(r).strip("/")
        patrones += [r, r + "/*", r + "/**"]
    snapshot_download(ModelPath.pipeline_root_hf, local_dir=DESTINO, allow_patterns=patrones)
    config = {"models-dir": {"pipeline": str(DESTINO)}, "model-source": "local"}
    (AQUI / "mineru.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    print("Modelos en", DESTINO)


if __name__ == "__main__":
    main()
