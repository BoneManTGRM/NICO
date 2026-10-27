"""Exact authored function-observation copy; opaque method/value tokens stay literal."""
from __future__ import annotations

import re

from nico.source_function_measurement_report_v1 import LIMITS, UNAVAILABLE

COPY_ES = {
    LIMITS: (
        'Las observaciones se refieren únicamente a las funciones enumeradas en el código fuente proporcionado. '
        'La conformidad calificada con CC<=20 se informa por separado y se excluye de la madurez general; la calidad arquitectónica general sigue sin establecerse. '
        'Completo significa la población enumerada de un archivo, no la cobertura completa del repositorio. Las observaciones parciales del analizador sintáctico se informan por separado. '
        'La carga de decisiones de todo el código fuente y los residuos de inicializadores de módulos y clases no están disponibles; no se enumeran las funciones lambda de Python. '
        'Los lenguajes utilizan reglas de conteo diferentes. La extracción puede reducir la CC máxima sin reducir sum(CC-1); ninguna de las dos constituye una puntuación de calidad calibrada. '
        'Los conteos absolutos incluyen observaciones fuera de las 50 ubicaciones críticas principales conservadas; no se infieren ubicaciones adicionales. '
        'La interpretación existente del subconjunto puntuado, las ponderaciones, la puntuación de complejidad deshabilitada y el indicador indirecto de velocidad dependiente no cambian.'
    ),
    UNAVAILABLE: 'Mediciones de funciones no disponibles: ausentes, inválidas o sin vinculación independiente con este encargo, instantánea e inventario de código fuente.',
    'Function measurement availability': 'Disponibilidad de las mediciones de funciones',
    'Function measurement scope': 'Alcance de las mediciones de funciones',
    'Bound source observations; scoped conformance reported separately': 'Observaciones vinculadas al código fuente; conformidad del alcance informada por separado',
    'Supplied eligible source files': 'Archivos de código fuente elegibles proporcionados',
    'Complete observed files': 'Archivos observados completos',
    'Partial observed files': 'Archivos observados parciales',
    'Missing files': 'Archivos faltantes',
    'Unsupported files': 'Archivos no compatibles',
    'Enumerated functions': 'Funciones enumeradas',
    'Sum(CC-1) in enumerated functions': 'Suma(CC-1) en las funciones enumeradas',
    'Excluded from scope': 'Excluido del alcance',
    'Function-level complexity measurement completed with Python AST and bounded JavaScript/TypeScript function extraction; module aggregate complexity remains separately disclosed.':
        'La medición de complejidad por función se completó con AST de Python y extracción acotada de funciones de JavaScript/TypeScript; la complejidad agregada de módulos se sigue declarando por separado.',
}


def translate_function_measurement_copy(value: str) -> str | None:
    if value in COPY_ES:
        return COPY_ES[value]
    match = re.fullmatch(r'(CC|NESTING|LOC) (measured functions|missing functions|maximum)', value)
    if match:
        dimension = {'CC':'CC','NESTING':'ANIDAMIENTO','LOC':'LOC'}[match[1]]
        return {'measured functions':f'Funciones medidas de {dimension}',
                'missing functions':f'Funciones sin medición de {dimension}',
                'maximum':f'Máximo de {dimension}'}[match[2]]
    match = re.fullmatch(r'(CC|NESTING|LOC) at least ([0-9]+): functions', value)
    if match:
        dimension = {'CC':'CC','NESTING':'ANIDAMIENTO','LOC':'LOC'}[match[1]]
        return f'{dimension} de al menos {match[2]}: funciones'
    match = re.fullmatch(r'CC ([0-9]+): functions', value)
    if match:
        return f'CC {match[1]}: funciones'
    match = re.fullmatch(r'(CC distribution — )?(Complete observed population|Partial observed population \(parser incomplete\)): ([A-Za-z0-9_+.-]+) / ([A-Za-z0-9_+.-]+)', value)
    if match:
        prefix = 'Distribución de CC — ' if match[1] else ''
        population = 'Población observada completa' if match[2] == 'Complete observed population' else 'Población observada parcial (analizador sintáctico incompleto)'
        return f'{prefix}{population}: {match[3]} / {match[4]}'
    return None
