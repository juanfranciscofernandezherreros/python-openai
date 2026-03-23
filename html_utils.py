"""
html_utils.py
-------------
Utilidades de procesamiento HTML para el generador de artículos.

Responsabilidades:
- Reemplazar o insertar el elemento ``<h1>`` en el cuerpo HTML generado.
- Extraer el texto plano de un cuerpo HTML (eliminando todas las etiquetas).
- Contar las palabras de un cuerpo HTML.
- Estimar el tiempo de lectura de un artículo a partir de su HTML.

Todas las funciones operan sobre cadenas de texto y no tienen efectos
secundarios ni dependencias externas al proyecto.
"""
from __future__ import annotations

import math
import re

from utils import html_escape


def _replace_h1(body: str, title: str) -> str:
    """Reemplaza el primer ``<h1>`` del cuerpo HTML con *title*, o lo antepone si no existe.

    Escapa *title* con :func:`~utils.html_escape` antes de insertarlo para evitar
    inyección HTML en el cuerpo del artículo.

    Args:
        body:  Cuerpo HTML del artículo.
        title: Nuevo texto del título (se escapará automáticamente).

    Returns:
        Cuerpo HTML con el ``<h1>`` actualizado.
    """
    escaped_title = html_escape(title)
    new_body, replacements = re.subn(
        r'<h1[^>]*>.*?</h1>', f'<h1>{escaped_title}</h1>',
        body, count=1, flags=re.DOTALL | re.IGNORECASE,
    )
    if not replacements:
        new_body = f'<h1>{escaped_title}</h1>\n' + body
    return new_body

def extract_plain_text(html: str) -> str:
    """Elimina todas las etiquetas HTML de *html* y devuelve el texto plano resultante.

    Reemplaza cada etiqueta por un espacio y colapsa los espacios múltiples.
    Útil para contar palabras o calcular el tiempo de lectura sin incluir
    el marcado HTML.

    Args:
        html: Cadena HTML de entrada.

    Returns:
        Texto plano sin etiquetas, con espacios normalizados. Cadena vacía si
        *html* es ``None`` o vacío.
    """
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()

def count_words(html: str) -> int:
    """Cuenta las palabras del texto plano obtenido de *html*.

    Extrae el texto plano con :func:`extract_plain_text` y divide por espacios.

    Args:
        html: Cuerpo HTML del artículo.

    Returns:
        Número de palabras (``0`` si *html* está vacío o no contiene texto).
    """
    text = extract_plain_text(html)
    return len(text.split()) if text else 0

def estimate_reading_time(body_html: str, wpm: int = 230) -> int:
    """Estima el tiempo de lectura de *body_html* en minutos.

    Calcula ``ceil(palabras / wpm)`` con un mínimo de 1 minuto.
    La velocidad media de lectura por defecto es 230 palabras por minuto (WPM),
    valor típico para lectura de contenido técnico.

    Args:
        body_html: Cuerpo HTML del artículo.
        wpm:       Palabras por minuto del lector medio (por defecto ``230``).

    Returns:
        Tiempo de lectura estimado en minutos enteros (mínimo ``1``).
    """
    words = count_words(body_html)
    return max(1, math.ceil(words / wpm))
