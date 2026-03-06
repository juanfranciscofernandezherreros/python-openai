# Cómo funciona `generateArticle.py`

Este documento explica en detalle la arquitectura interna, el flujo de datos y cada componente clave del script de publicación automática de artículos.

---

## Índice

1. [Visión general](#1-visión-general)
2. [Variables de entorno y configuración](#2-variables-de-entorno-y-configuración)
3. [Constantes importantes](#3-constantes-importantes)
4. [Arquitectura y componentes principales](#4-arquitectura-y-componentes-principales)
5. [Flujo de ejecución paso a paso](#5-flujo-de-ejecución-paso-a-paso)
6. [Funciones auxiliares (helpers)](#6-funciones-auxiliares-helpers)
7. [Gestión de categorías, subcategorías y tags](#7-gestión-de-categorías-subcategorías-y-tags)
8. [Integración con OpenAI](#8-integración-con-openai)
9. [Control del límite semanal](#9-control-del-límite-semanal)
10. [Sistema de notificaciones por correo](#10-sistema-de-notificaciones-por-correo)
11. [Documento insertado en MongoDB](#11-documento-insertado-en-mongodb)
12. [Diagrama de flujo](#12-diagrama-de-flujo)

---

## 1. Visión general

`generateArticle.py` es un script Python que automatiza la **generación y publicación semanal de artículos técnicos** en una base de datos MongoDB. El flujo principal es:

```
Configuración → MongoDB → Límite semanal → Elegir tema → IA (OpenAI) → Guardar artículo → Email
```

Cada ejecución publica **como máximo un artículo** (por defecto). El script está diseñado para ser ejecutado de forma programada (cron semanal, CI/CD, etc.) y notifica todos los eventos importantes por correo electrónico.

---

## 2. Variables de entorno y configuración

El script carga su configuración desde un fichero `.env` en el mismo directorio (usando `python-dotenv`). Las variables disponibles son:

| Variable | Obligatoria | Descripción |
|---|---|---|
| `MONGODB_URI` | ✅ | URI de conexión a MongoDB (ej. `mongodb://admin:pass@localhost:27017/blogdb?authSource=admin`) |
| `DB_NAME` | ✅ | Nombre de la base de datos |
| `CATEGORY_COLL` | ✅ | Nombre de la colección de categorías |
| `TAGS_COLL` | ✅ | Nombre de la colección de tags |
| `USERS_COLL` | ✅ | Nombre de la colección de usuarios |
| `ARTICLES_COLL` | ✅ | Nombre de la colección de artículos |
| `OPENAIAPIKEY` | ✅ | Clave de API de OpenAI (`sk-...`) |
| `OPENAI_MODEL` | ❌ | Modelo a usar (por defecto `gpt-5`) |
| `AUTHOR_USERNAME` | ❌ | Usuario autor de los artículos (por defecto `adminUser`) |
| `SITE` | ❌ | URL base de la web (ej. `https://tusitio.com`) |
| `SMTP_HOST` | ❌ | Servidor SMTP para notificaciones |
| `SMTP_PORT` | ❌ | Puerto SMTP (por defecto `587`) |
| `SMTP_USER` | ❌ | Usuario SMTP |
| `SMTP_PASS` | ❌ | Contraseña SMTP |
| `FROM_EMAIL` | ❌ | Dirección de envío |
| `NOTIFY_EMAIL` | ❌ | Destinatario de las notificaciones |
| `NOTIFY_VERBOSE` | ❌ | Si es `true` (por defecto), envía email en cada evento; si es `false`, solo en errores/avisos |
| `LIMIT_PUBLICATION` | ❌ | Si es `true` (por defecto), limita a 1 artículo por semana |
| `SEND_PROMPT_EMAIL` | ❌ | Si es `true`, envía por email el prompt antes de llamar a OpenAI |

> Las variables sin un valor predeterminado que sean obligatorias harán que el script se detenga con `sys.exit(1)` si faltan.

---

## 3. Constantes importantes

Definidas directamente en el código, controlan el comportamiento del algoritmo de deduplicación de títulos:

| Constante | Valor | Significado |
|---|---|---|
| `SIMILARITY_THRESHOLD_DEFAULT` | `0.82` | Umbral de similitud genérico: dos textos con ratio ≥ 0.82 se consideran "demasiado parecidos" |
| `SIMILARITY_THRESHOLD_STRICT` | `0.86` | Umbral más estricto que se aplica al reintentar la generación de un título |
| `MAX_TITLE_RETRIES` | `5` | Número máximo de intentos para obtener un título suficientemente único |
| `RECENT_TITLES_LIMIT` | `50` | Cuántos títulos recientes se cargan de MongoDB para la comparación |
| `OPENAI_MAX_RETRIES` | `3` | Reintentos para errores transitorios de la API de OpenAI |
| `OPENAI_RETRY_BASE_DELAY` | `2` | Segundos base del back-off exponencial entre reintentos de OpenAI |
| `MONGO_TIMEOUT_MS` | `5000` | Tiempo máximo de espera para la selección de servidor MongoDB |

---

## 4. Arquitectura y componentes principales

El script está organizado en capas bien separadas:

```
┌─────────────────────────────────────────────────────────────────┐
│  main()                                                          │
│  ├── Validación de entorno                                       │
│  ├── Conexión MongoDB                                            │
│  ├── Control límite semanal                                      │
│  ├── Carga de datos (categorías, tags, autor)                    │
│  ├── pick_fresh_target_strict()  ← selección de tema            │
│  └── ensure_article_for_tag()   ← generación e inserción        │
│       ├── generate_article_with_ai()  ← llamada a OpenAI        │
│       └── db.insert_one()             ← escritura en MongoDB    │
└─────────────────────────────────────────────────────────────────┘
```

### Módulos/grupos de funciones

| Grupo | Funciones clave | Responsabilidad |
|---|---|---|
| **Helpers genéricos** | `str_id`, `as_list`, `tag_name`, `slugify`, `html_escape` | Utilidades de conversión y normalización |
| **Similitud** | `normalize_for_similarity`, `similar_ratio`, `is_too_similar` | Detectar duplicados de título |
| **Notificaciones** | `send_notification_email`, `notify` | Email SMTP y logging unificado |
| **MongoDB (batch)** | `preload_published_tag_ids`, `preload_published_category_ids` | Evitar consultas N+1 |
| **Jerarquía** | `build_hierarchy`, `index_tags`, `find_subcats_with_tags` | Árbol categorías/subcategorías/tags |
| **Selección** | `pick_fresh_target_strict`, `guess_parent_and_subcat_for_tag` | Elegir el tema con regla estricta |
| **IA** | `build_generation_prompt`, `generate_article_with_ai`, `_extract_json_block`, `_safe_json_loads` | Construir prompt y parsear respuesta |
| **Publicación** | `ensure_article_for_tag` | Orquestar generación + deduplicación + inserción |
| **Tiempo** | `current_week_window_utc_for_madrid`, `today_window_utc_for_madrid` | Calcular ventana semanal en zona horaria de Madrid |

---

## 5. Flujo de ejecución paso a paso

### Paso 1 — Validación de entorno

```python
# Comprueba que todas las variables obligatorias están definidas
if missing:
    notify("Configuración incompleta", ..., level="error")
    sys.exit(1)
```

Si falta cualquier variable crítica (`OPENAIAPIKEY`, `MONGODB_URI`, etc.), se envía un email de error y el proceso se detiene inmediatamente.

---

### Paso 2 — Conexión a MongoDB

```python
client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
db = client[DB_NAME]
```

Abre la conexión con un timeout de 5 segundos. Si falla, notifica el error y termina.

---

### Paso 3 — Control del límite semanal

Si `LIMIT_PUBLICATION=true` (por defecto):

1. Calcula la ventana lunes-domingo de la semana actual en hora de Madrid.
2. Busca en MongoDB artículos con `status: "published"` cuya `publishDate` caiga dentro de esa ventana.
3. Si ya hay **1 o más**, notifica con los detalles del artículo ya publicado y termina con `sys.exit(0)`.

```python
already_this_week = db[ARTICLES_COLL].count_documents({
    "publishDate": {"$gte": start_utc, "$lt": end_utc},
    "status": "published"
})
```

---

### Paso 4 — Carga de datos

```python
categories = list(db[CATEGORY_COLL].find({}))
tags       = list(db[TAGS_COLL].find({}))
author_id  = find_author_id(db)
```

- Carga todas las categorías y tags en memoria (colecciones pequeñas).
- Busca el usuario autor por `username`, `userName` o `name` (insensible a mayúsculas).

---

### Paso 5 — Pre-carga de cobertura (optimización N+1)

```python
published_tag_ids = preload_published_tag_ids(db)
published_cat_ids = preload_published_category_ids(db)
```

En lugar de hacer una consulta a MongoDB por cada tag o categoría (N+1), se ejecutan **dos agregaciones** que devuelven el conjunto completo de IDs ya cubiertos. Esto se pasa a `pick_fresh_target_strict` para comparaciones O(1).

---

### Paso 6 — Selección estricta del tema

`pick_fresh_target_strict(...)` devuelve una tupla `(parent, subcat, tag)` eligiendo aleatoriamente entre los candidatos que cumplan:

- El **tag** no tiene ningún artículo publicado.
- La **subcategoría** no tiene ningún artículo publicado.
- La **categoría padre** no tiene ningún artículo publicado.

Si no hay candidatos con tag disponible, intenta elegir una categoría/subcategoría sin artículos (publicación sin tag). Si todo está cubierto, notifica y termina.

---

### Paso 7 — Generación del artículo con IA

`ensure_article_for_tag(...)` orquesta el bucle de generación con hasta `MAX_TITLE_RETRIES` intentos:

```
bucle:
  1. Llamar a generate_article_with_ai()  →  (title, summary, body)
  2. Si el título es demasiado similar a uno reciente → añadirlo a avoid_titles y reintentar
  3. Si el título es único → salir del bucle
```

Cada intento llama a `generate_article_with_ai`, que:

1. Construye el prompt con `build_generation_prompt`.
2. Intenta la **API Responses moderna** (`client.responses.create`).
3. Si falla, usa **Chat Completions** como fallback.
4. Extrae el bloque JSON de la respuesta con `_extract_json_block`.
5. Parsea el JSON con `_safe_json_loads` (tolerante a comillas tipográficas).
6. Devuelve `(title, summary, body)`.

---

### Paso 8 — Inserción en MongoDB

Si el título es único:

```python
doc = {
    "title": title, "slug": slug, "summary": summary, "body": body,
    "category": ObjectId(...), "tags": [tag_id],
    "author": author_id, "status": "published",
    "publishDate": now, "createdAt": now, ...
}
db[ARTICLES_COLL].insert_one(doc)
```

El **slug** se genera con `slugify(title)` y se garantiza que sea único con `next_available_slug` (añade `-2`, `-3`, etc. si ya existe).

---

### Paso 9 — Notificación y fin

- Si se publicó: email de éxito con título, slug y tag.
- Si no se publicó (todos los intentos fallaron): email de aviso.
- En ambos casos, imprime el resumen final en consola.

---

## 6. Funciones auxiliares (helpers)

### `slugify(text: str) → str`

Convierte un texto en un slug URL-friendly:

1. Normaliza caracteres Unicode (NFD) y elimina diacríticos (acentos).
2. Pasa a minúsculas.
3. Sustituye cualquier carácter no alfanumérico por `-`.
4. Elimina guiones al inicio y al final.

```python
slugify("Cómo usar @Builder en Spring Boot")
# → "como-usar-builder-en-spring-boot"
```

### `is_too_similar(title, candidates, threshold) → bool`

Usa `difflib.SequenceMatcher` sobre versiones normalizadas (sin acentos, minúsculas, sin signos de puntuación) de los títulos. Devuelve `True` si la ratio de similitud con cualquier candidato supera el umbral.

### `html_escape(s) → str`

Escapa `&`, `<` y `>` para uso seguro en correos HTML. Evita que el contenido del artículo rompa el HTML del email.

### `next_available_slug(db, base_slug) → str`

Comprueba en MongoDB si el slug ya existe. Si es así, prueba `{base_slug}-2`, `{base_slug}-3`, etc., hasta encontrar uno libre.

---

## 7. Gestión de categorías, subcategorías y tags

Esta sección describe en detalle la estructura de datos en MongoDB, el modelo relacional, los documentos almacenados y todos los algoritmos que intervienen en la selección del tema a generar.

---

### 7.1 Estructura jerárquica y modelo de datos

La taxonomía tiene **tres niveles**:

```
┌─────────────────────────────────────────────────────────────────────┐
│  NIVEL 1 — Categoría padre                                          │
│  ej. "Spring Boot" / "Data & Persistencia" / "Inteligencia         │
│       Artificial"                                                   │
│                                                                     │
│   └── NIVEL 2 — Subcategoría                                        │
│       ej. "Lombok" / "Spring Security" / "Spring AI"               │
│       (campo parent = ObjectId de la categoría padre)               │
│                                                                     │
│         └── NIVEL 3 — Tag                                           │
│             ej. "@Data" / "JWT Authentication" / "Spring AI         │
│                  Overview"                                          │
│             (campo categoryId = ObjectId de la subcategoría)        │
└─────────────────────────────────────────────────────────────────────┘
```

Cada artículo generado se asocia a **una subcategoría** (campo `category`) y **a un tag** (campo `tags`), lo que garantiza cobertura progresiva de todo el catálogo de temas.

---

### 7.2 Esquemas de documentos en MongoDB

#### Colección `categories` — Categoría padre

```json
{
  "_id":         ObjectId("..."),
  "name":        "Spring Boot",
  "description": "Desarrollo de aplicaciones Java con el framework Spring Boot.",
  "parent":      null,
  "createdAt":   ISODate("..."),
  "updatedAt":   ISODate("...")
}
```

#### Colección `categories` — Subcategoría

```json
{
  "_id":            ObjectId("..."),
  "name":           "Lombok",
  "description":    "Reducción de código boilerplate Java con Lombok.",
  "parent":         ObjectId("← _id de la categoría padre"),
  "parentName":     "Spring Boot",
  "tags":           [ObjectId("..."), ObjectId("..."), ...],
  "createdAt":      ISODate("..."),
  "updatedAt":      ISODate("...")
}
```

> El campo `tags` en la subcategoría es una lista de `ObjectId` que apuntan a los documentos de la colección `tags`.

#### Colección `tags`

```json
{
  "_id":                ObjectId("..."),
  "name":               "@Data",
  "tag":                "@Data",
  "categoryId":         ObjectId("← _id de la subcategoría"),
  "categoryName":       "Lombok",
  "parentCategoryId":   ObjectId("← _id de la categoría padre"),
  "parentCategoryName": "Spring Boot",
  "createdAt":          ISODate("..."),
  "updatedAt":          ISODate("...")
}
```

---

### 7.3 Diagrama entidad–relación (simplificado)

```
 ┌──────────────────┐           ┌──────────────────┐
 │   categories     │           │   categories     │
 │  (padre)         │1        N │  (subcategoría)  │
 │                  │◄──────────│                  │
 │  _id (PK)        │  parent   │  _id (PK)        │
 │  name            │           │  name            │
 │  description     │           │  description     │
 │  parent = null   │           │  parent (FK)     │
 └──────────────────┘           │  parentName      │
                                │  tags [ ]  ──────┼──────┐
                                └──────────────────┘      │ N
                                                          │
                                 ┌────────────────────────▼─┐
                                 │          tags            │
                                 │                          │
                                 │  _id (PK)                │
                                 │  name / tag              │
                                 │  categoryId (FK)         │
                                 │  categoryName            │
                                 │  parentCategoryId (FK)   │
                                 │  parentCategoryName      │
                                 └──────────────────────────┘
```

---

### 7.4 Taxonomía predefinida (`seed_data.py`)

El script `seed_data.py` siembra la base de datos con la siguiente estructura de 3 categorías padre, 14 subcategorías y ~140 tags:

```
Spring Boot (categoría padre)
├── Spring Boot Core         → 10 tags  (@SpringBootApplication, Auto-configuration, ...)
├── Spring Security          → 10 tags  (JWT Authentication, OAuth2, ...)
├── Spring Data JPA          → 10 tags  (@Entity y @Table, JpaRepository, ...)
├── Spring MVC REST          → 10 tags  (@RestController, ResponseEntity, ...)
├── Spring Boot Testing      → 10 tags  (@SpringBootTest, @WebMvcTest, ...)
└── Lombok                   → 10 tags  (@Data, @Builder, @Slf4j, ...)

Data & Persistencia (categoría padre)
├── JPA e Hibernate          → 10 tags  (Hibernate Caching L1 y L2, N+1, ...)
├── Bases de Datos SQL        → 10 tags  (PostgreSQL, MySQL, Flyway, ...)
├── NoSQL y MongoDB          → 10 tags  (Spring Data MongoDB, @Document, ...)
└── Migraciones de Esquema   →  8 tags  (Flyway, Liquibase, Rollback, ...)

Inteligencia Artificial (categoría padre)
├── Spring AI                → 10 tags  (Spring AI Overview, ChatClient, ...)
├── LLMs y Modelos de Lenguaje→ 10 tags  (OpenAI API con Java, GPT-4, ...)
├── Machine Learning con Java→ 10 tags  (Deeplearning4j, TensorFlow Java, ...)
└── Vector Databases y RAG   → 10 tags  (Embeddings, RAG, Pinecone, ...)
```

---

### 7.5 Funciones de gestión de la jerarquía

#### `build_hierarchy(categories) → (by_id, by_parent)`

Construye dos índices en memoria a partir de la lista de documentos de la colección `categories`:

| Índice | Tipo | Descripción |
|---|---|---|
| `by_id` | `Dict[str, doc]` | Mapa `{str(_id) → documento}`. Permite buscar cualquier categoría en O(1). |
| `by_parent` | `Dict[str, List[doc]]` | Mapa `{str(parent_id) → [hijos]}`. Permite recorrer el árbol de hijos en O(1). Las categorías raíz se agrupan bajo la clave `None`. |

```
Entrada:  lista de documentos category
Salida:   by_id = { "abc123": {name:"Spring Boot", parent:null, ...},
                   "def456": {name:"Lombok", parent:ObjectId("abc123"), ...}, ... }
          by_parent = { None:    [{name:"Spring Boot", ...}, ...],
                        "abc123":[{name:"Lombok", ...}, ...] }
```

#### `index_tags(tags) → (tags_by_id, tags_by_name)`

Construye dos índices sobre los documentos de la colección `tags`:

| Índice | Tipo | Descripción |
|---|---|---|
| `tags_by_id` | `Dict[str, doc]` | Mapa `{str(_id) → documento de tag}`. |
| `tags_by_name` | `Dict[str, doc]` | Mapa `{nombre_tag → documento de tag}`. Útil cuando la referencia al tag se hace por nombre en lugar de por `_id`. |

#### `get_related_tags_for_category(cat_or_subcat, tags, tags_by_id, tags_by_name)`

Devuelve la lista de tags relacionados con una categoría o subcategoría. Aplica las siguientes estrategias en orden, devolviendo el primer resultado no vacío:

```
Estrategia 1 — claves directas en el documento:
  Busca los campos "tags", "tagIds" o "tagsIds" en cat_or_subcat.
  Para cada valor encontrado:
    · Si es un ObjectId válido → busca en tags_by_id
    · Si no → busca como nombre en tags_by_name

Estrategia 2 — búsqueda inversa en los tags:
  Para cada tag de la colección, comprueba si:
    · tag.categoryId    == _id de la categoría
    · tag.categoryName  == name de la categoría
    · tag.categories[]  contiene el _id o name de la categoría

Resultado: lista deduplicada por _id de los tags relacionados.
```

Este diseño hace que la función sea robusta ante **esquemas MongoDB heterogéneos** (documentos creados con distintas versiones del código o con herramientas externas).

---

### 7.6 Algoritmo de selección estricta: `pick_fresh_target_strict()`

Esta función implementa la **regla de cobertura estricta**: solo elige un tema si **los tres niveles** (categoría padre, subcategoría y tag) están sin cobertura (sin artículos publicados).

#### Entrada

```python
pick_fresh_target_strict(
    db,                   # conexión MongoDB
    categories,           # lista completa de documentos category
    by_id,                # índice por _id
    by_parent,            # índice por parent_id
    tags,                 # lista completa de documentos tag
    tags_by_id,           # índice de tags por _id
    tags_by_name,         # índice de tags por nombre
    published_tag_ids,    # Set[str] de tag _id ya cubiertos
    published_cat_ids,    # Set[str] de category _id ya cubiertos
)
```

#### Salida

```python
(parent, subcat, tag)   # Tupla de documentos MongoDB (o None si no hay candidatos)
```

#### Diagrama del algoritmo

```
┌──────────────────────────────────────────────────────────────────────┐
│  pick_fresh_target_strict()                                          │
│                                                                      │
│  ┌─── FASE 1: Candidatos CON tag ────────────────────────────────┐  │
│  │                                                                │  │
│  │  find_subcats_with_tags()                                      │  │
│  │    → lista de (parent_id, subcat, rel_tags)                   │  │
│  │         para cada subcategoría que tenga tags relacionados     │  │
│  │                                                                │  │
│  │  Barajar aleatoriamente                                        │  │
│  │                                                                │  │
│  │  Para cada (parent_id, subcat, rel_tags):                     │  │
│  │    ¿subcat ya tiene artículo?   → saltar                       │  │
│  │    ¿parent ya tiene artículo?   → saltar                       │  │
│  │    available_tags = rel_tags sin artículo                      │  │
│  │    ¿available_tags vacío?        → saltar                      │  │
│  │    Elegir tag aleatorio de available_tags                      │  │
│  │    → DEVOLVER (parent, subcat, tag)  ✅                        │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌─── FASE 2: Candidatos SIN tag ────────────────────────────────┐  │
│  │  (solo si la Fase 1 no encontró candidatos)                   │  │
│  │                                                                │  │
│  │  cats_wo_article = categorías/subcategorías sin artículo       │  │
│  │  Barajar aleatoriamente                                        │  │
│  │                                                                │  │
│  │  Para cada c en cats_wo_article:                               │  │
│  │    Si c tiene padre:                                           │  │
│  │      ¿padre ya tiene artículo? → saltar                        │  │
│  │      → DEVOLVER (padre, c, None)  ✅                           │  │
│  │    Si c es raíz:                                               │  │
│  │      → DEVOLVER (c, None, None)  ✅                            │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌─── FASE 3: Sin candidatos ─────────────────────────────────────┐  │
│  │  → DEVOLVER (None, None, None)  ⚠️ Todo cubierto              │  │
│  └────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

#### Optimización anti N+1

En lugar de consultar MongoDB por cada tag o categoría individualmente, se usan dos **agregaciones batch** que precalculan todos los IDs cubiertos:

```python
# Todos los tag _id que tienen ≥1 artículo publicado
published_tag_ids = preload_published_tag_ids(db)
# → {"abc123", "def456", ...}

# Todos los category _id que tienen ≥1 artículo publicado
published_cat_ids = preload_published_category_ids(db)
# → {"ghi789", "jkl012", ...}
```

Las comprobaciones de cobertura son entonces O(1) (consulta en un `set`), en lugar de una consulta a MongoDB por cada tag/categoría.

---

### 7.7 Diagrama completo de la gestión de categorías/tags

```
  seed_data.py                    generateArticle.py
  ─────────────                   ──────────────────

  TAXONOMY[]                      db[CATEGORY_COLL].find({})
     │                                    │
     ▼                                    ▼
  upsert_category()  ──────►  categories[]  ──► build_hierarchy()
  upsert_tag()       ──────►  tags[]        ──► index_tags()
                                    │                 │
                                    │                 ▼
                                    │           by_id, by_parent
                                    │           tags_by_id, tags_by_name
                                    │
                                    ▼
                         preload_published_tag_ids()   ──► published_tag_ids (Set)
                         preload_published_category_ids() ► published_cat_ids (Set)
                                    │
                                    ▼
                         pick_fresh_target_strict()
                           │
                           ├── find_subcats_with_tags()
                           │       └── get_related_tags_for_category()
                           │
                           └── (parent, subcat, tag)
                                        │
                                        ▼
                              ensure_article_for_tag()
                                build_topic_text()
                                generate_article_with_ai()
                                db[ARTICLES_COLL].insert_one()
```

---

## 8. Integración con OpenAI

### Prompt generado

`build_generation_prompt(parent_name, subcat_name, tag_text, avoid_titles)` produce un prompt en español que instruye al modelo a devolver **únicamente un JSON** con la estructura:

```json
{
  "title":    "...",
  "summary":  "...",
  "body":     "...",
  "keywords": ["keyword1", "keyword2", "keyword3"]
}
```

| Campo | Descripción | Restricción |
|---|---|---|
| `title` | Título del artículo, optimizado para SEO | máx. 60 caracteres |
| `summary` | 2-3 frases de resumen (metadescripción) | máx. 160 caracteres |
| `body` | Cuerpo completo en HTML semántico con `<h1>`, secciones `<h2>`, `<pre><code>`, FAQ y conclusión | — |
| `keywords` | Lista de 3-7 palabras clave SEO en minúsculas | sin repetir el título exacto |

### Estrategia de llamada con fallback

El script intenta dos rutas distintas al SDK de OpenAI, en este orden:

```
1. client.responses.create(model, input=prompt)
   └── API Responses (disponible en openai-python ≥ 1.66.0, ~2025)
       Si el atributo no existe o la llamada falla →
2. client.chat.completions.create(model, messages)
   └── Chat Completions — endpoint estándar, siempre disponible
```

Este diseño garantiza compatibilidad hacia atrás: si la versión instalada del SDK no dispone del endpoint `responses`, la excepción se captura silenciosamente y el proceso continúa con Chat Completions. Ambas rutas tienen reintentos con **back-off exponencial** para errores transitorios (`ConnectionError`, `TimeoutError`).

### Parseo tolerante de la respuesta

La respuesta puede llegar en distintos formatos:
- JSON puro.
- Bloque de código ```json … ```.
- Texto con JSON embebido.

`_extract_json_block` extrae el primer objeto JSON válido. `_safe_json_loads` tolera comillas tipográficas (`"`, `"`) que a veces produce el modelo.

---

## 9. Control del límite semanal

```python
def current_week_window_utc_for_madrid(start_weekday=1):
    tz_madrid = ZoneInfo("Europe/Madrid")
    today = datetime.now(tz_madrid).date()
    # Calcula el lunes de la semana actual
    delta_days = (today.isoweekday() - start_weekday) % 7
    start_local = datetime.combine(today - timedelta(days=delta_days), time(0,0), tzinfo=tz_madrid)
    end_local = start_local + timedelta(days=7)
    # Convierte a UTC para la consulta a MongoDB
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)
```

Esto garantiza que el límite semanal **siempre se calcula en hora de Madrid** (incluyendo el cambio de horario de verano/invierno), independientemente del huso horario del servidor donde corra el script.

La variable `LIMIT_PUBLICATION=false` desactiva completamente esta comprobación, útil para entornos de prueba.

---

## 10. Sistema de notificaciones por correo

`notify(subject, message, level, always_email)` centraliza todo el logging:

1. Imprime en consola con timestamp UTC y emoji indicador de nivel.
2. Decide si enviar email según:
   - `always_email=True` → siempre envía.
   - `NOTIFY_VERBOSE=true` → envía en todos los eventos.
   - `level in ("error","warning")` → siempre envía errores y advertencias.

Los niveles disponibles son: `info`, `success`, `warning`, `error`.

`send_notification_email` envía un email SMTP con **texto plano + alternativa HTML** usando la librería estándar `smtplib` y `email.message.EmailMessage`. La conexión usa STARTTLS.

---

## 11. Documento insertado en MongoDB

El artículo que se inserta en la colección de artículos tiene la siguiente estructura:

```json
{
  "title":          "Cómo usar @Data en Lombok",
  "slug":           "como-usar-data-en-lombok",
  "summary":        "Resumen del artículo...",
  "body":           "<h1>...</h1><p>...</p>...",
  "category":       ObjectId("..."),
  "tags":           [ObjectId("...")],
  "author":         ObjectId("..."),
  "status":         "published",
  "likes":          [],
  "favoritedBy":    [],
  "isVisible":      true,
  "publishDate":    ISODate("..."),
  "generatedAt":    ISODate("..."),
  "createdAt":      ISODate("..."),
  "updatedAt":      ISODate("..."),
  "images":         null,
  "wordCount":      1240,
  "readingTime":    6,
  "keywords":       ["lombok", "@data", "java", "boilerplate", "pojo"],
  "metaTitle":      "Cómo usar @Data en Lombok",
  "metaDescription":"Aprende a reducir el código boilerplate con @Data de Lombok en Spring Boot."
}
```

| Campo | Tipo | Descripción |
|---|---|---|
| `category` | `ObjectId` | Apunta a la **subcategoría** elegida (o a la categoría raíz si no hay subcategoría). |
| `tags` | `[ObjectId]` | Lista de tags asociados. Puede ser vacía si no se encontró tag disponible. |
| `wordCount` | `int` | Número de palabras del cuerpo HTML (texto plano). |
| `readingTime` | `int` | Tiempo de lectura estimado en minutos (`ceil(wordCount / 230)`), mínimo 1. |
| `keywords` | `[str]` | Palabras clave SEO devueltas por la IA (3-7 términos en minúsculas). |
| `metaTitle` | `str` | Título SEO, truncado a 60 caracteres si es necesario. |
| `metaDescription` | `str` | Descripción SEO, truncada a 160 caracteres si es necesario. |

> Todas las fechas se almacenan en **UTC**.

---

## 12. Diagrama de flujo

### 12.1 Flujo principal del script

```
┌─────────────────────────────────────────┐
│             INICIO (main)               │
└────────────────┬────────────────────────┘
                 │
        ┌────────▼────────┐
        │ ¿Variables OK?  │──── NO ──► Email error + sys.exit(1)
        └────────┬────────┘
                 │ SÍ
        ┌────────▼────────┐
        │ Conectar MongoDB│──── FALLA ──► Email error + sys.exit(1)
        └────────┬────────┘
                 │ OK
        ┌────────▼──────────────┐
        │ LIMIT_PUBLICATION=true│
        │ ¿Ya hay artículo      │
        │  esta semana?         │──── SÍ ──► Email aviso + sys.exit(0)
        └────────┬──────────────┘
                 │ NO
        ┌────────▼─────────────────┐
        │ Cargar categorías + tags  │
        │ Buscar usuario autor      │──── FALLA ──► Email error + sys.exit(1)
        └────────┬─────────────────┘
                 │ OK
        ┌────────▼──────────────────────┐
        │ Precargar IDs ya cubiertos     │
        │ (tags, categorías publicadas)  │
        └────────┬──────────────────────┘
                 │
        ┌────────▼─────────────────────────────────┐
        │ pick_fresh_target_strict()                │
        │ ¿Hay (parent, subcat, tag) disponible?   │──── NO ──► Email aviso + sys.exit(0)
        └────────┬─────────────────────────────────┘
                 │ SÍ
        ┌────────▼──────────────────────────────────────┐
        │ ensure_article_for_tag()                       │
        │  ┌──────────────────────────────────────────┐ │
        │  │  Bucle (máx. 5 intentos)                 │ │
        │  │   1. generate_article_with_ai()          │ │
        │  │   2. ¿Título demasiado similar?          │ │
        │  │      SÍ → añadir a avoid_titles, repetir│ │
        │  │      NO → aceptar título                 │ │
        │  └──────────────────────────────────────────┘ │
        │  ¿Título obtenido?                             │
        └────────┬───────────────────┬──────────────────┘
                 │ SÍ                │ NO
        ┌────────▼──────┐   ┌────────▼──────────────────┐
        │ INSERT artículo│   │ Email error (sin título)   │
        │ Email éxito    │   └───────────────────────────┘
        └────────┬───────┘
                 │
        ┌────────▼──────────────────┐
        │ FIN — Email "Proceso OK"  │
        └───────────────────────────┘
```

---

### 12.2 Diagrama detallado: Gestión de categorías, subcategorías y tags (punto 7)

```
  ┌───────────────────────────────────────────────────────────────────────────┐
  │  PASO 7 — GESTIÓN DE CATEGORÍAS, SUBCATEGORÍAS Y TAGS                    │
  └───────────────────────────────────────────────────────────────────────────┘

  MongoDB
  ┌──────────────┐   find({})   ┌────────────────────────────────────────────┐
  │  categories  │─────────────►│  categories[]  (en memoria)                │
  └──────────────┘              │                                            │
  ┌──────────────┐   find({})   │  build_hierarchy(categories)               │
  │    tags      │─────────────►│  ┌──────────────┐  ┌────────────────────┐ │
  └──────────────┘              │  │ by_id         │  │ by_parent          │ │
                                │  │ {_id → doc}  │  │ {parent_id→[hijos]}│ │
                                │  └──────────────┘  └────────────────────┘ │
                                │                                            │
                                │  index_tags(tags)                          │
                                │  ┌──────────────┐  ┌────────────────────┐ │
                                │  │ tags_by_id   │  │ tags_by_name       │ │
                                │  │ {_id → doc}  │  │ {nombre → doc}     │ │
                                │  └──────────────┘  └────────────────────┘ │
                                └────────────────────────────────────────────┘
                                                   │
                                                   ▼
  ┌──────────────────────────────────────────────────────────────────────────┐
  │  preload_published_tag_ids(db)                                           │
  │    Agregación: artículos published → unwind tags → group _id            │
  │    Resultado: published_tag_ids = {"id1", "id2", ...}   (Set[str])      │
  │                                                                          │
  │  preload_published_category_ids(db)                                      │
  │    Agregación: artículos published → group category                      │
  │    Resultado: published_cat_ids = {"id3", "id4", ...}   (Set[str])      │
  └──────────────────────────────────────────────────────────────────────────┘
                                                   │
                                                   ▼
  ┌──────────────────────────────────────────────────────────────────────────┐
  │  pick_fresh_target_strict()                                              │
  │                                                                          │
  │  FASE 1 — Con tag:                                                       │
  │  ┌────────────────────────────────────────────────────────────────────┐ │
  │  │  find_subcats_with_tags()                                          │ │
  │  │    Para cada subcategoría con parent ≠ null:                       │ │
  │  │      get_related_tags_for_category(subcat, ...)                    │ │
  │  │        Estrategia 1: subcat.tags / subcat.tagIds → busca en        │ │
  │  │                      tags_by_id o tags_by_name                     │ │
  │  │        Estrategia 2 (fallback): recorre todos los tags buscando    │ │
  │  │                      tag.categoryId == subcat._id                  │ │
  │  │                   o  tag.categoryName == subcat.name               │ │
  │  │    → Lista: [(parent_id, subcat, rel_tags), ...]                   │ │
  │  └────────────────────────────────────────────────────────────────────┘ │
  │                │                                                         │
  │                ▼  random.shuffle                                         │
  │  Para cada (parent_id, subcat, rel_tags):                               │
  │    ┌─ subcat._id ∈ published_cat_ids? ──► SÍ → saltar                  │
  │    ├─ parent._id ∈ published_cat_ids? ──► SÍ → saltar                  │
  │    └─ available = [t for t in rel_tags                                  │
  │                    if t._id ∉ published_tag_ids]                        │
  │         ¿available vacío? ──► SÍ → saltar                              │
  │         NO → elegir tag aleatorio                                        │
  │              → RETURN (parent, subcat, tag)  ✅                          │
  │                                                                          │
  │  FASE 2 — Sin tag (si Fase 1 sin resultado):                             │
  │    cats_wo_article = [c for c in categories                              │
  │                       if c._id ∉ published_cat_ids]                     │
  │    random.shuffle                                                        │
  │    Para cada c:                                                          │
  │      Si c.parent: ¿parent ∈ published_cat_ids? → saltar                 │
  │                   → RETURN (parent, c, None)  ✅                         │
  │      Si raíz:     → RETURN (c, None, None)  ✅                           │
  │                                                                          │
  │  FASE 3 — Sin candidatos:                                                │
  │    → RETURN (None, None, None)  ⚠️                                       │
  └──────────────────────────────────────────────────────────────────────────┘
                                                   │
                              ┌────────────────────┼───────────────────┐
                              │ (parent, subcat, tag) obtenidos        │
                              ▼                                        ▼
              build_topic_text(parent, subcat, tag)         (None, None, None)
                  → texto del tema p/ el prompt              Email aviso + exit
                              │
                              ▼
              ensure_article_for_tag(db, client_ai,
                  tag, parent, subcat, recent_titles, author_id)
                              │
                              └─► generate_article_with_ai()
                                  insert_one(doc)  ← categoría + tag asignados
```
