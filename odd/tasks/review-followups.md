# TODO — mañana: investigar causalidad de los hallazgos severos del quality-gate (mes 2 agenda)

> Originó: review nativa RDD del commit `fa63fdc` (feature `97fa18d`, base `e07b3fa`), que escaló a `stop` por causalidad desconocida con 10 hallazgos severos. RDD quedó desactivado **clone-scoped** (decisión del usuario, opción D) — el delivery de `97fa18d` se hizo por política ordinaria con merge vía PR.
>
> Estos hallazgos NO fueron reparados ni descartados: quedaron como follow-ups con causalidad sin determinar. Está TODO para descartar causalidad y decidir fijarlo/descartarlo.

## Hallazgos severos a investigar (10)

| ID | Hallazgo | Lente | Estado |
|----|---------|-------|--------|
| R2-1 | — | Readability | 🔍 causalidad pendiente |
| R2-2 | — | Readability | 🔍 causalidad pendiente |
| R3-1 | — | Reliability | 🔍 causalidad pendiente |
| R3-2 | — | Reliability | 🔍 causalidad pendiente |
| R3-3 | — | Reliability | 🔍 causalidad pendiente |
| R3-4 | — | Reliability | 🔍 causalidad pendiente |
| R3-5 | — | Reliability | 🔍 causalidad pendiente |
| R4-1 | — | Resilience | 🔍 causalidad pendiente |
| R4-2 | — | Resilience | 🔍 causalidad pendiente |
| R4-3 | — | Resilience | 🔍 causalidad pendiente |

> Nota: el contenido textual de cada hallazgo vive en el artifact de review (lineage `lineage-...` del commit `fa63fdc`). Este doc es el tracker de seguimiento, no reemplaza el contenido del artifact.

## Verificación (cómo se cierra cada uno)
- [ ] Reproducir/confirmar el hallazgo contra el código actual (`main`@... después del merge + push de mes 2).
- [ ] Determinar causa raíz o descartar con evidencia.
- [ ] Dejar decisión: fix aplicado en un work-unit | issue documentado | descartado (con motivo).

## Enlace
- Feature doc del mes 1 (fundaciones): `odd/tasks/fundaciones.md`
- Propuesta/roadmap: `propuesta.md` (sección 7, mes 2 = Agente + ingesta)
