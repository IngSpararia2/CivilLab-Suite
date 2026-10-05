from __future__ import annotations

from PySide6.QtWidgets import QLabel, QTextBrowser, QVBoxLayout, QWidget

STANDARDS_HTML = """
<h2>Biblioteca técnica resumida</h2>
<p><b>Importante:</b> este panel es una guía de navegación. No sustituye los documentos oficiales,
las especificaciones del proyecto ni el criterio profesional.</p>

<h3>ACI PRC-211.1-22</h3>
<p>Guía para seleccionar y ajustar proporciones de concreto de densidad normal y alta. El flujo
conceptual incluye requisitos, selección de agua y aire, relación agua/material cementante,
contenido cementante, agregados, cálculo por volúmenes absolutos y ajuste mediante mezclas de prueba.</p>

<h3>Regla de volúmenes absolutos</h3>
<p>Para cada material con masa <i>m</i> y gravedad específica <i>GE</i>, el volumen absoluto en litros
es aproximadamente <i>m / GE</i>. El aire se incorpora directamente en litros. La suma objetivo de
esta aplicación es 1000 L por metro cúbico.</p>

<h3>ASTM C33/C33M</h3>
<p>Especificación para agregados de concreto: gradación, calidad, sustancias perjudiciales y otros
requisitos. La aceptación depende de la edición contractual y de los documentos del proyecto.</p>

<h3>ASTM C150/C150M</h3>
<p>Especificación para cemento Portland. Verifica tipo de cemento, propiedades químicas y físicas,
y compatibilidad con las condiciones de exposición.</p>

<h3>ASTM C143/C143M</h3>
<p>Método de ensayo de asentamiento del concreto hidráulico. Se usa para evaluar consistencia en
condiciones definidas; no representa por sí solo la totalidad de la trabajabilidad.</p>

<h3>ASTM C494/C494M</h3>
<p>Especificación para aditivos químicos. La reducción de agua, retardo, aceleración y desempeño
deben comprobarse con materiales reales y mezclas de prueba.</p>

<h3>Corrección por humedad</h3>
<p>Concretos Lab interpreta los agregados de diseño en condición SSD. Convierte a masa seca al horno,
aplica la humedad total para obtener masa húmeda de carga y ajusta el agua por la diferencia
entre humedad y absorción.</p>

<h3>Secuencia recomendada de validación</h3>
<ol>
<li>Confirmar edición normativa y requisitos contractuales.</li>
<li>Caracterizar materiales reales y registrar gravedad específica, absorción y humedad.</li>
<li>Generar proporciones iniciales.</li>
<li>Preparar mezcla de prueba y medir asentamiento, aire, densidad y rendimiento.</li>
<li>Ajustar proporciones conservando el rendimiento volumétrico.</li>
<li>Moldear especímenes y verificar resistencia y durabilidad.</li>
</ol>
"""


class StandardsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        title = QLabel("Biblioteca de normativas")
        title.setObjectName("Title")
        browser = QTextBrowser()
        browser.setHtml(STANDARDS_HTML)
        browser.setOpenExternalLinks(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.addWidget(title)
        layout.addWidget(browser, 1)
