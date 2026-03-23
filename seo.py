"""
seo.py
------
Funciones de optimización SEO para el generador de artículos.

Responsabilidades:
- Construir la URL canónica del artículo (``canonicalUrl``) a partir del
  dominio base y el slug.
- Generar los datos estructurados **JSON-LD** en formato Schema.org de tipo
  ``TechArticle``, que Google y otros motores de búsqueda usan para mostrar
  resultados enriquecidos (*rich snippets*).

El JSON-LD generado incluye: ``headline``, ``description``, ``author``,
``datePublished``, ``dateModified``, ``wordCount``, ``timeRequired``,
``inLanguage``, ``keywords``, ``articleSection``, ``url``,
``mainEntityOfPage``, ``publisher`` y ``about``.
"""
from __future__ import annotations

from typing import Any

import config


def build_canonical_url(site: str, slug: str) -> str:
    """Construye la URL canónica del artículo a partir del dominio y el slug.

    La URL se forma como ``{site}/post/{slug}``. La barra final de *site*
    se elimina automáticamente para evitar dobles barras.

    Args:
        site: URL base del sitio web (p. ej. ``https://tusitio.com``).
        slug: Slug URL-seguro del artículo (p. ej. ``como-usar-data-en-lombok``).

    Returns:
        URL canónica completa, o cadena vacía si *site* o *slug* están vacíos.

    Examples::

        build_canonical_url("https://tusitio.com", "como-usar-jwt")
        # → "https://tusitio.com/post/como-usar-jwt"
    """
    if not site or not slug:
        return ""
    base = site.rstrip("/")
    return f"{base}/post/{slug}"

def build_json_ld_structured_data(
    title: str,
    summary: str,
    canonical_url: str,
    keywords: list[str],
    author_name: str,
    date_published: str,
    date_modified: str,
    word_count: int,
    reading_time: int,
    category_name: str,
    tag_names: list[str],
    site: str,
    language: str = config.ARTICLE_LANGUAGE,
) -> dict:
    """Genera datos estructurados JSON-LD (Schema.org ``TechArticle``) para el artículo.

    Estos datos permiten a los motores de búsqueda (Google, Bing, etc.) entender
    mejor el contenido y mostrarlo en resultados enriquecidos (*rich snippets*).
    El diccionario devuelto debe incluirse en el campo ``structuredData`` del
    documento JSON del artículo.

    Campos incluidos siempre:
        ``@context``, ``@type``, ``headline``, ``description``, ``author``,
        ``datePublished``, ``dateModified``, ``wordCount``, ``timeRequired``,
        ``inLanguage``, ``keywords``, ``articleSection``.

    Campos opcionales (solo si los parámetros correspondientes no están vacíos):
        ``url``, ``mainEntityOfPage`` (si *canonical_url* no está vacío),
        ``publisher`` (si *site* no está vacío),
        ``about`` (si *tag_names* no está vacío).

    Args:
        title:          Título del artículo (se trunca a 110 caracteres en ``headline``).
        summary:        Resumen del artículo (se trunca a 200 caracteres en ``description``).
        canonical_url:  URL canónica del artículo.
        keywords:       Lista de palabras clave SEO.
        author_name:    Nombre del autor del artículo.
        date_published: Fecha de publicación en formato ISO 8601.
        date_modified:  Fecha de última modificación en formato ISO 8601.
        word_count:     Número de palabras del artículo.
        reading_time:   Tiempo de lectura estimado en minutos.
        category_name:  Nombre de la subcategoría (``articleSection``).
        tag_names:      Lista de nombres de tags (``about``).
        site:           URL base del sitio para el campo ``publisher``.
        language:       Código ISO 639-1 del idioma (por defecto ``config.ARTICLE_LANGUAGE``).

    Returns:
        Diccionario con los datos estructurados JSON-LD listos para serializar.
    """
    base_url = site.rstrip("/") if site else ""
    data: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "TechArticle",
        "headline": title[:110],
        "description": summary[:200],
        "author": {
            "@type": "Person",
            "name": author_name,
        },
        "datePublished": date_published,
        "dateModified": date_modified,
        "wordCount": word_count,
        "timeRequired": f"PT{reading_time}M",
        "inLanguage": language,
        "keywords": ", ".join(keywords) if keywords else "",
        "articleSection": category_name,
    }
    if canonical_url:
        data["url"] = canonical_url
        data["mainEntityOfPage"] = {"@type": "WebPage", "@id": canonical_url}
    if base_url:
        data["publisher"] = {
            "@type": "Organization",
            "name": base_url.replace("https://", "").replace("http://", ""),
            "url": base_url,
        }
    if tag_names:
        data["about"] = [{"@type": "Thing", "name": t} for t in tag_names]
    return data
