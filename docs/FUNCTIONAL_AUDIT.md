# Auditoría funcional integral de CivilLab Suite

Fecha de verificación: 2026-10-04. Trabajo sobre datos temporales y sintéticos; no se migraron las bases personales durante el desarrollo.

## Diagnóstico y correcciones

Se confirmó físicamente la existencia de los tres archivos de producción legacy en el perfil local: `CivilLabSuite/core.sqlite3`, `ConcreteMixDesignerACI/materials.sqlite3` y `CivilLabSuite/prefabricados/precon_lab.db`. Se inspeccionaron Core, adapters, repositorios, esquemas, servicios, UI, portabilidad, pruebas, dependencias y scripts de distribución.

| Categoría / hallazgo | Esperado y causa observada | Corregido | Prueba | Riesgo o límite |
|---|---|---|---|---|
| Crítico / arquitectura | Un laboratorio; tres SQLite operativos y tablas homónimas | Un archivo Core con tablas `concretos_*` y `prefabricados_*` | `test_legacy_migration_is_lossless_backed_up_and_idempotent` | Cerrar otras instancias al migrar/restaurar |
| Integridad / conexiones | Reemplazo seguro; el contexto sqlite3 confirma pero no cierra conexiones | Conexiones cerradas, checkpoint WAL y liberación del pool | `test_restore_checkpoints_old_wal_before_replacing` | Un proceso externo puede bloquear el reemplazo; se conserva respaldo |
| Integridad / recuperación | No publicar una migración parcial | Conversión en staging, backup previo, conteos, integrity/FK, publicación final | `test_interrupted_migration_keeps_originals_and_retry_succeeds` | Tablas legacy desconocidas se rechazan, no se descartan |
| Funcional / portabilidad | Export/import y entorno vacío reversibles | Formato 2, conversión de v1, respaldo antes de sustituir y rollback | `test_import_v1_converts_before_replacing_unified_workspace`, `test_demo_e2e_new_environment_restore_and_calendar` | Reinicio de la aplicación después de restaurar |
| Integridad / materiales | Una identidad; guardado material/caracterización podía ser parcial | FK a material_objects, reutilización de código, transacción única y borrado protegido | `test_material_atomic_crud_snapshots_and_safe_delete`, `test_same_identity_two_areas_and_revoked_result_reopens_obligation` | Materiales legacy sin código reciben uno; no se fusionan nombres ambiguos |
| Cálculo / resistencia | Cada observación debe ser un ensayo; antes se contaban cilindros y s=0 con N=1 | StrengthTest por producción/edad, rechazo de muestras incompletas, s no estimable con N=1 | `test_strength_basis.py` | Una muestra por producción y edad; ver criterio abajo |
| Cálculo / f’cr | Separar f’c, media histórica y f’cr | Dos modos, N/s/factor/periodo/serie visibles, snapshot y sugerencia basada en f’cr | `test_statistical_equations_and_snapshot`, smoke Qt de demo | La comparabilidad y el curado estándar requieren confirmación técnica |
| Cálculo / solver | Cerrar pasta, mortero y mezclas no convencionales | Ecuaciones simultáneas, proyección determinista no negativa y restricciones manuales inalterables | `test_solver_matrix.py` y tests existentes | No sustituye validación experimental de la formulación |
| Usabilidad / candados | Cantidad controlada no debe parecer libre | Candado efectivo separado del manual, tooltip y edición bloqueada por relaciones/a-mc | `test_workspace_disables_only_active_relation_numerator` | Desactivar una relación conserva cualquier otro control activo |
| Funcional / humedad | Humedad actual por amasada, no solo valor del maestro | Entradas en Dosificación/Producción, corrección única y snapshot inmutable; PDF/CSV usan humedad operativa | `test_batch_moisture_on_od_base_overrides_legacy`, smoke Qt | Valores legacy se presentan como referencia para verificar |
| Funcional / calendario | Reprogramaciones visibles fuera de ventana y sin duplicados | Proyección incluye origen remoto y excluye fecha antigua | `test_pie_rescheduling_across_projection_windows_is_not_duplicated` | Preparación y resultados conservan estados distintos |
| Integridad / resultados | Invalidar un resultado debe retirar la satisfacción PIE | Se invalidan enlaces derivados; calendario refleja satisfacciones vigentes | `test_same_identity_two_areas_and_revoked_result_reopens_obligation` | Registro de referencias compartidas disponible en servicio Core |
| Funcional / Prefabricados | No registrar datos inválidos ni reprogramar muestras ya ensayadas | Validación de fecha, finitud, signo y resultado obligatorio; cierre de tarea terminal | `test_invalid_provisional_result_does_not_change_sample` | Las tareas preparatorias no se completan ficticiamente al cargar resultados |
| Rendimiento | Evitar consultas por cada material visible | Caracterizaciones/granulometrías en dos consultas y conservación de selección | Pruebas CRUD/Qt y dataset integral | No se realizó benchmark de millones de registros |
| Mantenibilidad / cobertura | Verificación completa | Limpieza Ruff, diagnóstico ejecutable y 57 casos adicionales | 205 pruebas totales | No se generó instalador nuevo |

## Arquitectura y migración

La ruta normal de producción es `%LOCALAPPDATA%/CivilLabSuite/core.sqlite3` (sobrescribible mediante `CIVILLAB_SUITE_DATA_DIR`). Las interfaces permanecen separadas. El lanzamiento legacy de Prefabricados entra por el ciclo de inicio de Suite. Suelos sigue deshabilitado.

Core conserva identidades de materiales, tipos, ensayos, métodos, normas, PIE y referencias de resultados. Las tablas especializadas tienen prefijos de dominio. Los catálogos legacy de Prefabricados se conservan para migración/compatibilidad; la UI compartida usa Core. Los IDs antiguos de productos, producciones, probetas y materiales se conservan; `concretos_materials.canonical_id` referencia la identidad común. No se altera el JSON de diseños/producciones históricos durante la migración.

Esquema Core v3 y marcador `workspace_migrations` v1. JSON de diseño v2 añade `format_version`, `batch_moistures`, `fcr_mpa`, `strength_basis_snapshot` y referencias canónicas del material. JSON sin versión sigue migrando reglas ocultas legacy una sola vez al cargar; diseños v2 no regeneran relaciones eliminadas.

`storage.migrate_workspace` valida las fuentes y toma snapshots completos SQLite en `backups/migration-<fecha>-<id>/`. Renombra y copia tablas en un directorio temporal, conserva secuencias/autoincrementos, valida conteos/FK/integridad e inicializa las estructuras faltantes. Solo publica al finalizar. Se probó además con copias de los tres archivos reales; esas copias y respaldos de ensayo están en `.pytest_cache/legacy_actual_copy/`. Los originales no se borran.

El formato `.civillab` v2 transporta una base y las preferencias funcionales. Conserva checksum, tamaño, protección de rutas y validación SQLite; importa v1 mediante conversión previa. “Nuevo entorno de datos…” exporta primero un paquete y crea únicamente estructuras/catálogos necesarios. Respaldo habitual: `<directorio-suite>/backups/antes-de-nuevo-*.civillab` o `antes-de-importar-*.civillab`. El usuario debe reabrir Suite después del reemplazo.

## Propiedades y snapshots

- Identidad: Core (`material_objects`, código y tipo). Concretos referencia esa identidad.
- Caracterización: fuente, lote, proveedor, granulometría y mediciones. SSD medido tiene precedencia como gravedad de cálculo en guardado conjunto; para aditivos, densidad medida. Los campos legacy se preservan por compatibilidad.
- Operación: humedad de cada agregado en cada amasada. La humedad del maestro es referencia legacy.
- Diseño: relaciones, dosificaciones, restricciones y base estadística; no reglas ocultas del maestro.
- Historia: diseños guardados y producciones contienen snapshots. Editar el maestro o crear otra revisión no los reescribe. La producción conserva también su especificación y humedades.

## Resistencia: método y fuentes

Se implementa **ACI PRC-211.1-22 §4.7.4**, que remite a **ACI SPEC-301-20**, con las tablas en psi convertidas mediante `1 psi = 0.006894757293168361 MPa`. No se mezclan umbrales redondeados de una edición SI distinta.

Sin historial: f’cr = f’c + 1000 psi si f’c < 3000 psi; f’c + 1200 psi entre 3000 y 5000 psi; 1.1 f’c + 700 psi por encima. Con historial se toma el mayor de f’c + 1.34ks y f’c + 2.33ks − 500 psi (hasta 5000 psi), o 0.90f’c + 2.33ks (por encima). Factores: 15→1.16, 20→1.08, 25→1.03, ≥30→1.00; interpolación lineal permitida. [ACI PRC-211.1-22, tablas 4.7.4.1, 4.7.4.3 y 4.7.4.4](https://storethinghiem.vn/uploads/files/ACI%20211.1-22.pdf).

La unidad es el promedio de una muestra completa de la misma producción/edad. Criterio de probetas de las ediciones seleccionadas: al menos dos cilindros nominales de 150 mm o tres de 100 mm. Se excluyen canceladas, incompletas, dimensiones incompatibles y edades reales alejadas de la objetivo. La tolerancia informática de edad (2%, mínimo 0.1 días) y diámetro (5 mm) es un filtro explícito de esta implementación, no una atribución normativa de tolerancias ASTM. [ACI, FAQ sobre strength tests](https://www.concrete.org/frequentlyaskedquestions.aspx?faqid=13), [artículo ACI/Concrete International de noviembre de 2024](https://www.nrmca.org/wp-content/uploads/CI4611Snell.pdf).

No se combinan revisiones/diseños automáticamente. Se exige una revisión seleccionada, N≥15, al menos 45 días, datos dentro de 24 meses y confirmación de comparabilidad/curado. La UI verifica que el f’c de la serie no difiera más de 1000 psi. [Presentación ACI 301, requisitos del historial](https://alconcrete.org/wp-content/uploads/2018/10/ACI-301-Presentation-bg-092618.pdf). El snapshot conserva los IDs/resultados incluidos, N, media, s muestral, factor, fechas, edad, serie, f’c/f’cr, ecuaciones y edición. N=1 tiene s no estimable, nunca cero inventado.

La selección de estas ediciones es explícita: no se afirma que se implementen todos los cambios de ACI 318-25. La sugerencia de agua y relación a/mc preexistente sigue siendo un punto de partida académico que requiere ensayos, no una verificación normativa integral.

## Humedad y solver

Para agregado en base SSD: `OD = SSD/(1+A)`, `masa húmeda = OD*(1+H)`, `agua libre = OD*(H−A)`; A/H son fracciones sobre masa seca. Agua a añadir = agua de diseño − suma de agua libre. Se admite demanda por agregado seco. Si hay exceso, se limita el agua a cargar a cero y se muestra advertencia de exceso y cambio de relación efectiva. Las producciones guardan el mapa usado; PDF/CSV y detalle histórico lo recuperan.

El solver resuelve volumen, candados manuales y relaciones simultáneamente. Prefiere conservar cantidades independientes y la editada, relajando solo preferencias cuando es necesario. Usa eliminación de ecuaciones redundantes y búsqueda de límites no negativos; verifica residuales antes de aplicar resultados. Un conflicto conserva las cantidades y retorna `converged=False`. La persistencia permite mezclas experimentales/no convergentes con valores íntegros, y rechaza negativos/NaN/Inf.

## Evidencia final

- `pytest`: **205 passed in 26.62s**, suite completa, datos temporales.
- Ruff: **All checks passed!** (`src tests tools`).
- `compileall -q src tests`: correcto.
- SQLite `integrity_check`: **ok**; `foreign_key_check`: **sin filas** en base vacía, demo, migración y restauración.
- Importación/exportación y secuencia A→vacío→respaldo recuperan exactamente la base A en prueba automatizada.
- Fallo simulado antes de publicar migración y durante reemplazo: datos originales y respaldos recuperables.
- Smoke Qt abre ambos módulos sobre la demo y comprueba selector estadístico y edición operativa de humedades.
- Dos generaciones independientes con la misma fecha/semilla: **ninguna tabla con datos diferentes**. Los metadatos del ZIP de exportación registran la fecha real de exportación.
- Evidencia detallada: `artifacts/demo/diagnostics.json` y `artifacts/demo/validation.json`.

## Dataset y uso

Generador: `src/civillab_suite/demo.py`. Desde entorno con proyecto instalado o `PYTHONPATH=src`:

```powershell
python -m civillab_suite.demo --output artifacts/demo-nuevo --anchor 2026-10-04 --seed 2026
python -m civillab_suite.diagnostics artifacts/demo-nuevo/core.sqlite3
```

La fecha por defecto es hoy. Se rechaza sobrescribir una base existente. Usa repositorios/servicios normales, incluyendo la importación Excel de un resumen sintético; al final normaliza exclusivamente metadatos sintéticos para reproducibilidad.

Entrega: **`artifacts/demo/CivilLab-Demo-Integral.civillab`**. Contiene 10 materiales, 9 diseños/revisiones, 107 producciones, 856 probetas, 107 ensayos de fresco, 390 resultados de compresión, 130 de flexión; 3 productos, 36 producciones de Prefabricados, 96 muestras, 336 especímenes, 216 tareas, 30 resultados provisionales y 6 históricos importados. Core incluye 5 PIE, 3 resultados compartidos y 4 satisfacciones. Series de resistencia de **32, 18 y 5** ensayos. Hay concreto, mortero, pasta, filler, resultados bajos, pendientes/canceladas, tareas vencidas/actuales/futuras y reprogramadas.

## Pendientes y límites reales

La tarea no incluye publicar un instalador ni ejecutar la migración sobre los archivos personales. La validación de condiciones de curado, equivalencia de materiales y aceptación técnica sigue requiriendo al laboratorista. La agrupación representa una muestra por producción/edad; múltiples muestras independientes a la misma edad requieren una extensión explícita del modelo, no contar cilindros adicionales como N independientes. Se conserva compatibilidad de catálogos legacy, pero las pantallas compartidas utilizan Core. No se habilitó Suelos ni se añadieron dependencias.

## Inventario de archivos

Modificados (los cambios de una línea fuera del núcleo corresponden principalmente a Ruff):

- `src/civillab_suite/__main__.py`
- `src/civillab_suite/app.py`
- `src/civillab_suite/config.py`
- `src/civillab_suite/context.py`
- `src/civillab_suite/core/__init__.py`
- `src/civillab_suite/core/catalog.py`
- `src/civillab_suite/core/database.py`
- `src/civillab_suite/core/pie.py`
- `src/civillab_suite/core/results.py`
- `src/civillab_suite/data_portability.py`
- `src/civillab_suite/modules/concretos/adapter.py`
- `src/civillab_suite/modules/prefabricados/adapter.py`
- `src/civillab_suite/ui/calendar_page.py`
- `src/civillab_suite/ui/pie_page.py`
- `src/civillab_suite/ui/shell.py`
- `src/concrete_mix_designer/config.py`
- `src/concrete_mix_designer/data/calendar_repository.py`
- `src/concrete_mix_designer/data/database.py`
- `src/concrete_mix_designer/data/laboratory_repository.py`
- `src/concrete_mix_designer/domain/aci_seed.py`
- `src/concrete_mix_designer/domain/engine.py`
- `src/concrete_mix_designer/domain/laboratory_models.py`
- `src/concrete_mix_designer/domain/models.py`
- `src/concrete_mix_designer/services/app_state.py`
- `src/concrete_mix_designer/services/pdf_report.py`
- `src/concrete_mix_designer/services/report_preferences.py`
- `src/concrete_mix_designer/ui/dialogs/material_dialog.py`
- `src/concrete_mix_designer/ui/dialogs/pie_dialog.py`
- `src/concrete_mix_designer/ui/dialogs/production_dialogs.py`
- `src/concrete_mix_designer/ui/dialogs/ratio_constraint_dialog.py`
- `src/concrete_mix_designer/ui/pages/calendar_page.py`
- `src/concrete_mix_designer/ui/pages/dashboard_page.py`
- `src/concrete_mix_designer/ui/pages/design_library_page.py`
- `src/concrete_mix_designer/ui/pages/materials_page.py`
- `src/concrete_mix_designer/ui/pages/production_page.py`
- `src/concrete_mix_designer/ui/pages/results_page.py`
- `src/concrete_mix_designer/ui/pages/standards_page.py`
- `src/concrete_mix_designer/ui/pages/workspace_page.py`
- `src/concrete_mix_designer/ui/widgets/volume_stack.py`
- `src/precon_lab/__main__.py`
- `src/precon_lab/config.py`
- `src/precon_lab/database.py`
- `src/precon_lab/historical_queries.py`
- `src/precon_lab/importers.py`
- `src/precon_lab/inspection_catalog.py`
- `src/precon_lab/models.py`
- `src/precon_lab/services.py`
- `src/precon_lab/ui/historical_explorer.py`
- `src/precon_lab/ui/history_page.py`
- `tests/concretos/test_calendar_repository.py`
- `tests/concretos/test_engine.py`
- `tests/concretos/test_laboratory_repository.py`
- `tests/concretos/test_pie_calendar.py`
- `tests/concretos/test_repository_integration.py`
- `tests/concretos/test_ui_filter_selection.py`
- `tests/prefabricados/test_database_migrations.py`
- `tests/prefabricados/test_historical_queries.py`
- `tests/prefabricados/test_inspection_plan.py`
- `tests/prefabricados/test_scheduling.py`
- `tests/suite/conftest.py`
- `tests/suite/test_core_database.py`

Creados:

- `artifacts/demo/CivilLab-Demo-Integral.civillab`
- `artifacts/demo/Resumen-Demo.xlsx`
- `artifacts/demo/core.sqlite3`
- `artifacts/demo/diagnostics.json`
- `artifacts/demo/validation.json`
- `docs/FUNCTIONAL_AUDIT.md`
- `src/civillab_suite/demo.py`
- `src/civillab_suite/diagnostics.py`
- `src/civillab_suite/sqlite_support.py`
- `src/civillab_suite/storage.py`
- `src/concrete_mix_designer/domain/linear_solver.py`
- `src/concrete_mix_designer/domain/strength.py`
- `src/concrete_mix_designer/ui/moisture_widget.py`
- `tests/concretos/test_solver_matrix.py`
- `tests/concretos/test_strength_basis.py`
- `tests/suite/test_integrity_regressions.py`
- `tests/suite/test_unified_workspace.py`
