"""Crea el ícono del extractor y el acceso directo "Extractor de matriz" en el Escritorio.

El acceso directo ejecuta Extractor.vbs, que lanza Extractor.ps1 sin mostrar consola.
Uso (con un Python que tenga Pillow, por ejemplo el de servicio-mineru):
    servicio-mineru/.venv/Scripts/python herramientas/crear_icono_y_acceso.py
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

RAIZ = Path(__file__).resolve().parents[1]
ICONO = RAIZ / "recursos" / "extractor.ico"
VBS = RAIZ / "Extractor.vbs"


def dibujar(lado: int = 256) -> Image.Image:
    """Cuadro redondeado azul (degradado) con una tabla blanca, al estilo de un ícono de app."""
    img = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    fondo = Image.new("RGBA", (lado, lado))
    d = ImageDraw.Draw(fondo)
    for y in range(lado):  # degradado vertical #3a8dff → #0058d6
        t = y / lado
        d.line([(0, y), (lado, y)], fill=(int(58 + (0 - 58) * t), int(141 + (88 - 141) * t), int(255 + (214 - 255) * t)))
    mascara = Image.new("L", (lado, lado), 0)
    ImageDraw.Draw(mascara).rounded_rectangle([0, 0, lado - 1, lado - 1], radius=int(lado * 0.225), fill=255)
    img.paste(fondo, (0, 0), mascara)

    d = ImageDraw.Draw(img)
    m, g = int(lado * 0.22), max(2, int(lado * 0.045))
    x0, y0, x1, y1 = m, int(lado * 0.26), lado - m, lado - int(lado * 0.26)
    blanco = (255, 255, 255, 255)
    d.rounded_rectangle([x0, y0, x1, y1], radius=int(lado * 0.05), outline=blanco, width=g)
    d.rectangle([x0, y0, x1, y0 + int((y1 - y0) * 0.28)], fill=blanco)  # fila de encabezado
    for f in (0.62,):
        y = y0 + int((y1 - y0) * f)
        d.line([(x0, y), (x1, y)], fill=blanco, width=g)
    x = x0 + int((x1 - x0) * 0.36)
    d.line([(x, y0), (x, y1)], fill=blanco, width=g)
    # marca de resaltado: la celda con evidencia
    d.rounded_rectangle([x + g, y0 + int((y1 - y0) * 0.36), x1 - g * 2, y0 + int((y1 - y0) * 0.56)],
                        radius=g, fill=(255, 214, 10, 255))
    return img


def main() -> None:
    ICONO.parent.mkdir(parents=True, exist_ok=True)
    dibujar().save(ICONO, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    ps1 = RAIZ / "Extractor.ps1"
    VBS.write_text(
        "' Lanza Extractor.ps1 sin ventana de consola.\r\n"
        'CreateObject("WScript.Shell").Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden '
        f'-File ""{ps1}""", 0, False\r\n',
        encoding="utf-8",
    )
    script = f"""
$escritorio = [Environment]::GetFolderPath('Desktop')
$s = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $escritorio 'Extractor de matriz.lnk'))
$s.TargetPath = "$env:SystemRoot\\System32\\wscript.exe"
$s.Arguments = '"{VBS}"'
$s.WorkingDirectory = '{RAIZ}'
$s.IconLocation = '{ICONO},0'
$s.Description = 'Abre el Extractor de matriz; al cerrar la ventana se apaga'
$s.Save()
Write-Output (Join-Path $escritorio 'Extractor de matriz.lnk')
"""
    r = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True)
    print(r.stdout.strip() or r.stderr.strip())
    print(f"Ícono: {ICONO}")


if __name__ == "__main__":
    main()
