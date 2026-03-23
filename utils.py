"""
utils.py
--------
Funciones auxiliares genéricas utilizadas por todos los submódulos del proyecto.

Responsabilidades:
- Conversión y normalización de tipos de datos básicos.
- Generación de slugs URL-seguros a partir de texto Unicode.
- Detección de similitud entre cadenas de texto (para deduplicación de títulos).
- Escapado de HTML para el cuerpo de los emails de notificación.
- Obtención del timestamp UTC actual.

Todas las funciones son puras (sin efectos secundarios), fácilmente testeables
y sin dependencias externas al proyecto.
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any


def str_id(x: Any) -> str:
    """Convierte *x* a cadena de texto usando ``str()``.

    Útil para normalizar identificadores que pueden llegar como ``ObjectId``,
    ``int`` u otros tipos a un ``str`` uniforme.
    """
    return str(x)

def as_list(v: Any) -> list:
    """Garantiza que el valor devuelto sea siempre una ``list``.

    - Si *v* es ``None``, devuelve ``[]``.
    - Si ya es una lista, tupla o conjunto, devuelve ``list(v)``.
    - En cualquier otro caso, envuelve *v* en una lista de un elemento.
    """
    if v is None: return []
    if isinstance(v, (list, tuple, set)): return list(v)
    return [v]

def tag_name(t: dict[str, Any]) -> str:
    """Extrae el nombre de un objeto tag/categoría en formato diccionario.

    Busca en orden las claves ``"name"``, ``"tag"`` y ``"_id"`` y devuelve
    el primer valor no nulo encontrado como cadena.

    Args:
        t: Diccionario con al menos una de las claves ``name``, ``tag`` o ``_id``.

    Returns:
        El nombre del tag como cadena de texto.
    """
    return str(t.get("name") or t.get("tag") or t.get("_id"))

def slugify(text: str) -> str:
    """Convierte *text* en un slug URL-seguro en minúsculas.

    Proceso:
    1. Normaliza a NFD para separar caracteres base de sus diacríticos.
    2. Elimina los caracteres combinantes (acentos, tildes, etc.).
    3. Convierte a minúsculas.
    4. Reemplaza cualquier secuencia de caracteres no alfanuméricos por ``-``.
    5. Elimina guiones al inicio y al final.

    Ejemplos::

        slugify("Cómo usar @Data en Lombok") → "como-usar-data-en-lombok"
        slugify("  Spring Boot 3  ")         → "spring-boot-3"

    Args:
        text: Texto de entrada (puede contener Unicode, espacios y símbolos).

    Returns:
        Slug limpio y URL-seguro.
    """
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"^-+|-+$", "", text)
    return text

def normalize_for_similarity(s: str) -> str:
    """Normaliza una cadena de texto para compararla con ``similar_ratio``.

    Aplica las siguientes transformaciones para que la comparación sea
    insensible a mayúsculas, tildes y separadores:

    1. Normalización NFD + eliminación de diacríticos.
    2. Conversión a minúsculas.
    3. Reemplazo de caracteres no alfanuméricos por espacio.
    4. Colapso de espacios múltiples y recorte de extremos.

    Args:
        s: Cadena a normalizar.

    Returns:
        Cadena normalizada, o ``""`` si la entrada está vacía.
    """
    if not s: return ""
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = s.lower()
    s = re.sub(r"[\W_]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def similar_ratio(a: str, b: str) -> float:
    """Calcula la ratio de similitud entre dos cadenas en el rango [0.0, 1.0].

    Usa :class:`difflib.SequenceMatcher` sobre las versiones normalizadas
    (sin tildes, en minúsculas, sin separadores especiales) de *a* y *b*.

    Args:
        a: Primera cadena.
        b: Segunda cadena.

    Returns:
        Valor entre ``0.0`` (completamente distintas) y ``1.0`` (idénticas).
        Devuelve ``0.0`` si alguna cadena está vacía tras la normalización.
    """
    a_norm, b_norm = normalize_for_similarity(a), normalize_for_similarity(b)
    if not a_norm or not b_norm: return 0.0
    return difflib.SequenceMatcher(None, a_norm, b_norm).ratio()

def is_too_similar(title: str, candidates: list, threshold: float = 0.82) -> bool:
    """Determina si *title* es demasiado similar a algún candidato de la lista.

    Compara *title* con cada elemento de *candidates* usando :func:`similar_ratio`.
    Si alguna comparación supera o iguala *threshold*, devuelve ``True``.

    Se usa en la lógica de deduplicación de títulos para evitar generar artículos
    con títulos repetidos o casi idénticos.

    Args:
        title:      Título candidato a verificar.
        candidates: Lista de títulos ya existentes contra los que comparar.
        threshold:  Umbral de similitud (por defecto ``0.82``). El módulo
                    ``config`` define ``SIMILARITY_THRESHOLD_STRICT = 0.86``
                    para el bucle de reintentos de título.

    Returns:
        ``True`` si *title* es demasiado similar a algún candidato; ``False`` en caso contrario.
    """
    for c in candidates:
        if similar_ratio(title, c) >= threshold:
            return True
    return False

def now_utc():
    """Devuelve el instante actual como objeto :class:`~datetime.datetime` con zona horaria UTC.

    Returns:
        :class:`datetime.datetime` consciente de zona horaria (``tzinfo=timezone.utc``).
    """
    return datetime.now(tz=timezone.utc)

def html_escape(s: str) -> str:
    """Escapa los caracteres especiales HTML de *s* para insertarlos con seguridad en HTML.

    Reemplaza ``&`` → ``&amp;``, ``<`` → ``&lt;`` y ``>`` → ``&gt;``.
    Suficiente para el cuerpo de los emails HTML generados por este proyecto.

    Args:
        s: Cadena de texto a escapar.

    Returns:
        Cadena con los caracteres HTML especiales escapados.
    """
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
    )
