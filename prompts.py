"""
prompts.py
----------
Módulo de construcción de prompts para la generación de artículos con IA.

Responsabilidades:
- Generar el prompt de artículo completo para la llamada principal a la IA
  (título + resumen + cuerpo HTML + keywords).
- Generar el prompt ligero para regenerar únicamente el título de un artículo
  (más económico que regenerar todo el artículo).
- Enviar el prompt de generación por email como herramienta de depuración
  (cuando ``SEND_PROMPT_EMAIL=true``).

Los prompts generados incluyen instrucciones detalladas de SEO on-page:
estructura de encabezados (h1 > h2 > h3), sección FAQ, CTA, código de ejemplo,
keywords en contexto y formato JSON de respuesta estricto.
"""
from __future__ import annotations

import config
from utils import html_escape
from notifications import send_notification_email


def build_generation_prompt(parent_name: str, subcat_name: str, tag_text: str | None = None, title: str | None = None, avoid_titles: list[str] | None = None, language: str = config.ARTICLE_LANGUAGE) -> str:
    """Construye el prompt completo para generar un artículo técnico SEO con IA.

    Instruye a la IA para que devuelva un JSON estricto con los campos:
    ``title``, ``summary``, ``body`` (HTML semántico) y ``keywords`` (lista).

    Instrucciones SEO incluidas en el prompt:

    - ``title``: optimizado para SEO y CTR, ≤ 60 caracteres con keyword principal
      al inicio. Si se proporciona *title*, se instruye a la IA a usarlo exactamente.
    - ``summary``: meta-descripción SEO ≤ 160 caracteres con keyword y CTA implícito.
    - ``keywords``: 5-7 palabras clave long-tail en minúsculas.
    - ``body``: HTML semántico con ``<h1>``, 3-5 secciones ``<h2>``, subsecciones
      ``<h3>``, bloques ``<pre><code>``, FAQ y sección de conclusión/CTA.

    Args:
        parent_name:   Nombre de la categoría padre (p. ej. ``"Spring Boot"``).
        subcat_name:   Nombre de la subcategoría (p. ej. ``"Spring Security"``).
        tag_text:      Tema o tag del artículo (p. ej. ``"JWT Authentication"``).
                       Si es ``None``, no se incluye en el prompt.
        title:         Título exacto a usar. Si se proporciona, la IA no genera
                       un título nuevo sino que usa éste.
        avoid_titles:  Lista de títulos a evitar (se incluyen hasta
                       ``MAX_AVOID_TITLES_IN_PROMPT`` en el prompt).
        language:      Código ISO 639-1 del idioma (por defecto ``config.ARTICLE_LANGUAGE``).

    Returns:
        Cadena de texto con el prompt listo para enviar a la IA.
    """
    avoid_titles = avoid_titles or []
    avoid_block = ""
    if avoid_titles:
        avoid_list = [t.replace('"', '\"') for t in avoid_titles[:config.MAX_AVOID_TITLES_IN_PROMPT]]
        avoid_block = (
            "\nEvita títulos iguales o muy similares a: "
            + "; ".join(f'"{t}"' for t in avoid_list)
        )
    lang = config._language_name(language)
    topic = f'sobre "{tag_text}" ' if tag_text else ""
    if title:
        title_instruction = f'title: usa EXACTAMENTE este título: "{title}". No lo modifiques.'
    else:
        title_instruction = "title: optimizado para SEO y CTR, conciso (máx. 60 caracteres), incluye palabra clave principal al inicio."
    return f"""Artículo SEO en {lang} {topic}(categoría: "{parent_name}", subcategoría: "{subcat_name}").
Devuelve SOLO JSON: {{"title":"...","summary":"...","body":"...","keywords":[...]}}

{title_instruction}
summary: meta-descripción SEO (máx. 160 caracteres), incluye palabra clave, llamada a la acción implícita.
keywords: 5-7 palabras clave SEO en minúsculas (long-tail incluidas), sin repetir el título exacto.
body (HTML semántico bien cerrado, optimizado para SEO on-page):
- <h1> con título (sin emojis), palabra clave principal incluida.
- Intro <p> que enganche, presente el problema y contenga la keyword principal.
- 3-5 secciones <h2> con keywords secundarias: explicación técnica, buenas prácticas, casos reales.
- Subsecciones <h3> donde sea necesario para profundizar.
- Código en <pre><code class="language-...">. Funcional, copiable, con comentarios descriptivos.
- Usa <strong> y <em> para resaltar términos clave (sin abusar).
- <h2> FAQ (Preguntas frecuentes): 3-5 preguntas en <h3> con respuestas en <p>. Redacta preguntas como búsquedas reales de usuarios.
- <h2> Conclusión con resumen de puntos clave y CTA (llamada a la acción).
- Listas <ul>/<ol> para ventajas, pasos o comparativas.
- Párrafos cortos (3-4 líneas máx.) para mejorar la legibilidad.

Tono profesional, sin relleno. JSON con comillas escapadas.{avoid_block}
"""

def build_title_prompt(parent_name: str, subcat_name: str, tag_text: str | None = None, avoid_titles: list[str] | None = None, language: str = config.ARTICLE_LANGUAGE) -> str:
    """Construye un prompt ligero para regenerar únicamente el título de un artículo.

    Mucho más económico que :func:`build_generation_prompt` porque solo pide
    el título, sin resumen, cuerpo ni keywords. Se usa en el bucle de
    deduplicación de títulos (Fase 2) cuando el título generado en la Fase 1
    es demasiado similar a uno existente.

    Instrucciones incluidas:
    - Título atractivo y conciso (≤ ``META_TITLE_MAX_LENGTH`` caracteres, por defecto 60).
    - Optimizado para SEO con la keyword principal.
    - Lista de títulos a evitar (hasta ``MAX_AVOID_TITLES_IN_PROMPT``).
    - Respuesta únicamente con el texto del título, sin comillas ni texto adicional.

    Args:
        parent_name:   Nombre de la categoría padre.
        subcat_name:   Nombre de la subcategoría.
        tag_text:      Tema o tag del artículo. Si es ``None``, no se incluye.
        avoid_titles:  Lista de títulos a evitar.
        language:      Código ISO 639-1 del idioma (por defecto ``config.ARTICLE_LANGUAGE``).

    Returns:
        Cadena de texto con el prompt de título listo para enviar a la IA.
    """
    avoid_titles = avoid_titles or []
    avoid_block = ""
    if avoid_titles:
        avoid_list = [t.replace('"', '\\"') for t in avoid_titles[:config.MAX_AVOID_TITLES_IN_PROMPT]]
        avoid_block = (
            "\nEvita títulos iguales o muy similares a cualquiera de estos: "
            + "; ".join(f'"{t}"' for t in avoid_list)
        )
    lang = config._language_name(language)
    topic = f'para el tema "{tag_text}" ' if tag_text else ""
    return (
        f'Genera un título de artículo técnico en {lang} {topic}'
        f'(categoría: "{parent_name}", subcategoría: "{subcat_name}").\n'
        f"Requisitos: atractivo, conciso (máx. {config.META_TITLE_MAX_LENGTH} caracteres), "
        f"optimizado para SEO, incluye la palabra clave principal.{avoid_block}\n"
        "Devuelve ÚNICAMENTE el texto del título, sin comillas ni texto adicional."
    )

def email_generation_prompt(parent_name: str, subcat_name: str, tag_text: str | None = None, avoid_titles=None):
    """Construye el prompt de generación y lo envía por email para depuración.

    Solo envía el prompt; no llama a la IA ni parsea ninguna respuesta.
    Se activa cuando ``SEND_PROMPT_EMAIL=true`` en el entorno. Útil para
    revisar y auditar el contenido del prompt antes de la llamada real a la IA.

    Args:
        parent_name:  Nombre de la categoría padre.
        subcat_name:  Nombre de la subcategoría.
        tag_text:     Tema o tag del artículo. Si es ``None``, no se incluye.
        avoid_titles: Lista de títulos a evitar (se pasa a :func:`build_generation_prompt`).

    Returns:
        El prompt generado como cadena de texto (también lo envía por email).
    """
    prompt = build_generation_prompt(parent_name, subcat_name, tag_text, avoid_titles=avoid_titles)
    html = f"<h3>Prompt de generación</h3><p>Se envía el prompt que se usará con OpenAI:</p><pre style=\"white-space:pre-wrap; word-break:break-word;\">{html_escape(prompt)}</pre>"
    send_notification_email(subject="Prompt de generación", html_body=html, text_body=prompt)
    return prompt
