# CivilLab Suite

Aplicación de escritorio que integra **Concretos Lab**, **Prefabricados Lab** y el espacio futuro de **Suelos Lab** dentro de un solo proceso Qt.

## Ejecutar

En Windows, use `run_windows.bat`. Desde un entorno ya instalado:

```powershell
python app.py
```

La ventana inicial permite abrir Concretos o Prefabricados y regresar a la suite desde el menú **Archivo > Volver a CivilLab Suite**. Suelos se muestra como próximamente y no contiene lógica geotécnica.

## Persistencia

- Concretos conserva su ruta histórica en `%LOCALAPPDATA%\ConcreteMixDesignerACI\materials.sqlite3` para no ocultar instalaciones existentes.
- Prefabricados usa `%LOCALAPPDATA%\CivilLabSuite\prefabricados\precon_lab.db` dentro de la suite. En la primera ejecución copia, sin sobrescribir, una base histórica detectada.
- El catálogo compartido se guarda en `%LOCALAPPDATA%\CivilLabSuite\core.sqlite3`. Sus migraciones son idempotentes y no eliminan las tablas de los módulos.

Para pruebas aisladas se pueden definir `CIVILLAB_SUITE_DATA_DIR` y `PRECON_LAB_DATA_DIR`.

## Pruebas

```powershell
python -m pytest
```
