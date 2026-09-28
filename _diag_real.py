import sys, io, time
sys.path.insert(0, 'src')
from pathlib import Path
from webapp.drive_reader import DriveReader, _IMGS_DIR
import webapp.drive_reader as dmod

URL = "https://drive.google.com/file/d/1pYSB3ndAFlY-StqGkfx2lNP43cUWK-Ar/view"
DOC = "1pYSB3ndAFlY-StqGkfx2lNP43cUWK-Ar"

# Limpiar imágenes previas del doc para medir desde cero
import shutil
dd = _IMGS_DIR / DOC
if dd.is_dir():
    shutil.rmtree(dd, ignore_errors=True)
    print("limpie imágenes previas")

import tempfile
tmp = Path(tempfile.mkdtemp(prefix="drtest_"))
rdr = DriveReader(cache_dir=tmp)

t0 = time.monotonic()
txt = rdr.download_and_extract(URL, timeout=10.0, enable_ocr=True)
dt = time.monotonic() - t0
print("--- RESULTADO ---")
print("tiempo (s):", round(dt, 2))
print("len texto:", len(txt or ""))
print("tiene sección OCR:", "DATOS EXTRA" in (txt or ""))
marcas = dmod.IMAGE_MARKER_RE.findall(txt or "")
print("marcas IMG:", len(marcas))
for m in marcas[:5]:
    print("   img:", m)

# Ver imágenes guardadas
dd = _IMGS_DIR / DOC
files = sorted(dd.glob("*")) if dd.is_dir() else []
print("imágenes en disco:", len(files), [f.name for f in files])

# Buscar dato esperado en el texto extraído
for kw in ["plastilina", "-1,7", "jun", "may", "DANE", "EMC"]:
    print(f"  contiene {kw!r}:", (kw.lower() in (txt or "").lower()))

print("--- rev/done ---")
shutil.rmtree(tmp, ignore_errors=True)