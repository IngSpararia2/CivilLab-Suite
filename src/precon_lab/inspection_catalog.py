"""Catálogo maestro y reconciliación idempotente del Plan de Inspección."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .models import InspectionPlanEntry, LaboratoryTest, MaterialType, StandardReference, TestApplicability, TestRequirement

VERIFIED_ATTACHED = "VERIFIED_ATTACHED"
PUBLIC_OFFICIAL_DERIVED = "PUBLIC_OFFICIAL_DERIVED"
SECONDARY_REFERENCE = "SECONDARY_REFERENCE"
PENDING_VERIFICATION = "PENDING_VERIFICATION"
INVIAS_2022_SOURCE = "Especificaciones Generales de Construcción de Carreteras 2022, INVÍAS, Resolución 4561 de 2022"

MATERIALS = (
    ("SLAB_FLOOR", "Losas para pisos"), ("PAVER_CONCRETE", "Adoquines de concreto"),
    ("BLOCK_STRUCTURAL", "Bloques estructurales"), ("BLOCK_NON_STRUCTURAL", "Bloques no estructurales"),
    ("GRANULAR_BASE", "Base Granular"), ("GRANULAR_SUBBASE", "Subbase Granular"),
    ("COARSE_AGGREGATE", "Agregado Grueso"), ("FINE_AGGREGATE", "Agregado Fino"),
    ("CEMENT", "Cemento"), ("GRASS_PAVER", "Gramoquines"), ("OTHER", "Otros"),
)

STANDARDS = (
    ("INV-ART-320", "Artículo 320 - Subbase granular", "INVIAS", "2022", INVIAS_2022_SOURCE, "Tablas 320-2 a 320-4", PUBLIC_OFFICIAL_DERIVED),
    ("INV-ART-330", "Artículo 330 - Base granular", "INVIAS", "2022", INVIAS_2022_SOURCE, "Tablas 330-2 a 330-4", PUBLIC_OFFICIAL_DERIVED),
    ("INV-ART-500", "Artículo 500 - Agregados para concreto (referencia histórica)", "INVIAS", "2013", "CAPÍTULO 5_1.pdf", "Tabla 500-2", VERIFIED_ATTACHED),
    ("INV-ART-501", "Artículo 501 - Cemento hidráulico", "INVIAS", "2013", "CAPÍTULO 5_1.pdf", "Tabla 501-1", VERIFIED_ATTACHED),
    ("INV-ART-505", "Artículo 505 - Agregado grueso para concreto (referencia histórica)", "INVIAS", "2013", "CAPÍTULO 5_1.pdf", "Tabla 505-2", VERIFIED_ATTACHED),
    ("INV-ART-510", "Artículo 510 - Adoquines de concreto (referencia histórica)", "INVIAS", "2013", "CAPÍTULO 5_1.pdf", "Tabla 510-1", VERIFIED_ATTACHED),
    ("INV-E-123", "INV E-123 - Tamaños de partículas (referencia histórica)", "INVIAS", "2013", "SECCIÓN 100 mod_2013-NOV-15.pdf", "", VERIFIED_ATTACHED),
    ("INV-E-125", "INV E-125 - Límite líquido", "INVIAS", "2013", "SECCIÓN 100 mod_2013-NOV-15.pdf", "", VERIFIED_ATTACHED),
    ("INV-E-126", "INV E-126 - Límite plástico e índice de plasticidad", "INVIAS", "2013", "SECCIÓN 100 mod_2013-NOV-15.pdf", "", VERIFIED_ATTACHED),
    ("INV-E-133", "INV E-133 - Equivalente de arena", "INVIAS", "2013", "SECCIÓN 100 mod_2013-NOV-15.pdf", "", VERIFIED_ATTACHED),
    ("INV-E-142", "INV E-142 - Compactación modificada", "INVIAS", "2013", "SECCIÓN 100 mod_2013-NOV-15.pdf", "", VERIFIED_ATTACHED),
    ("INV-E-148", "INV E-148 - CBR de laboratorio", "INVIAS", "2013", "SECCIÓN 100 mod_2013-NOV-15.pdf", "", VERIFIED_ATTACHED),
    ("INV-E-211", "INV E-211 - Terrones de arcilla y partículas deleznables", "INVIAS", "2013", "SECCIÓN 200 mod_2013-NOV-15.pdf", "", VERIFIED_ATTACHED),
    ("INV-E-213", "INV E-213 - Análisis granulométrico de agregados gruesos y finos", "INVIAS", "2013", "SECCIÓN 200 mod_2013-NOV-15.pdf", "", VERIFIED_ATTACHED),
    ("INV-E-218", "INV E-218 - Desgaste Los Ángeles", "INVIAS", "2013", "SECCIÓN 200 mod_2013-NOV-15.pdf", "", VERIFIED_ATTACHED),
    ("INV-E-220", "INV E-220 - Solidez en sulfatos", "INVIAS", "2013", "SECCIÓN 200 mod_2013-NOV-15.pdf", "", VERIFIED_ATTACHED),
    ("INV-E-224", "INV E-224 - Valor del 10 % de finos", "INVIAS", "2013", "SECCIÓN 200 mod_2013-NOV-15.pdf", "", VERIFIED_ATTACHED),
    ("INV-E-227", "INV E-227 - Partículas fracturadas", "INVIAS", "2013", "SECCIÓN 200 mod_2013-NOV-15.pdf", "", VERIFIED_ATTACHED),
    ("INV-E-230", "INV E-230 - Índices de aplanamiento y alargamiento", "INVIAS", "2013", "SECCIÓN 200 mod_2013-NOV-15.pdf", "", VERIFIED_ATTACHED),
    ("INV-E-235", "INV E-235 - Azul de metileno", "INVIAS", "2013", "SECCIÓN 200 mod_2013-NOV-15.pdf", "", VERIFIED_ATTACHED),
    ("INV-E-238", "INV E-238 - Micro-Deval", "INVIAS", "2013", "SECCIÓN 200 mod_2013-NOV-15.pdf", "", VERIFIED_ATTACHED),
    ("INV-E-239", "INV E-239 - Angularidad de agregado fino", "INVIAS", "2013", "SECCIÓN 200 mod_2013-NOV-15.pdf", "", VERIFIED_ATTACHED),
    ("INV-E-425", "INV E-425 - Abrasión por chorro de arena (referencia histórica)", "INVIAS", "2013", "CAPÍTULO 5_1.pdf", "Artículo 510", VERIFIED_ATTACHED),
    ("INV-E-426", "INV E-426 - Resistencia a compresión de adoquines (referencia histórica)", "INVIAS", "2013", "CAPÍTULO 5_1.pdf", "Tabla 510-1", VERIFIED_ATTACHED),
    ("INV-E-427", "INV E-427 - Absorción de adoquines (referencia histórica)", "INVIAS", "2013", "CAPÍTULO 5_1.pdf", "Tabla 510-1", VERIFIED_ATTACHED),
    ("NTC-77", "NTC 77 - Análisis granulométrico de agregados", "ICONTEC", "2018", "Copia licenciada no disponible", "", PENDING_VERIFICATION),
    ("NTC-78", "NTC 78 - Material que pasa tamiz 75 µm por lavado", "ICONTEC", "2019", "Copia licenciada no disponible", "", PENDING_VERIFICATION),
    ("NTC-93", "NTC 93 - Desgaste Los Ángeles para agregado grueso", "ICONTEC", "2022", "Copia licenciada no disponible", "", PENDING_VERIFICATION),
    ("NTC-98", "NTC 98 - Desgaste Los Ángeles para agregado grueso", "ICONTEC", "2019", "Copia licenciada no disponible", "", PENDING_VERIFICATION),
    ("NTC-126", "NTC 126 - Solidez de agregados mediante sulfatos", "ICONTEC", "", "Copia licenciada no disponible", "", PENDING_VERIFICATION),
    ("NTC-127", "NTC 127 - Impurezas orgánicas en arenas", "ICONTEC", "2024", "Copia licenciada no disponible", "", PENDING_VERIFICATION),
    ("NTC-174", "NTC 174 - Agregados para concreto", "ICONTEC", "2018", "Copia licenciada no disponible", "Especificación de aceptación", PENDING_VERIFICATION),
    ("NTC-589", "NTC 589 - Terrones de arcilla y partículas deleznables", "ICONTEC", "2024", "Copia licenciada no disponible", "", PENDING_VERIFICATION),
    ("NTC-2017", "NTC 2017 - Adoquines de concreto para pavimentos", "ICONTEC", "2018", "Referencias públicas de laboratorios", "", SECONDARY_REFERENCE),
    ("NTC-5147", "NTC 5147 - Abrasión de adoquines de concreto", "ICONTEC", "2024", "Copia licenciada no disponible", "", PENDING_VERIFICATION),
    ("NTC-4992", "NTC 4992 - Losetas de concreto para pavimentos", "ICONTEC", "", "Especificación pública del IDU", "", PUBLIC_OFFICIAL_DERIVED),
    ("NTC-4993", "NTC 4993 - Tabletas de concreto para pisos", "ICONTEC", "", "Referencia pública", "", PENDING_VERIFICATION),
    ("NTC-4024", "NTC 4024 - Métodos de ensayo para unidades de mampostería de concreto", "ICONTEC", "", "Referencia normativa indicada; edición por verificar", "Compresión, absorción y densidad", PENDING_VERIFICATION),
    ("NTC-4026", "NTC 4026 - Bloques de concreto estructurales", "ICONTEC", "", "Fuentes públicas secundarias", "", SECONDARY_REFERENCE),
    ("NTC-4076", "NTC 4076 - Bloques de concreto no estructurales", "ICONTEC", "", "Fuentes públicas secundarias", "", SECONDARY_REFERENCE),
    ("NTC-3766", "NTC 3766 - Rejillas de concreto", "ICONTEC", "", "Ficha técnica de fabricante", "", SECONDARY_REFERENCE),
)

TESTS = (
    ("FLEXURAL_MODULUS", "Flexotracción / Módulo de Rotura", None), ("ABSORPTION", "Absorción de agua", None),
    ("PAVER_ABRASION_NTC_5147", "Abrasión de adoquines", "NTC-5147"), ("PAVER_DIMENSIONS_NTC_2017", "Dimensiones y geometría de adoquines", "NTC-2017"),
    ("COMPRESSION_DOCUMENTARY", "Compresión (referencia documental INV)", "INV-E-426"),
    ("MASONRY_COMPRESSION_NTC_4024", "Resistencia a compresión de unidades de mampostería de concreto", "NTC-4024"),
    ("MASONRY_ABSORPTION_NTC_4024", "Absorción de unidades de mampostería de concreto", "NTC-4024"),
    ("GRADATION", "Granulometría", "INV-E-213"), ("AGGREGATE_GRADATION_NTC_77", "Granulometría y módulo de finura", "NTC-77"),
    ("AGGREGATE_SAMPLING", "Muestreo de agregados", None), ("MATERIAL_FINER_75UM", "Material que pasa tamiz 75 µm por lavado", "NTC-78"),
    ("ORGANIC_IMPURITIES", "Impurezas orgánicas", "NTC-127"), ("ORGANIC_IMPURITIES_STRENGTH", "Efecto de impurezas orgánicas sobre resistencia", None),
    ("SULFATE_SOUNDNESS", "Solidez en sulfatos", "INV-E-220"), ("AGGREGATE_SULFATE_SOUNDNESS_NTC_126", "Solidez de agregados mediante sulfatos", "NTC-126"),
    ("CLAY_LUMPS_INV", "Terrones de arcilla y partículas deleznables", "INV-E-211"), ("CLAY_LUMPS_NTC_589", "Terrones de arcilla y partículas deleznables", "NTC-589"),
    ("LIGHTWEIGHT_PARTICLES", "Carbón, lignito y partículas livianas", None), ("ALKALI_AGGREGATE_REACTIVITY", "Reactividad potencial álcali-agregado", None),
    ("LOS_ANGELES", "Desgaste Los Ángeles", "INV-E-218"), ("LOS_ANGELES_NTC_98", "Desgaste Los Ángeles (agregado < 37.5 mm)", "NTC-98"), ("LOS_ANGELES_NTC_93", "Desgaste Los Ángeles (agregado > 19 mm)", "NTC-93"),
    ("MICRO_DEVAL", "Micro-Deval", "INV-E-238"), ("TEN_PERCENT_FINES", "Resistencia mecánica por método del 10 % de finos", "INV-E-224"),
    ("LIQUID_LIMIT", "Límite líquido", "INV-E-125"), ("PLASTICITY_INDEX", "Índice de plasticidad", "INV-E-126"), ("SAND_EQUIVALENT", "Equivalente de arena", "INV-E-133"),
    ("METHYLENE_BLUE", "Valor de azul de metileno", "INV-E-235"), ("FLAKINESS_ELONGATION", "Índices de aplanamiento y alargamiento", "INV-E-230"),
    ("FRACTURED_FACES", "Caras fracturadas", "INV-E-227"), ("FINE_ANGULARITY", "Angularidad de la fracción fina", "INV-E-239"),
    ("CBR", "CBR de laboratorio", "INV-E-148"), ("MODIFIED_COMPACTION", "Ensayo modificado de compactación", "INV-E-142"),
    ("CEMENT_CONTROL", "Control de características del cemento", "INV-ART-501"),
)


def _procedure(equipment: str, preparation: str, steps: str, calculation: str, notes: str) -> str:
    """Guía operativa propia; no reproduce el texto de las normas."""
    return (
        f"Equipos\n{equipment}\n\n"
        f"Preparación previa\n{preparation}\n\n"
        f"Procedimiento\n{steps}\n\n"
        f"Cálculo y registro final\n{calculation}\n\n"
        f"Observaciones\n{notes}"
    )


TEST_GUIDANCE = {
    "FLEXURAL_MODULUS": (
        "Dispositivo de flexión, máquina de ensayo calibrada, apoyos, regla o calibrador y balanza cuando aplique.",
        "Seleccione unidades representativas, identifíquelas y mida las dimensiones que intervienen en el cálculo. Acondicione las piezas conforme a la especificación aplicable.",
        "1. Centre la unidad sobre los apoyos del dispositivo.\n2. Aplique la carga en la posición definida para la geometría de la pieza, sin golpes.\n3. Mantenga el registro continuo de la carga hasta la rotura.\n4. Registre carga máxima, dimensiones medidas y tipo de falla.",
        "Calcule el módulo de rotura con la geometría y la carga máxima registradas; informe en MPa, junto con los valores individuales y el promedio exigido.",
        "Para adoquines y losetas confirme en la edición vigente la separación de apoyos, orientación y velocidad de carga antes de ensayar.",
    ),
    "ABSORPTION": (
        "Balanza, horno, recipiente de inmersión, bandejas, paños absorbentes y termómetro cuando la norma lo requiera.",
        "Limpie las unidades, retire material suelto y marque cada espécimen. Obtenga la masa seca después del acondicionamiento indicado y la masa saturada superficialmente seca.",
        "1. Seque y enfríe las unidades según el método aplicable.\n2. Pese cada unidad seca.\n3. Sature por inmersión durante el periodo definido por la norma.\n4. Retire el exceso superficial de agua sin extraer agua de poros y pese de nuevo.\n5. Registre masas por espécimen.",
        "Calcule la absorción como el incremento de masa respecto a la masa seca y reporte porcentaje individual y promedio.",
        "Confirme el tiempo de inmersión, temperatura y condición superficial en la edición vigente de la especificación del producto.",
    ),
    "PAVER_ABRASION_NTC_5147": (
        "Equipo de abrasión indicado por NTC 5147, material abrasivo, regla o dispositivo de lectura, calibrador y cepillo.",
        "Seleccione las unidades y las zonas de ensayo sin defectos ajenos al desgaste. Limpie y acondicione las superficies antes de la prueba.",
        "1. Identifique la cara de desgaste.\n2. Monte la unidad y verifique la condición inicial.\n3. Ejecute el ciclo de abrasión con el equipo y abrasivo especificados.\n4. Limpie la zona y mida la huella resultante en los puntos requeridos.\n5. Registre cada lectura y observación.",
        "Obtenga la longitud media de huella por espécimen y el promedio del conjunto; reporte en mm.",
        "El ajuste de carga, abrasivo y ciclo debe confirmarse con la edición vigente de NTC 5147.",
    ),
    "PAVER_DIMENSIONS_NTC_2017": (
        "Calibrador, regla metálica, escuadra, galgas y superficie plana de referencia.",
        "Limpie las piezas y seleccione una muestra representativa. Identifique cara superior, separadores y biseles cuando existan.",
        "1. Mida longitud, ancho y espesor en los puntos requeridos.\n2. Mida biseles, separadores y capa superficial cuando aplique.\n3. Compruebe escuadría, alabeo y defectos visibles.\n4. Registre cada valor por unidad, sin redondear antes del cálculo.",
        "Calcule promedios, diferencias entre mediciones y desviaciones frente a la dimensión nominal; informe en mm.",
        "Use las posiciones de medición de NTC 2017 vigente; la inspección visual no sustituye la medición dimensional.",
    ),
    "COMPRESSION_DOCUMENTARY": (
        "Prensa de compresión calibrada, dispositivos de centrado, regla o calibrador y balanza si la especificación lo exige.",
        "Acondicione e identifique las unidades y determine el área de carga pertinente antes de montarlas en la prensa.",
        "1. Centre el espécimen entre platinas.\n2. Aplique carga continua y sin impacto hasta la falla.\n3. Registre la carga máxima y la forma de falla.\n4. Repita para todas las unidades de la muestra.",
        "Divida la carga máxima por el área definida por la especificación y reporte resistencia individual y promedio en MPa.",
        "Es una referencia documental histórica: confirme el método operativo aplicable al producto antes de usar el resultado para aceptación.",
    ),
    "MASONRY_COMPRESSION_NTC_4024": (
        "Prensa calibrada, accesorios de apoyo o refrentado autorizados, regla/calibrador y balanza cuando aplique.",
        "Muestree unidades representativas, identifíquelas y acondiciónelas conforme a NTC 4024. Determine previamente las dimensiones y el área neta o bruta requerida por la especificación.",
        "1. Prepare las caras de carga con el método permitido.\n2. Centre la unidad en la prensa y verifique el contacto uniforme.\n3. Aplique carga axial continua hasta la falla.\n4. Registre carga máxima, área empleada y tipo de rotura para cada unidad.",
        "Calcule resistencia como carga máxima dividida por el área indicada; informe MPa individuales y promedio sobre el área exigida.",
        "Confirme en NTC 4024 vigente el acondicionamiento, refrentado y velocidad de carga antes de ejecutar el ensayo.",
    ),
    "MASONRY_ABSORPTION_NTC_4024": (
        "Balanza, horno, tanque de inmersión, bandejas, paños y, para densidad, instrumentos dimensionales.",
        "Limpie e identifique las unidades. Obtenga masa seca y prepare la saturación conforme a NTC 4024; mida volumen o dimensiones si se requiere clasificar por densidad.",
        "1. Seque las unidades y registre masa seca.\n2. Sature según el método.\n3. Obtenga masa saturada superficialmente seca.\n4. Registre las masas y la información de densidad aplicable.",
        "Calcule absorción porcentual respecto a masa seca y, cuando corresponda, densidad de la unidad; reporte promedio e individuales.",
        "Verifique tiempos, temperatura y método de determinación de densidad en la edición vigente de NTC 4024.",
    ),
    "GRADATION": (
        "Balanza, horno, juego de tamices, agitador mecánico, bandejas, cepillo y divisor de muestras.",
        "Obtenga una muestra representativa, redúzcala sin segregación, seque a masa constante cuando aplique y registre masa inicial. Seleccione la serie de tamices del material, incluyendo 75 µm/No. 200 cuando corresponda.",
        "1. Arme los tamices de abertura mayor a menor.\n2. Tamice la muestra con agitación controlada.\n3. Recupere y pese el material retenido en cada tamiz.\n4. Verifique el balance de masas y repita si existe pérdida no explicada.\n5. Registre masas y porcentajes acumulados.",
        "Calcule porcentaje retenido, retenido acumulado y porcentaje que pasa cada tamiz; compare la curva con la gradación especificada.",
        "Para base y subbase use la serie exigida por INV E-213 y la tabla del artículo aplicable; para agregados confirme la serie NTC 77 vigente.",
    ),
    "AGGREGATE_GRADATION_NTC_77": (
        "Balanza, horno, divisor de muestras, juego de tamices, agitador, bandejas y cepillo.",
        "Reduzca una muestra representativa, séquela cuando corresponda y registre la masa de ensayo. Seleccione los tamices establecidos por la gradación comercial; incluya No. 4 y No. 200/75 µm cuando el programa lo exija.",
        "1. Ensamble la columna de tamices en orden decreciente.\n2. Tamice la muestra y pese cada fracción retenida.\n3. Revise el balance de masa y anote cualquier lavado previo.\n4. Consolide el porcentaje que pasa por cada tamiz.",
        "Calcule porcentajes retenidos y pasantes; para agregado fino calcule módulo de finura con la serie normativa aplicable.",
        "Confirme masa mínima y serie exacta de tamices con NTC 77 vigente para el tamaño máximo nominal del agregado.",
    ),
    "AGGREGATE_SAMPLING": (
        "Palas o cucharas, recipientes limpios, sellos, etiquetas, divisor y balanza si se controla masa.",
        "Defina lote, fuente, fecha y punto de extracción. Prepare recipientes que eviten contaminación, pérdida de finos o cambio de humedad.",
        "1. Tome incrementos de zonas representativas, evitando solo la superficie segregada.\n2. Combine incrementos cuando corresponda al lote.\n3. Reduzca con divisor o cuarteo controlado.\n4. Selle, rotule y registre cadena de custodia.",
        "Registre origen, lote, fecha, masa aproximada, condición de humedad y responsable; entregue porciones separadas para los ensayos previstos.",
        "La cantidad mínima y número de incrementos deben confirmarse en la norma de muestreo vigente aplicable al agregado.",
    ),
    "MATERIAL_FINER_75UM": (
        "Balanza, tamiz 75 µm/No. 200, recipiente de lavado, horno, bandejas y cepillo.",
        "Seque y pese la porción de ensayo. Proteja el material retenido y asegure que el lavado no arrastre partículas mayores por manipulación.",
        "1. Lave la muestra sobre el tamiz 75 µm hasta que el agua salga visualmente clara.\n2. Recupere el material retenido y séquelo.\n3. Enfríe y pese la masa final.\n4. Registre masas inicial y final.",
        "Calcule el porcentaje de material que pasa 75 µm por la pérdida de masa atribuible al lavado y reporte en porcentaje.",
        "Confirme el acondicionamiento y criterio de lavado de NTC 78 vigente antes de liberar el resultado.",
    ),
    "ORGANIC_IMPURITIES": (
        "Frascos transparentes, solución reactiva indicada, patrón de color, balanza y elementos de seguridad.",
        "Obtenga arena representativa y limpia los frascos. Prepare el blanco o patrón de comparación que exija el método.",
        "1. Introduzca la porción de agregado fino en el frasco.\n2. Añada la solución reactiva indicada y mezcle.\n3. Deje reposar el tiempo establecido.\n4. Compare el color del líquido con el patrón y registre la observación.",
        "Reporte la comparación de color y la decisión de continuar o no con ensayo de efecto sobre resistencia.",
        "Confirme solución, proporciones y tiempo de reposo en NTC 127 vigente.",
    ),
    "ORGANIC_IMPURITIES_STRENGTH": (
        "Mezcladora, moldes de mortero, materiales de referencia, equipo de curado y máquina de compresión.",
        "Prepare arena de ensayo y arena de referencia conforme al criterio previo de impurezas. Dosifique morteros comparables con materiales controlados.",
        "1. Elabore series de mortero de referencia y de ensayo.\n2. Moldee y cure en condiciones equivalentes.\n3. Ensaye resistencia a la edad indicada.\n4. Registre resistencias y condiciones de curado.",
        "Calcule la relación de resistencia entre mortero con arena de ensayo y mortero de referencia; reporte el porcentaje comparativo.",
        "Use este ensayo cuando el cribado por color lo requiera y confirme edades y dosificación en la norma vigente.",
    ),
    "SULFATE_SOUNDNESS": (
        "Tamices, balanza, horno, recipientes resistentes, solución de sulfato de sodio o magnesio, bandejas y EPP.",
        "Separe las fracciones granulométricas exigidas, lave y seque. Prepare la solución y verifique seguridad química antes de iniciar.",
        "1. Sumerja las fracciones en la solución.\n2. Complete los ciclos de inmersión y secado definidos.\n3. Lave para retirar sales al finalizar.\n4. Seque, tamice por fracción y determine la masa retenida.",
        "Calcule la pérdida porcentual ponderada o por fracción según el método y reporte el sulfato utilizado.",
        "Los ciclos, concentración y fracciones deben confirmarse en INV E-220 vigente.",
    ),
    "AGGREGATE_SULFATE_SOUNDNESS_NTC_126": (
        "Tamices, balanza, horno, recipientes, solución de sulfato, bandejas y EPP.",
        "Clasifique y acondicione las fracciones de agregado conforme al método NTC. Registre masa seca inicial de cada fracción.",
        "1. Exponga las fracciones a los ciclos de solución y secado.\n2. Lave las sales al finalizar.\n3. Seque y tamice cada fracción.\n4. Pese la masa retenida y documente desintegración visible.",
        "Calcule la pérdida de masa por fracción y el resultado combinado cuando aplique; informe en porcentaje.",
        "Confirme sal, concentración, ciclos y tamices con NTC 126 vigente.",
    ),
    "CLAY_LUMPS_INV": (
        "Tamices, balanza, recipiente de inmersión, horno, bandejas y utensilios manuales.",
        "Separe la fracción requerida, séquela y determine masa inicial. Prepare una superficie limpia para desintegrar solo las partículas deleznables.",
        "1. Sumerja la porción según el método.\n2. Desintegre manualmente los terrones que se ablanden, sin triturar partículas sanas.\n3. Lave, seque y tamice.\n4. Pese el material retenido final.",
        "Calcule el porcentaje perdido respecto a la masa seca inicial y reporte por fracción o combinado.",
        "Confirme fracciones y tiempos de inmersión en INV E-211 vigente.",
    ),
    "CLAY_LUMPS_NTC_589": (
        "Tamices, balanza, recipientes, horno, bandejas y herramienta de desintegración manual.",
        "Acondicione la muestra, separe las fracciones exigidas y registre la masa seca inicial de cada una.",
        "1. Humedezca o sumerja conforme al método.\n2. Desintegre terrones de arcilla y partículas friables sin forzar el agregado sano.\n3. Lave, seque y tamice.\n4. Pese el material conservado.",
        "Calcule el porcentaje de terrones y partículas deleznables por pérdida de masa; informe en porcentaje.",
        "Verifique fracciones, tiempos y criterio de desintegración con NTC 589 vigente.",
    ),
    "LIGHTWEIGHT_PARTICLES": (
        "Balanza, tamices, recipiente de separación por densidad, líquido apropiado, horno y EPP.",
        "Separe la fracción requerida, seque y registre masa inicial. Revise la ficha de seguridad del líquido de separación.",
        "1. Coloque la fracción en el medio de separación.\n2. Retire las partículas flotantes o livianas según el método.\n3. Lave y seque las fracciones recuperadas.\n4. Pese las partículas clasificadas.",
        "Calcule el porcentaje de partículas livianas respecto a la masa de ensayo; reporte por fracción si aplica.",
        "Confirme medio de separación, densidad y fracciones con la norma vigente antes de ejecutar.",
    ),
    "ALKALI_AGGREGATE_REACTIVITY": (
        "Tamices, balanza, moldes de mortero o equipo químico según método seleccionado, cámara de curado y comparador de longitud cuando aplique.",
        "Defina el método de cribado o confirmación aplicable y revise antecedentes petrográficos, fuente y resultados de expansión disponibles.",
        "1. Prepare la muestra con la gradación prescrita.\n2. Elabore especímenes o extractos conforme al método seleccionado.\n3. Mantenga el acondicionamiento y lecturas programadas.\n4. Registre expansiones, observaciones y controles.",
        "Reporte el indicador del método elegido y su interpretación, identificando la fuente del agregado.",
        "La metodología y criterios requieren confirmación con la edición vigente y el plan de durabilidad del proyecto.",
    ),
    "LOS_ANGELES": (
        "Máquina Los Ángeles, carga abrasiva, tamices, balanza, horno y bandejas.",
        "Seleccione la gradación de carga según el tamaño del agregado, lave/seque si corresponde y registre masa inicial. Verifique estado de esferas y tambor.",
        "1. Introduzca agregado y carga abrasiva en el tambor.\n2. Ejecute el número de revoluciones definido para la gradación.\n3. Descargue, tamice el material y determine la masa retenida.\n4. Registre desgaste y observaciones.",
        "Calcule la pérdida porcentual de masa respecto a la masa inicial e informe la gradación utilizada.",
        "Para controles INV el catálogo usa la condición de 500 revoluciones; confirme la gradación y carga con INV E-218 vigente.",
    ),
    "LOS_ANGELES_NTC_98": (
        "Máquina Los Ángeles, carga abrasiva, tamices, balanza, horno y bandejas.",
        "Prepare agregado grueso menor a 37.5 mm conforme a la gradación NTC aplicable y registre masa inicial.",
        "1. Cargue tambor, agregado y esferas.\n2. Ejecute el ciclo prescrito.\n3. Descargue, tamice y pese la fracción retenida.\n4. Documente pérdida y condición de la muestra.",
        "Calcule porcentaje de desgaste por diferencia entre masa inicial y masa retenida final.",
        "Confirme gradación, esferas y revoluciones con NTC 98 vigente.",
    ),
    "LOS_ANGELES_NTC_93": (
        "Máquina Los Ángeles, carga abrasiva, tamices, balanza, horno y bandejas.",
        "Prepare agregado grueso de tamaño mayor a 19 mm y seleccione la gradación exigida por NTC 93.",
        "1. Cargue tambor, agregado y esferas según la gradación.\n2. Complete el ciclo prescrito.\n3. Tamice el material descargado y determine la masa retenida.\n4. Registre resultados individuales del lote.",
        "Calcule porcentaje de pérdida de masa y reporte la gradación ensayada.",
        "Verifique masa de carga, esferas y revoluciones con NTC 93 vigente.",
    ),
    "MICRO_DEVAL": (
        "Equipo Micro-Deval, cilindros, carga abrasiva, agua, tamices, horno y balanza.",
        "Seleccione y acondicione la fracción granulométrica requerida. Registre masa inicial y compruebe el estado de cilindros y carga abrasiva.",
        "1. Introduzca muestra, carga abrasiva y medio de ensayo en el cilindro.\n2. Ejecute el ciclo del equipo.\n3. Lave y tamice el material al finalizar.\n4. Seque la fracción retenida y pésela.",
        "Calcule la pérdida porcentual respecto a la masa inicial e informe la fracción ensayada.",
        "Confirme masa, carga abrasiva, agua y revoluciones en INV E-238 vigente.",
    ),
    "TEN_PERCENT_FINES": (
        "Prensa, molde y pistón del método, balanza, tamices, instrumentos de desplazamiento y bandejas.",
        "Prepare la fracción granulométrica indicada, acondiciónela y registre masa. Revise la calibración de carga y desplazamiento.",
        "1. Llene el molde conforme al procedimiento.\n2. Aplique la carga controlada y registre la fuerza asociada a la deformación establecida.\n3. Repita las determinaciones necesarias.\n4. Registre masas y curvas de carga.",
        "Obtenga la carga o resistencia equivalente al 10 % de finos con las relaciones del método; informe el valor y condiciones de muestra.",
        "Verifique preparación, velocidad y lectura objetivo en INV E-224 vigente.",
    ),
    "LIQUID_LIMIT": (
        "Copa de Casagrande o penetrómetro según método, ranurador, balanza, horno, espátulas y recipientes de humedad.",
        "Use la fracción de suelo indicada, desagregada sin alterar sus finos. Prepare porciones con diferentes humedades y recipientes identificados.",
        "1. Mezcle con agua hasta consistencia uniforme.\n2. Ejecute lecturas a varias humedades con el equipo seleccionado.\n3. Tome porciones para humedad cerca de cada lectura.\n4. Seque y determine contenido de agua.\n5. Trace o calcule la relación requerida.",
        "Determine el límite líquido a partir de la relación entre humedad y la respuesta del equipo; reporte en porcentaje.",
        "Confirme método, número de puntos y criterio de lectura con INV E-125 vigente.",
    ),
    "PLASTICITY_INDEX": (
        "Placa de vidrio, espátula, balanza, horno, recipientes de humedad y equipo para límite líquido.",
        "Prepare material fino representativo. Disponga del límite líquido determinado sobre la misma fracción y acondicione la pasta para los rollos.",
        "1. Forme rollos con la pasta sobre superficie no absorbente.\n2. Amasar y repetir hasta la condición de agrietamiento indicada.\n3. Tome muestra para humedad.\n4. Determine límite plástico y consolide con el límite líquido.",
        "Calcule índice de plasticidad como límite líquido menos límite plástico; reporte ambos límites y el índice en porcentaje.",
        "El criterio de diámetro del rollo y acondicionamiento debe confirmarse en INV E-126 vigente.",
    ),
    "SAND_EQUIVALENT": (
        "Cilindros graduados, agitador, tubo irrigador, solución de trabajo, cronómetro y regla de lectura.",
        "Prepare la fracción que pasa el tamiz indicado, mezcle la solución de trabajo y verifique limpieza de cilindros.",
        "1. Introduzca muestra y solución en el cilindro.\n2. Agite con el método establecido.\n3. Irrigue y deje sedimentar por el tiempo definido.\n4. Lea altura de arena y de suspensión de finos.\n5. Registre temperaturas u observaciones si el método lo exige.",
        "Calcule equivalente de arena como relación entre lectura de arena y lectura de arcilla/suspensión, expresada en porcentaje.",
        "Confirme tiempos de agitación, sedimentación y lectura con INV E-133 vigente.",
    ),
    "METHYLENE_BLUE": (
        "Bureta o dosificador, solución de azul de metileno, agitador, papel filtro, balanza y recipientes.",
        "Prepare la fracción fina y la suspensión conforme al método. Estandarice o verifique la solución antes de usarla.",
        "1. Agite la suspensión.\n2. Añada incrementos de solución de azul de metileno.\n3. Realice la prueba de mancha sobre papel filtro después de cada adición.\n4. Identifique el punto final y registre volumen consumido.",
        "Calcule valor de azul de metileno a partir de volumen, concentración y masa seca de muestra; informe en la unidad del método.",
        "Confirme concentración, incrementos y criterio de halo con INV E-235 vigente.",
    ),
    "FLAKINESS_ELONGATION": (
        "Tamices, calibradores de aplanamiento y alargamiento, balanza y bandejas.",
        "Seque y clasifique el agregado por fracciones de tamiz. Registre la masa de cada fracción a evaluar.",
        "1. Pase cada partícula por el calibrador de aplanamiento.\n2. Separe y pese las partículas clasificadas.\n3. Evalúe alargamiento con su calibrador.\n4. Consolide resultados ponderados por fracción.",
        "Calcule índices de aplanamiento y alargamiento como porcentaje de masa de partículas clasificadas respecto a la masa evaluada.",
        "Verifique fracciones y apertura de galgas en INV E-230 vigente.",
    ),
    "FRACTURED_FACES": (
        "Tamices, balanza, bandejas y superficie de inspección iluminada.",
        "Separe la fracción gruesa requerida, lave/seque si es necesario y registre masa inicial de cada fracción.",
        "1. Examine cada partícula sobre superficie limpia.\n2. Clasifique por una o más caras fracturadas conforme a la definición del método.\n3. Pese cada grupo.\n4. Registre fotografías u observaciones de casos dudosos.",
        "Calcule porcentaje en masa de partículas con el número de caras fracturadas requerido.",
        "Confirme definición de cara fracturada y fracciones con INV E-227 vigente.",
    ),
    "FINE_ANGULARITY": (
        "Molde/cilindro de angularidad, embudo, balanza, regla de enrase y bandejas.",
        "Seque y prepare la fracción fina especificada. Verifique volumen del recipiente y condición del embudo antes de cada serie.",
        "1. Llene el recipiente por caída libre sin compactar.\n2. Enrase sin vibrar.\n3. Pese el contenido.\n4. Repita las determinaciones y registre masas y volumen.",
        "Calcule porcentaje de vacíos o índice de angularidad a partir de masa, volumen y densidad de referencia del método.",
        "Confirme fracción de ensayo, altura de caída y ecuación con INV E-239 vigente.",
    ),
    "MODIFIED_COMPACTION": (
        "Molde Proctor modificado, pisón mecánico o manual permitido, balanza, horno, bandejas, extractor y tamices.",
        "Prepare material representativo, controle la fracción máxima permitida y elabore porciones con varios contenidos de humedad.",
        "1. Mezcle una porción con agua conocida.\n2. Compacte en el molde por capas usando la energía del método.\n3. Determine masa húmeda y contenido de humedad.\n4. Repita con humedades sucesivas.\n5. Construya la curva humedad-densidad seca.",
        "Calcule densidad seca de cada punto y obtenga densidad seca máxima y humedad óptima de la curva.",
        "Confirme molde, capas, golpes y energía de compactación con INV E-142 vigente.",
    ),
    "CBR": (
        "Molde CBR, equipo de compactación, sobrecarga, tanque de inmersión si aplica, penetrómetro, prensa y comparadores.",
        "Use la humedad óptima y densidad seca de referencia del Proctor aplicable. Prepare especímenes con la energía de compactación definida y acondicione según el programa de ensayo.",
        "1. Compacte el material en el molde y registre humedad/densidad.\n2. Aplique sobrecarga y acondicionamiento requerido, incluido remojo cuando aplique.\n3. Penetre el pistón a velocidad controlada.\n4. Registre carga frente a penetración.\n5. Repita para la condición de densidad requerida.",
        "Obtenga CBR comparando las cargas medidas con las cargas patrón del método; reporte CBR, expansión si se midió, humedad y densidad seca.",
        "La condición de inmersión, sobrecarga y penetraciones de reporte se confirman en INV E-148 vigente.",
    ),
    "CEMENT_CONTROL": (
        "Balanza, recipientes de almacenamiento, formatos de recepción y equipos de verificación disponibles en el laboratorio.",
        "Revise certificado, tipo de cemento, lote, fecha de recepción, integridad de empaque y condiciones de almacenamiento seco.",
        "1. Identifique cada lote recibido.\n2. Revise documentación de conformidad y vigencia.\n3. Inspeccione humedad, grumos, contaminación y rotación de inventario.\n4. Registre cualquier muestra retenida o ensayo externo requerido.",
        "Registre proveedor, lote, fecha, cantidad, certificado y decisión de aceptación; relacione resultados de verificación disponibles.",
        "Este control es documental y de recepción; los ensayos físicos/químicos se coordinan con el método contractual aplicable.",
    ),
}


def _application_procedure(material_code: str, test_code: str, material_name: str) -> str:
    equipment, preparation, steps, calculation, notes = TEST_GUIDANCE[test_code]
    if material_code == "SLAB_FLOOR" and test_code == "FLEXURAL_MODULUS":
        notes = "Para losetas confirme orientación, apoyos y velocidad de carga en NTC 4992 vigente antes de ensayar."
    elif material_code == "PAVER_CONCRETE" and test_code == "FLEXURAL_MODULUS":
        notes = "Para adoquines confirme orientación, apoyos y velocidad de carga en NTC 2017 vigente antes de ensayar."
    return _procedure(equipment, f"Aplicación: {material_name}. {preparation}", steps, calculation, notes)


def seed_inspection_catalog(session: Session) -> None:
    materials = _upsert_materials(session)
    standards = _upsert_standards(session)
    tests = _upsert_tests(session, standards)
    session.execute(delete(TestRequirement).where(TestRequirement.seed_key.in_((
        "paver-pavement-flex-average", "paver-pavement-flex-individual", "paver-inv-compression-average", "paver-inv-compression-individual", "paver-inv-absorption-average", "paver-inv-absorption-individual", "paver-inv-abrasion-volume", "paver-inv-abrasion-thickness", "paver-flex-average", "paver-flex-individual", "fine-aggregate-absorption", "fine-aggregate-sand-equivalent",
    ))))
    _migrate_legacy_relations(session, materials, tests)
    _upsert_applicabilities(session, materials, standards, tests)
    _upsert_requirements(session, materials, standards, tests)


def _upsert_materials(session: Session) -> dict[str, MaterialType]:
    existing = {item.code: item for item in session.scalars(select(MaterialType))}
    for code, name in MATERIALS:
        item = existing.get(code)
        if item is None:
            item = MaterialType(code=code, name=name)
            session.add(item)
            existing[code] = item
        item.name, item.active = name, True
    session.flush()
    return {item.code: item for item in session.scalars(select(MaterialType))}


def _upsert_standards(session: Session) -> dict[str, StandardReference]:
    existing = {item.code: item for item in session.scalars(select(StandardReference))}
    fields = ("title", "issuer", "edition", "source_reference", "location_reference", "verification_status")
    for code, *values in STANDARDS:
        item = existing.get(code)
        if item is None:
            item = StandardReference(code=code)
            session.add(item)
            existing[code] = item
        for field, value in zip(fields, values):
            setattr(item, field, value)
    session.flush()
    return existing


def _upsert_tests(session: Session, standards: dict[str, StandardReference]) -> dict[str, LaboratoryTest]:
    existing = {item.code: item for item in session.scalars(select(LaboratoryTest))}
    for code, name, standard in TESTS:
        item = existing.get(code)
        if item is None:
            item = LaboratoryTest(code=code)
            session.add(item)
            existing[code] = item
        equipment, _preparation, _steps, _calculation, _notes = TEST_GUIDANCE[code]
        item.name, item.standard, item.active = name, standards.get(standard), True
        if not item.equipment:
            item.equipment = equipment
        if not item.procedure_summary:
            item.procedure_summary = (
                "Guía operativa disponible por material: preparación, ejecución, "
                "registros y cálculo del resultado."
            )
    session.flush()
    return existing


def _migrate_legacy_relations(session: Session, materials: dict[str, MaterialType], tests: dict[str, LaboratoryTest]) -> None:
    canonical = materials["PAVER_CONCRETE"]
    replacements = {"ABRASION": "PAVER_ABRASION_NTC_5147", "DIMENSIONS": "PAVER_DIMENSIONS_NTC_2017"}
    for code in ("PAVER_PAVEMENT", "PAVER_FLOOR"):
        legacy = materials.get(code)
        if legacy is None:
            continue
        for entry in session.scalars(select(InspectionPlanEntry).where(InspectionPlanEntry.material_type_id == legacy.id)):
            entry.material_type = canonical
            entry.laboratory_test = tests.get(replacements.get(entry.laboratory_test.code), entry.laboratory_test)
        for requirement in session.scalars(select(TestRequirement).where(TestRequirement.material_type_id == legacy.id)):
            requirement.material_type = canonical
            requirement.laboratory_test = tests.get(replacements.get(requirement.laboratory_test.code), requirement.laboratory_test)
        for item in list(session.scalars(select(TestApplicability).where(TestApplicability.material_type_id == legacy.id))):
            target = tests.get(replacements.get(item.laboratory_test.code), item.laboratory_test)
            duplicate = session.scalar(select(TestApplicability).where(TestApplicability.material_type_id == canonical.id, TestApplicability.laboratory_test_id == target.id))
            if duplicate is None:
                item.material_type, item.laboratory_test = canonical, target
            else:
                session.delete(item)
        legacy.active = False
    for code in ("FINE_AGGREGATE", "COARSE_AGGREGATE"):
        material = materials[code]
        for entry in session.scalars(select(InspectionPlanEntry).where(InspectionPlanEntry.material_type_id == material.id, InspectionPlanEntry.laboratory_test_id == tests["GRADATION"].id)):
            entry.laboratory_test = tests["AGGREGATE_GRADATION_NTC_77"]
        for item in list(session.scalars(select(TestApplicability).where(TestApplicability.material_type_id == material.id, TestApplicability.laboratory_test_id == tests["GRADATION"].id))):
            duplicate = session.scalar(select(TestApplicability).where(
                TestApplicability.material_type_id == material.id,
                TestApplicability.laboratory_test_id == tests["AGGREGATE_GRADATION_NTC_77"].id,
            ))
            if duplicate is None:
                item.laboratory_test = tests["AGGREGATE_GRADATION_NTC_77"]
            else:
                session.delete(item)
    for material_code in ("BLOCK_STRUCTURAL", "BLOCK_NON_STRUCTURAL"):
        material = materials[material_code]
        replacements = {
            "COMPRESSION_DOCUMENTARY": "MASONRY_COMPRESSION_NTC_4024",
            "ABSORPTION": "MASONRY_ABSORPTION_NTC_4024",
        }
        for entry in session.scalars(select(InspectionPlanEntry).where(
            InspectionPlanEntry.material_type_id == material.id,
            InspectionPlanEntry.laboratory_test_id.in_(
                (tests["COMPRESSION_DOCUMENTARY"].id, tests["ABSORPTION"].id)
            ),
        )):
            entry.laboratory_test = tests[replacements[entry.laboratory_test.code]]
        for item in list(session.scalars(select(TestApplicability).where(
            TestApplicability.material_type_id == material.id,
            TestApplicability.laboratory_test_id.in_(
                (tests["COMPRESSION_DOCUMENTARY"].id, tests["ABSORPTION"].id)
            ),
        ))):
            target = tests[replacements[item.laboratory_test.code]]
            duplicate = session.scalar(select(TestApplicability).where(
                TestApplicability.material_type_id == material.id,
                TestApplicability.laboratory_test_id == target.id,
            ))
            if duplicate is None:
                item.laboratory_test = target
            else:
                session.delete(item)
    session.flush()


def _upsert_applicabilities(session, materials, standards, tests) -> None:
    entries = (
        ("PAVER_CONCRETE", "FLEXURAL_MODULUS", "NTC-2017", "", True), ("PAVER_CONCRETE", "ABSORPTION", "NTC-2017", "", False), ("PAVER_CONCRETE", "PAVER_ABRASION_NTC_5147", "NTC-2017", "", False), ("PAVER_CONCRETE", "PAVER_DIMENSIONS_NTC_2017", "NTC-2017", "", False),
        ("SLAB_FLOOR", "FLEXURAL_MODULUS", "NTC-4992", "", True), ("SLAB_FLOOR", "ABSORPTION", "NTC-4992", "", False),
        ("BLOCK_STRUCTURAL", "MASONRY_COMPRESSION_NTC_4024", "NTC-4026", "", True), ("BLOCK_STRUCTURAL", "MASONRY_ABSORPTION_NTC_4024", "NTC-4026", "", False), ("BLOCK_NON_STRUCTURAL", "MASONRY_COMPRESSION_NTC_4024", "NTC-4076", "", True), ("BLOCK_NON_STRUCTURAL", "MASONRY_ABSORPTION_NTC_4024", "NTC-4076", "", False),
        ("GRASS_PAVER", "COMPRESSION_DOCUMENTARY", "NTC-3766", "", True), ("GRASS_PAVER", "ABSORPTION", "NTC-3766", "", False),
        ("GRANULAR_SUBBASE", "GRADATION", "INV-ART-320", "Una vez por jornada", True), ("GRANULAR_SUBBASE", "LIQUID_LIMIT", "INV-ART-320", "Una vez por jornada", False), ("GRANULAR_SUBBASE", "PLASTICITY_INDEX", "INV-ART-320", "Una vez por jornada", False), ("GRANULAR_SUBBASE", "LOS_ANGELES", "INV-ART-320", "Una vez por semana", False), ("GRANULAR_SUBBASE", "SAND_EQUIVALENT", "INV-ART-320", "Una vez por semana", False), ("GRANULAR_SUBBASE", "MODIFIED_COMPACTION", "INV-ART-320", "Una vez por semana", False), ("GRANULAR_SUBBASE", "CBR", "INV-ART-320", "Una vez por semana", False),
        *(("GRANULAR_SUBBASE", test, "INV-ART-320", "Control de procedencia y cambio de fuente", False) for test in ("MICRO_DEVAL", "SULFATE_SOUNDNESS", "CLAY_LUMPS_INV")),
        ("GRANULAR_BASE", "GRADATION", "INV-ART-330", "Una vez por jornada", True), ("GRANULAR_BASE", "LIQUID_LIMIT", "INV-ART-330", "Una vez por jornada", False), ("GRANULAR_BASE", "PLASTICITY_INDEX", "INV-ART-330", "Una vez por jornada", False), ("GRANULAR_BASE", "SAND_EQUIVALENT", "INV-ART-330", "Una vez por semana", False), ("GRANULAR_BASE", "METHYLENE_BLUE", "INV-ART-330", "Una vez por semana, cuando aplique", False), ("GRANULAR_BASE", "MODIFIED_COMPACTION", "INV-ART-330", "Una vez por semana", False), ("GRANULAR_BASE", "CBR", "INV-ART-330", "Una vez por semana", False),
        *(("GRANULAR_BASE", test, "INV-ART-330", "Control de procedencia y cambio de fuente", False) for test in ("LOS_ANGELES", "MICRO_DEVAL", "TEN_PERCENT_FINES", "SULFATE_SOUNDNESS", "CLAY_LUMPS_INV", "FLAKINESS_ELONGATION", "FRACTURED_FACES", "FINE_ANGULARITY")),
        *(("FINE_AGGREGATE", test, "NTC-174", "Control de aceptación según NTC 174" if test not in {"AGGREGATE_SAMPLING", "ORGANIC_IMPURITIES", "ORGANIC_IMPURITIES_STRENGTH", "AGGREGATE_SULFATE_SOUNDNESS_NTC_126", "LIGHTWEIGHT_PARTICLES", "ALKALI_AGGREGATE_REACTIVITY"} else "Cuando aplique", test == "AGGREGATE_GRADATION_NTC_77") for test in ("AGGREGATE_SAMPLING", "AGGREGATE_GRADATION_NTC_77", "MATERIAL_FINER_75UM", "ORGANIC_IMPURITIES", "ORGANIC_IMPURITIES_STRENGTH", "AGGREGATE_SULFATE_SOUNDNESS_NTC_126", "CLAY_LUMPS_NTC_589", "LIGHTWEIGHT_PARTICLES", "ALKALI_AGGREGATE_REACTIVITY")),
        *(("COARSE_AGGREGATE", test, "NTC-174", "Control de aceptación según NTC 174" if test in {"AGGREGATE_GRADATION_NTC_77", "MATERIAL_FINER_75UM", "CLAY_LUMPS_NTC_589"} else "Cuando aplique", test == "AGGREGATE_GRADATION_NTC_77") for test in ("AGGREGATE_SAMPLING", "AGGREGATE_GRADATION_NTC_77", "MATERIAL_FINER_75UM", "CLAY_LUMPS_NTC_589", "LIGHTWEIGHT_PARTICLES", "AGGREGATE_SULFATE_SOUNDNESS_NTC_126", "LOS_ANGELES_NTC_98", "LOS_ANGELES_NTC_93", "ALKALI_AGGREGATE_REACTIVITY")),
        ("CEMENT", "CEMENT_CONTROL", "INV-ART-501", "Una vez por cada mes de ejecución", True),
    )
    existing = {(item.material_type_id, item.laboratory_test_id): item for item in session.scalars(select(TestApplicability))}
    for material, test, standard, frequency, preferred in entries:
        item = existing.get((materials[material].id, tests[test].id))
        if item is None:
            item = TestApplicability(material_type=materials[material], laboratory_test=tests[test])
            session.add(item)
        item.standard, item.normative_frequency, item.preferred = standards[standard], frequency, preferred
        item.procedure_detail = _application_procedure(
            material,
            test,
            materials[material].name,
        )


def _upsert_requirements(session, materials, standards, tests) -> None:
    existing = {item.seed_key: item for item in session.scalars(select(TestRequirement))}
    fields = ("minimum", "maximum", "unit", "operator", "requirement_text", "condition", "aggregation", "age_days", "grading", "source_detail", "verification_status")
    for key, material, test, standard, *values in _requirement_rows():
        item = existing.get(key)
        if item is None:
            item = TestRequirement(seed_key=key)
            session.add(item)
        item.material_type, item.laboratory_test, item.standard = materials[material], tests[test], standards[standard]
        for field, value in zip(fields, values):
            setattr(item, field, value)


def _requirement_rows() -> list[tuple]:
    rows = []
    def add(key, material, test, standard, minimum=None, maximum=None, unit="", operator="", text="", condition="", aggregation="", age=None, grading="", source="", status=PUBLIC_OFFICIAL_DERIVED):
        rows.append((key, material, test, standard, minimum, maximum, unit, operator, text, condition, aggregation, age, grading, source, status))
    def limits(prefix, material, test, values, unit, operator, source, condition=""):
        standard = "INV-ART-320" if material == "GRANULAR_SUBBASE" else "INV-ART-330"
        for grade, value in values.items():
            if value is None:
                add(f"{prefix}-{grade.lower()}-not-required", material, test, standard, text="No exigido para esta clase.", condition=f"Clase {grade}; {condition}".strip("; "), source=source)
            elif operator == "≥":
                add(f"{prefix}-{grade.lower()}", material, test, standard, minimum=value, unit=unit, operator=operator, condition=f"Clase {grade}; {condition}".strip("; "), source=source)
            else:
                add(f"{prefix}-{grade.lower()}", material, test, standard, maximum=value, unit=unit, operator=operator, condition=f"Clase {grade}; {condition}".strip("; "), source=source)

    # NTC 2017:2018 - adoquines, sin compresión como ensayo operativo.
    add("paver-absorption-average", "PAVER_CONCRETE", "ABSORPTION", "NTC-2017", maximum=7, unit="%", operator="≤", aggregation="Promedio de 5 especímenes", source="NTC 2017:2018", status=SECONDARY_REFERENCE)
    add("paver-absorption-individual", "PAVER_CONCRETE", "ABSORPTION", "NTC-2017", maximum=8, unit="%", operator="≤", aggregation="Individual", source="NTC 2017:2018", status=SECONDARY_REFERENCE)
    add("paver-flex-with-wear-average", "PAVER_CONCRETE", "FLEXURAL_MODULUS", "NTC-2017", minimum=4.2, unit="MPa", operator="≥", condition="Cumple desgaste: longitud promedio de huella de abrasión ≤ 23 mm", aggregation="Promedio de 5 adoquines", source="NTC 2017:2018", status=SECONDARY_REFERENCE)
    add("paver-flex-with-wear-individual", "PAVER_CONCRETE", "FLEXURAL_MODULUS", "NTC-2017", minimum=3.8, unit="MPa", operator="≥", condition="Cumple desgaste: longitud promedio de huella de abrasión ≤ 23 mm", aggregation="Individual", source="NTC 2017:2018", status=SECONDARY_REFERENCE)
    add("paver-flex-alternative-average", "PAVER_CONCRETE", "FLEXURAL_MODULUS", "NTC-2017", minimum=5, unit="MPa", operator="≥", condition="Alternativa sin aplicar el criterio de desgaste asociado", aggregation="Promedio de 5 adoquines", source="NTC 2017:2018", status=SECONDARY_REFERENCE)
    add("paver-flex-alternative-individual", "PAVER_CONCRETE", "FLEXURAL_MODULUS", "NTC-2017", minimum=4.2, unit="MPa", operator="≥", condition="Alternativa sin aplicar el criterio de desgaste asociado", aggregation="Individual", source="NTC 2017:2018", status=SECONDARY_REFERENCE)
    add("paver-abrasion", "PAVER_CONCRETE", "PAVER_ABRASION_NTC_5147", "NTC-2017", maximum=23, unit="mm", operator="≤", condition="Condición asociada a la rama de módulo de rotura 4.2 / 3.8 MPa", aggregation="Promedio de longitud de huella de 5 especímenes", source="NTC 2017:2018; método NTC 5147:2024", status=SECONDARY_REFERENCE)
    for key, minimum, maximum, condition in (("length", 100, 250, "Longitud nominal"), ("bevel-straight-horizontal", 3, 7, "Bisel recto; proyección horizontal"), ("bevel-straight-vertical", 3, 7, "Bisel recto; proyección vertical"), ("bevel-curved-horizontal", 4, 6, "Bisel curvo; proyección horizontal"), ("bevel-curved-vertical", 3, 5, "Bisel curvo; proyección vertical"), ("spacer-width", 8, 15, "Ancho de separadores cuando aplique"), ("spacer-thickness", 1.5, 2.5, "Espesor de separadores cuando aplique (2 ± 0.5 mm)")):
        add(f"paver-{key}", "PAVER_CONCRETE", "PAVER_DIMENSIONS_NTC_2017", "NTC-2017", minimum=minimum, maximum=maximum, unit="mm", operator="rango", condition=condition, source="NTC 2017:2018", status=SECONDARY_REFERENCE)
    for key, maximum, condition in (("length-width-spread", 1.5, "Diferencia entre mediciones de longitud/ancho"), ("length-width-standard", 1.5, "Diferencia respecto a longitud/ancho estándar"), ("thickness-standard", 2, "Desviación de espesor respecto al estándar para acabados aplicables"), ("thickness-spread", 2, "Rango entre mediciones de espesor"), ("chipping", 3, "Desportilladuras en condiciones aplicables"), ("bevel-spread", 1.5, "Rango entre mediciones de bisel")):
        add(f"paver-{key}", "PAVER_CONCRETE", "PAVER_DIMENSIONS_NTC_2017", "NTC-2017", maximum=maximum, unit="mm", operator="≤", condition=condition, source="NTC 2017:2018", status=SECONDARY_REFERENCE)
    add("paver-surface-layer", "PAVER_CONCRETE", "PAVER_DIMENSIONS_NTC_2017", "NTC-2017", minimum=8, unit="mm", operator="≥", condition="Capa superficial de adoquines bicapa", source="NTC 2017:2018", status=SECONDARY_REFERENCE)

    # Bloques de mampostería: especificación del producto y método NTC 4024 separados.
    add("block-structural-high-compression-average", "BLOCK_STRUCTURAL", "MASONRY_COMPRESSION_NTC_4024", "NTC-4026", minimum=13, unit="MPa", operator="≥", condition="Clase Alta; resistencia sobre área neta", aggregation="Promedio de 3 unidades", source="NTC 4026; método NTC 4024", status=SECONDARY_REFERENCE)
    add("block-structural-high-compression-individual", "BLOCK_STRUCTURAL", "MASONRY_COMPRESSION_NTC_4024", "NTC-4026", minimum=11, unit="MPa", operator="≥", condition="Clase Alta; resistencia sobre área neta", aggregation="Individual", source="NTC 4026; método NTC 4024", status=SECONDARY_REFERENCE)
    add("block-structural-low-compression-average", "BLOCK_STRUCTURAL", "MASONRY_COMPRESSION_NTC_4024", "NTC-4026", minimum=8, unit="MPa", operator="≥", condition="Clase Baja; resistencia sobre área neta", aggregation="Promedio de 3 unidades", source="NTC 4026; método NTC 4024", status=SECONDARY_REFERENCE)
    add("block-structural-low-compression-individual", "BLOCK_STRUCTURAL", "MASONRY_COMPRESSION_NTC_4024", "NTC-4026", minimum=7, unit="MPa", operator="≥", condition="Clase Baja; resistencia sobre área neta", aggregation="Individual", source="NTC 4026; método NTC 4024", status=SECONDARY_REFERENCE)
    for density, high, low in (("Peso liviano; densidad < 1680 kg/m³", 15, 18), ("Peso mediano; densidad 1680 a < 2000 kg/m³", 12, 15), ("Peso normal; densidad ≥ 2000 kg/m³", 9, 12)):
        key = density.split(";")[0].split()[-1].lower()
        add(f"block-structural-high-absorption-{key}", "BLOCK_STRUCTURAL", "MASONRY_ABSORPTION_NTC_4024", "NTC-4026", maximum=high, unit="%", operator="≤", condition=f"Clase Alta; {density}", aggregation="Promedio", source="NTC 4026; método NTC 4024", status=SECONDARY_REFERENCE)
        add(f"block-structural-low-absorption-{key}", "BLOCK_STRUCTURAL", "MASONRY_ABSORPTION_NTC_4024", "NTC-4026", maximum=low, unit="%", operator="≤", condition=f"Clase Baja; {density}", aggregation="Promedio", source="NTC 4026; método NTC 4024", status=SECONDARY_REFERENCE)
    add("block-nonstructural-compression-average", "BLOCK_NON_STRUCTURAL", "MASONRY_COMPRESSION_NTC_4024", "NTC-4076", minimum=6, unit="MPa", operator="≥", aggregation="Promedio de 3 unidades", source="NTC 4076; método NTC 4024", status=SECONDARY_REFERENCE)
    add("block-nonstructural-compression-individual", "BLOCK_NON_STRUCTURAL", "MASONRY_COMPRESSION_NTC_4024", "NTC-4076", minimum=5, unit="MPa", operator="≥", aggregation="Individual", source="NTC 4076; método NTC 4024", status=SECONDARY_REFERENCE)
    for density, maximum in (("Peso liviano; densidad < 1680 kg/m³", 18), ("Peso mediano; densidad 1680 a < 2000 kg/m³", 15), ("Peso normal; densidad ≥ 2000 kg/m³", 12)):
        key = density.split(";")[0].split()[-1].lower()
        add(f"block-nonstructural-absorption-{key}", "BLOCK_NON_STRUCTURAL", "MASONRY_ABSORPTION_NTC_4024", "NTC-4076", maximum=maximum, unit="%", operator="≤", condition=density, aggregation="Promedio", source="NTC 4076; método NTC 4024", status=SECONDARY_REFERENCE)

    # INVÍAS 2022 - Tabla 320-2.
    limits("subbase-los-angeles", "GRANULAR_SUBBASE", "LOS_ANGELES", {"A": 50, "B": 50, "C": 50}, "%", "≤", "Tabla 320-2", "500 revoluciones")
    limits("subbase-micro-deval", "GRANULAR_SUBBASE", "MICRO_DEVAL", {"A": 30, "B": 35, "C": None}, "%", "≤", "Tabla 320-2")
    for salt, maximum in (("sodium", 12), ("magnesium", 18)):
        limits(f"subbase-sulfate-{salt}", "GRANULAR_SUBBASE", "SULFATE_SOUNDNESS", {"A": maximum, "B": maximum, "C": maximum}, "%", "≤", "Tabla 320-2", f"Sulfato de {'sodio' if salt == 'sodium' else 'magnesio'}; se admite cualquiera de los sulfatos indicados")
    limits("subbase-liquid-limit", "GRANULAR_SUBBASE", "LIQUID_LIMIT", {"A": 25, "B": 25, "C": 25}, "%", "≤", "Tabla 320-2")
    limits("subbase-plasticity", "GRANULAR_SUBBASE", "PLASTICITY_INDEX", {"A": 6, "B": 6, "C": 6}, "%", "≤", "Tabla 320-2")
    limits("subbase-sand-equivalent", "GRANULAR_SUBBASE", "SAND_EQUIVALENT", {"A": 25, "B": 25, "C": 25}, "%", "≥", "Tabla 320-2")
    limits("subbase-clay-lumps", "GRANULAR_SUBBASE", "CLAY_LUMPS_INV", {"A": 2, "B": 2, "C": 2}, "%", "≤", "Tabla 320-2")
    limits("subbase-cbr", "GRANULAR_SUBBASE", "CBR", {"A": 40, "B": 30, "C": 30}, "%", "≥", "Tabla 320-2", "Cuatro días de inmersión y valor mínimo de densidad seca")
    _gradation(add, "subbase", "GRANULAR_SUBBASE", "SBG-50", [("50.0 mm / 2\"", 100, 100), ("37.5 mm / 1½\"", 70, 95), ("25.0 mm / 1\"", 60, 90), ("12.5 mm / 1/2\"", 45, 75), ("9.5 mm / 3/8\"", 40, 70), ("4.75 mm / No.4", 25, 55), ("2.00 mm / No.10", 15, 40), ("0.425 mm / No.40", 6, 25), ("0.075 mm / No.200", 2, 15)], "Tabla 320-3")
    _gradation(add, "subbase", "GRANULAR_SUBBASE", "SBG-38", [("37.5 mm / 1½\"", 100, 100), ("25.0 mm / 1\"", 75, 95), ("12.5 mm / 1/2\"", 55, 85), ("9.5 mm / 3/8\"", 45, 75), ("4.75 mm / No.4", 30, 60), ("2.00 mm / No.10", 20, 45), ("0.425 mm / No.40", 8, 30), ("0.075 mm / No.200", 2, 15)], "Tabla 320-3")

    # INVÍAS 2022 - Tabla 330-2.
    limits("base-los-angeles-500", "GRANULAR_BASE", "LOS_ANGELES", {"A": 35, "B": 40, "C": 40}, "%", "≤", "Tabla 330-2", "500 revoluciones")
    limits("base-los-angeles-100", "GRANULAR_BASE", "LOS_ANGELES", {"A": 7, "B": 8, "C": 8}, "%", "≤", "Tabla 330-2", "100 revoluciones")
    limits("base-micro-deval", "GRANULAR_BASE", "MICRO_DEVAL", {"A": 25, "B": 30, "C": None}, "%", "≤", "Tabla 330-2")
    limits("base-ten-percent-dry", "GRANULAR_BASE", "TEN_PERCENT_FINES", {"A": 90, "B": 70, "C": None}, "kN", "≥", "Tabla 330-2", "Valor en seco")
    limits("base-ten-percent-wet-dry", "GRANULAR_BASE", "TEN_PERCENT_FINES", {"A": 75, "B": 75, "C": None}, "%", "≥", "Tabla 330-2", "Relación húmedo/seco")
    for salt, maximum in (("sodium", 12), ("magnesium", 18)):
        limits(f"base-sulfate-{salt}", "GRANULAR_BASE", "SULFATE_SOUNDNESS", {"A": maximum, "B": maximum, "C": maximum}, "%", "≤", "Tabla 330-2", f"Sulfato de {'sodio' if salt == 'sodium' else 'magnesio'}")
    limits("base-liquid-limit", "GRANULAR_BASE", "LIQUID_LIMIT", {"A": None, "B": None, "C": 25}, "%", "≤", "Tabla 330-2")
    add("base-plasticity-a", "GRANULAR_BASE", "PLASTICITY_INDEX", "INV-ART-330", maximum=0, unit="%", operator="≤", text="No plástico (IP = 0).", condition="Clase A", source="Tabla 330-2")
    add("base-plasticity-b", "GRANULAR_BASE", "PLASTICITY_INDEX", "INV-ART-330", maximum=0, unit="%", operator="≤", text="No plástico (IP = 0).", condition="Clase B", source="Tabla 330-2")
    add("base-plasticity-c", "GRANULAR_BASE", "PLASTICITY_INDEX", "INV-ART-330", maximum=3, unit="%", operator="≤", condition="Clase C", source="Tabla 330-2")
    limits("base-sand-equivalent", "GRANULAR_BASE", "SAND_EQUIVALENT", {"A": 30, "B": 30, "C": 30}, "%", "≥", "Tabla 330-2")
    limits("base-methylene-blue", "GRANULAR_BASE", "METHYLENE_BLUE", {"A": 10, "B": 10, "C": 10}, "", "≤", "Tabla 330-2", "Exigido si equivalente de arena < 30 % y ≥ 25 %")
    limits("base-clay-lumps", "GRANULAR_BASE", "CLAY_LUMPS_INV", {"A": 2, "B": 2, "C": 2}, "%", "≤", "Tabla 330-2")
    limits("base-flakiness", "GRANULAR_BASE", "FLAKINESS_ELONGATION", {"A": 35, "B": 35, "C": 35}, "%", "≤", "Tabla 330-2")
    limits("base-one-face", "GRANULAR_BASE", "FRACTURED_FACES", {"A": 90, "B": 70, "C": 50}, "%", "≥", "Tabla 330-2", "Una cara")
    limits("base-two-faces", "GRANULAR_BASE", "FRACTURED_FACES", {"A": 85, "B": 50, "C": None}, "%", "≥", "Tabla 330-2", "Dos caras")
    limits("base-fine-angularity", "GRANULAR_BASE", "FINE_ANGULARITY", {"A": 35, "B": 35, "C": None}, "%", "≥", "Tabla 330-2")
    limits("base-cbr", "GRANULAR_BASE", "CBR", {"A": 95, "B": 80, "C": 80}, "%", "≥", "Tabla 330-2", "Cuatro días de inmersión")
    _gradation(add, "base", "GRANULAR_BASE", "BG-40", [("37.5 mm / 1½\"", 100, 100), ("25.0 mm / 1\"", 75, 100), ("19.0 mm / 3/4\"", 65, 90), ("9.5 mm / 3/8\"", 45, 68), ("4.75 mm / No.4", 30, 50), ("2.00 mm / No.10", 15, 32), ("0.425 mm / No.40", 7, 20), ("0.075 mm / No.200", 0, 9)], "Tabla 330-3")
    _gradation(add, "base", "GRANULAR_BASE", "BG-27", [("25.0 mm / 1\"", 100, 100), ("19.0 mm / 3/4\"", 75, 100), ("9.5 mm / 3/8\"", 52, 78), ("4.75 mm / No.4", 35, 59), ("2.00 mm / No.10", 20, 40), ("0.425 mm / No.40", 8, 22), ("0.075 mm / No.200", 0, 9)], "Tabla 330-3")
    _gradation(add, "base", "GRANULAR_BASE", "BG-38", [("37.5 mm / 1½\"", 100, 100), ("25.0 mm / 1\"", 70, 100), ("19.0 mm / 3/4\"", 60, 90), ("9.5 mm / 3/8\"", 45, 75), ("4.75 mm / No.4", 30, 60), ("2.00 mm / No.10", 20, 45), ("0.425 mm / No.40", 10, 30), ("0.075 mm / No.200", 5, 15)], "Tabla 330-3")
    _gradation(add, "base", "GRANULAR_BASE", "BG-25", [("25.0 mm / 1\"", 100, 100), ("19.0 mm / 3/4\"", 70, 100), ("9.5 mm / 3/8\"", 50, 80), ("4.75 mm / No.4", 35, 65), ("2.00 mm / No.10", 20, 45), ("0.425 mm / No.40", 10, 30), ("0.075 mm / No.200", 5, 15)], "Tabla 330-3")
    for material, standard, table, gradings in (("GRANULAR_SUBBASE", "INV-ART-320", "Tabla 320-3", ("SBG-50", "SBG-38")), ("GRANULAR_BASE", "INV-ART-330", "Tabla 330-3", ("BG-40", "BG-27", "BG-38", "BG-25"))):
        for grading in gradings:
            add(f"{material.lower()}-{grading.lower()}-working-formula", material, "GRADATION", standard, text="Tolerancias sobre la fórmula de trabajo: consultar el grupo de tamices aplicable en la tabla normativa.", grading=grading, source=table, status=PENDING_VERIFICATION)
        add(f"{material.lower()}-modified-compaction", material, "MODIFIED_COMPACTION", standard, text="Ensayo periódico de compactación modificada según la tabla de verificaciones.", source="Tabla 320-4" if material == "GRANULAR_SUBBASE" else "Tabla 330-4")

    # No se inventan límites NTC 174: se registra condición, método y estado pendiente.
    for material, label, tests in (("FINE_AGGREGATE", "Agregado fino", ("AGGREGATE_SAMPLING", "AGGREGATE_GRADATION_NTC_77", "MATERIAL_FINER_75UM", "ORGANIC_IMPURITIES", "ORGANIC_IMPURITIES_STRENGTH", "AGGREGATE_SULFATE_SOUNDNESS_NTC_126", "CLAY_LUMPS_NTC_589", "LIGHTWEIGHT_PARTICLES", "ALKALI_AGGREGATE_REACTIVITY")), ("COARSE_AGGREGATE", "Agregado grueso", ("AGGREGATE_SAMPLING", "AGGREGATE_GRADATION_NTC_77", "MATERIAL_FINER_75UM", "CLAY_LUMPS_NTC_589", "LIGHTWEIGHT_PARTICLES", "AGGREGATE_SULFATE_SOUNDNESS_NTC_126", "LOS_ANGELES_NTC_98", "LOS_ANGELES_NTC_93", "ALKALI_AGGREGATE_REACTIVITY"))):
        for test in tests:
            add(f"ntc174-{material.lower()}-{test.lower()}", material, test, "NTC-174", text="Requisito condicionado por clase de exposición, tamaño nominal, tipo de concreto o condición aplicable; confirmar límites en NTC 174:2018.", condition=label, source="NTC 174:2018; copia licenciada no disponible", status=PENDING_VERIFICATION)
    return rows


def _gradation(add, prefix, material, grading, sieves, source):
    standard = "INV-ART-320" if material == "GRANULAR_SUBBASE" else "INV-ART-330"
    for index, (sieve, minimum, maximum) in enumerate(sieves):
        add(f"{prefix}-{grading.lower()}-{index}", material, "GRADATION", standard, minimum=minimum, maximum=maximum, unit="% pasa", operator="rango", condition=f"Tamiz {sieve}", grading=grading, source=source)
