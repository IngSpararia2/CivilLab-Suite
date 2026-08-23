RECURSOS DE MARCA DE CONCRETOS LAB

- brand_source.png conserva la imagen original proporcionada para la aplicación.
- app_icon.png es la versión recortada usada en la cabecera de la interfaz.
- app_icon.ico contiene tamaños 16, 24, 32, 48, 64, 128 y 256 px para Windows.

Para regenerar ambos iconos desde la fuente, instala requirements-dev.txt y
ejecuta desde la raíz del repositorio:

   python tools\generate_app_icons.py "ruta\a\Concretos Lab.png" --crop 152,144,880,872

El recorte elimina el margen exterior de la imagen original de 1024 x 1024 px
y mantiene completo el emblema. Si se reemplaza la imagen por otra composición,
omite --crop o ajusta sus coordenadas.

build_windows.bat usa tools\pysidedeploy.spec.template para incorporar los
dos iconos necesarios y aplicar app_icon.ico al ejecutable.
