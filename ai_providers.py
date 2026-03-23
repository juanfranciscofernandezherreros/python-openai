"""
ai_providers.py
---------------
Abstracción de proveedores de IA para el generador de artículos.

Responsabilidades:
- Detectar qué proveedor de IA usar: OpenAI, Google Gemini u Ollama (local).
- Construir y ejecutar cadenas LangChain LCEL (``prompt | llm | StrOutputParser``).
- Extraer y parsear bloques JSON de las respuestas de la IA.
- Implementar reintentos con back-off exponencial para errores transitorios.

Proveedores soportados:
    **OpenAI (GPT)**
        Usa :class:`~langchain_openai.ChatOpenAI` con la clave ``OPENAIAPIKEY``.
        Modelos: ``gpt-4o``, ``gpt-4-turbo``, ``gpt-3.5-turbo``, etc.

    **Google Gemini**
        Usa :class:`~langchain_google_genai.ChatGoogleGenerativeAI` con la clave
        ``GEMINI_API_KEY``. Detectado cuando ``OPENAI_MODEL`` empieza por ``gemini-``
        o cuando ``AI_PROVIDER=gemini``.

    **Ollama (local)**
        Usa :class:`~langchain_openai.ChatOpenAI` con ``base_url=OLLAMA_BASE_URL``
        y una clave ficticia. No requiere clave de API. Detectado cuando
        ``OLLAMA_BASE_URL`` está definida o cuando ``AI_PROVIDER=ollama``.

Selección de proveedor:
    La variable ``AI_PROVIDER`` (``config.py``) permite forzar un proveedor:
    ``"auto"`` (por defecto), ``"openai"``, ``"gemini"`` u ``"ollama"``.
    El argumento CLI ``--provider`` sobreescribe esta variable en tiempo de ejecución.
"""
from __future__ import annotations

import json
import logging
import random
import re
import time as _time
from collections.abc import Callable
from typing import Any, Union

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

import config

logger = config.logger

# ====== Utilidades de parseo/IA ======
def _extract_json_block(text: str) -> str:
    """Extrae el primer bloque JSON del texto de respuesta de la IA.

    Soporta dos formatos habituales de respuesta:

    1. **Bloque de código cercado**: ````json { ... }``` `` o ```` ``` { ... }``` ``.
    2. **JSON suelto**: busca el primer ``{`` hasta el último ``}`` en el texto.

    Args:
        text: Texto de respuesta del modelo de IA.

    Returns:
        Cadena con el bloque JSON extraído y recortado, o cadena vacía si
        *text* es ``None`` o vacío.
    """
    if not text:
        return ""
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        return fence.group(1).strip()
    brace = re.search(r"\{.*\}", text, flags=re.DOTALL)
    return brace.group(0).strip() if brace else text.strip()

def _safe_json_loads(s: str) -> dict:
    """Parsea una cadena JSON con tolerancia a caracteres tipográficos.

    Primer intento con :func:`json.loads` estándar. Si falla, reemplaza
    las comillas tipográficas (``\u201c``, ``\u201d``) y la comilla
    derecha (``\u2019``) por sus equivalentes ASCII y reintenta.

    Args:
        s: Cadena JSON a parsear (posiblemente con comillas tipográficas).

    Returns:
        Diccionario Python resultante del parseo.

    Raises:
        :class:`json.JSONDecodeError`: Si el JSON no es válido incluso tras
        la sustitución de caracteres.
    """
    try:
        return json.loads(s)
    except Exception:
        s2 = s.replace("\u201c", "\"").replace("\u201d", "\"").replace("\u2019", "'")
        return json.loads(s2)

def _is_gemini_model(model: str) -> bool:
    """Determina si el proveedor de IA activo es Google Gemini.

    Lógica de detección (en orden de precedencia):

    1. Si ``AI_PROVIDER == "gemini"`` → siempre ``True``.
    2. Si ``AI_PROVIDER == "openai"`` o ``"ollama"`` → siempre ``False``.
    3. Si ``AI_PROVIDER == "auto"`` → ``True`` cuando el nombre del modelo
       empieza por ``"gemini"`` (insensible a mayúsculas).

    Args:
        model: Nombre del modelo de IA (p. ej. ``"gemini-2.0-flash"``).

    Returns:
        ``True`` si el proveedor activo es Google Gemini; ``False`` en caso contrario.
    """
    provider = config.AI_PROVIDER
    if provider == "gemini":
        return True
    if provider in ("openai", "ollama"):
        return False
    return model.lower().startswith("gemini")


def _is_ollama_provider() -> bool:
    """Determina si el proveedor de IA activo es Ollama (servidor LLM local).

    Lógica de detección (en orden de precedencia):

    1. Si ``AI_PROVIDER == "ollama"`` → siempre ``True``.
    2. Si ``AI_PROVIDER == "openai"`` o ``"gemini"`` → siempre ``False``.
    3. Si ``AI_PROVIDER == "auto"`` → ``True`` cuando ``OLLAMA_BASE_URL``
       tiene algún valor no vacío.

    Returns:
        ``True`` si el proveedor activo es Ollama; ``False`` en caso contrario.
    """
    provider = config.AI_PROVIDER
    if provider == "ollama":
        return True
    if provider in ("openai", "gemini"):
        return False
    return bool(config.OLLAMA_BASE_URL)


class LLMChain:
    """
    Cadena que combina un ChatPromptTemplate con un modelo de lenguaje (LLM).
    Implementa el patrón LLMChain usando LCEL (LangChain Expression Language):
      prompt | llm | StrOutputParser()
    Uso:
        chain = LLMChain(llm=llm, prompt=prompt_template)
        result = chain.run(user_prompt="Escribe un artículo sobre Python")
    """

    def __init__(self, llm: Union["ChatOpenAI", "ChatGoogleGenerativeAI"], prompt: ChatPromptTemplate) -> None:
        self._chain = prompt | llm | StrOutputParser()

    def run(self, **input_variables) -> str:
        """Ejecuta la cadena con las variables del prompt y devuelve el texto generado."""
        return self._chain.invoke(input_variables)

    def invoke(self, input_dict: dict[str, Any]) -> str:
        """Ejecuta la cadena con un diccionario de variables del prompt y devuelve el texto generado.

        Args:
            input_dict: Diccionario con las variables definidas en el ChatPromptTemplate,
                        por ejemplo ``{"user_prompt": "Escribe un artículo sobre Python"}``.
        """
        return self._chain.invoke(input_dict)


def _generate_with_langchain(
    system_msg: str,
    user_prompt: str,
    max_tokens: int,
    temperature: float = 0.7,
) -> str:
    """Invoca el modelo de lenguaje activo mediante LangChain LCEL y devuelve el texto generado.

    Construye la cadena ``prompt | llm | StrOutputParser()`` usando :class:`LLMChain` e
    instancia el LLM apropiado según el proveedor detectado:

    - **Gemini** → :class:`~langchain_google_genai.ChatGoogleGenerativeAI`
    - **Ollama** → :class:`~langchain_openai.ChatOpenAI` con ``base_url=OLLAMA_BASE_URL``
    - **OpenAI** → :class:`~langchain_openai.ChatOpenAI` con ``api_key=OPENAIAPIKEY``

    Args:
        system_msg:   Mensaje de sistema para el LLM (rol ``"system"``).
        user_prompt:  Prompt del usuario (rol ``"human"``).
        max_tokens:   Límite de tokens de salida del modelo.
        temperature:  Temperatura de generación (por defecto ``0.7``).

    Returns:
        Texto generado por el modelo como cadena de texto.

    Raises:
        :class:`RuntimeError`: Si la llamada al LLM no devuelve contenido.
    """
    if _is_gemini_model(config.OPENAI_MODEL):
        llm = ChatGoogleGenerativeAI(
            model=config.OPENAI_MODEL,
            google_api_key=config.GEMINI_API_KEY,
            max_output_tokens=max_tokens,
            temperature=temperature,
        )
    elif _is_ollama_provider():
        llm = ChatOpenAI(
            model=config.OPENAI_MODEL,
            base_url=config.OLLAMA_BASE_URL,
            api_key=config.OLLAMA_PLACEHOLDER_API_KEY,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    else:
        llm = ChatOpenAI(
            model=config.OPENAI_MODEL,
            api_key=config.OPENAIAPIKEY,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", system_msg),
        ("human", "{user_prompt}"),
    ])
    chain = LLMChain(llm=llm, prompt=prompt_template)
    result = chain.run(user_prompt=user_prompt)
    if not result:
        raise RuntimeError("LangChain no devolvió contenido.")
    return result

# ========= Retry con back-off exponencial =========
def _retry_with_backoff(fn: Callable, max_retries: int = config.OPENAI_MAX_RETRIES, base_delay: float = config.OPENAI_RETRY_BASE_DELAY) -> Any:
    """Ejecuta *fn()* con reintentos y back-off exponencial.

    Solo reintenta errores transitorios de red (:class:`ConnectionError`,
    :class:`TimeoutError`). Cualquier otro tipo de excepción se propaga
    inmediatamente sin reintentos.

    Fórmula de espera: ``delay = base_delay × 2^(attempt - 1) + random(0, 1)``

    Args:
        fn:          Función sin argumentos a ejecutar.
        max_retries: Número máximo de reintentos (por defecto ``OPENAI_MAX_RETRIES = 3``).
        base_delay:  Segundos base para el back-off exponencial
                     (por defecto ``OPENAI_RETRY_BASE_DELAY = 2``).

    Returns:
        El valor devuelto por *fn()* en el primer intento exitoso.

    Raises:
        :class:`RuntimeError`: Si se agotan todos los reintentos.
        Cualquier excepción no transitoria que lance *fn()*.
    """
    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            return fn()
        except (ConnectionError, TimeoutError) as exc:
            last_exc = exc
            wait = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 1)
            logger.warning("Reintento %d/%d tras error transitorio: %s (espera %.1fs)", attempt, max_retries, exc, wait)
            _time.sleep(wait)
        except Exception:
            raise
    raise RuntimeError(f"Falló tras {max_retries} reintentos") from last_exc
