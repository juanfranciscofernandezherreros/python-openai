# -*- coding: utf-8 -*-
import os, sys, json, random, re, unicodedata, difflib
import smtplib
from datetime import datetime, timezone, time, timedelta
from zoneinfo import ZoneInfo
from pymongo import MongoClient
from bson import ObjectId
from openai import OpenAI
from dotenv import load_dotenv
from email.message import EmailMessage

# ============ CARGA .env ============
# Busca el .env en la carpeta actual del script
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

# ============ CONFIG DESDE ENTORNO ============
MONGODB_URI     = os.getenv("MONGODB_URI")
DB_NAME         = os.getenv("DB_NAME")
CATEGORY_COLL   = os.getenv("CATEGORY_COLL")
TAGS_COLL       = os.getenv("TAGS_COLL")
USERS_COLL      = os.getenv("USERS_COLL")
ARTICLES_COLL   = os.getenv("ARTICLES_COLL")
SITE            = os.getenv("SITE") or ""
OPENAIAPIKEY    = os.getenv("OPENAIAPIKEY")
AUTHOR_USERNAME = os.getenv("AUTHOR_USERNAME") or "adminUser"
OPENAI_MODEL    = os.getenv("OPENAI_MODEL", "gpt-5")

# Notificaciones
SMTP_HOST   = os.getenv("SMTP_HOST")
SMTP_PORT   = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER   = os.getenv("SMTP_USER")
SMTP_PASS   = os.getenv("SMTP_PASS")
FROM_EMAIL  = os.getenv("FROM_EMAIL") or (SMTP_USER or "")
TO_EMAIL    = os.getenv("NOTIFY_EMAIL") or "juanfranciscofernandezherreros@gmail.com"
NOTIFY_VERBOSE = (os.getenv("NOTIFY_VERBOSE", "true").lower() in ("1","true","yes","y"))

# ============ HELPERS ============
def str_id(x):
    try:
        if isinstance(x, ObjectId):
            return str(x)
        return str(ObjectId(x)) if ObjectId.is_valid(str(x)) else str(x)
    except Exception:
        return str(x)

def as_list(v):
    if v is None: return []
    if isinstance(v, (list, tuple, set)): return list(v)
    return [v]

def tag_name(t):
    return str(t.get("name") or t.get("tag") or t.get("_id"))

def slugify(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"^-+|-+$", "", text)
    return text

def next_available_slug(db, base_slug: str) -> str:
    slug = base_slug
    n = 2
    while db[ARTICLES_COLL].find_one({"slug": slug}):
        slug = f"{base_slug}-{n}"
        n += 1
    return slug

def normalize_for_similarity(s: str) -> str:
    if not s: return ""
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = s.lower()
    s = re.sub(r"[\W_]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def similar_ratio(a: str, b: str) -> float:
    a_norm, b_norm = normalize_for_similarity(a), normalize_for_similarity(b)
    if not a_norm or not b_norm: return 0.0
    return difflib.SequenceMatcher(None, a_norm, b_norm).ratio()

def is_too_similar(title: str, candidates: list, threshold: float = 0.82) -> bool:
    for c in candidates:
        if similar_ratio(title, c) >= threshold:
            return True
    return False

def now_utc():
    return datetime.now(tz=timezone.utc)

# ========= Notificaciones / logging =========
def send_notification_email(subject: str, html_body: str, text_body: str = None):
    if not all([SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, FROM_EMAIL, TO_EMAIL]):
        print("⚠️  Faltan variables SMTP para enviar el correo. Se omite el envío.")
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = FROM_EMAIL
    msg["To"] = TO_EMAIL
    text_body = text_body or "Notificación del proceso."
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(SMTP_USER, SMTP_PASS)
            smtp.send_message(msg)
        print(f"📧 Notificación enviada a {TO_EMAIL}: {subject}")
        return True
    except Exception as e:
        print(f"❌ Error enviando el correo: {e}", file=sys.stderr)
        return False

def notify(subject: str, message: str, level: str = "info", always_email: bool = True):
    """
    Centraliza impresión y envío de email. Si NOTIFY_VERBOSE es False,
    sólo envía emails para level in ['error','warning'] salvo que always_email=True.
    """
    stamp = now_utc().isoformat()
    prefix = {"info":"ℹ️","success":"✅","warning":"⚠️","error":"❌"}.get(level, "ℹ️")
    line = f"{prefix} [{stamp}] {subject} :: {message}"
    print(line)
    should_email = always_email or NOTIFY_VERBOSE or (level in ("error","warning"))
    if should_email:
        html = f"<p><b>{subject}</b></p><p>{message}</p><p><small>{stamp} UTC</small></p>"
        send_notification_email(subject=f"[{level.upper()}] {subject}", html_body=html, text_body=f"{subject}\n\n{message}\n\n{stamp} UTC")

# ========= Dominio categorías/tags =========
def index_tags(tags):
    """Índices útiles de tags por _id y por nombre/tag."""
    by_id = {}
    by_name = {}
    for t in tags:
        tid = str_id(t.get("_id"))
        by_id[tid] = t
        nm = (t.get("name") or t.get("tag") or "").strip()
        if nm:
            by_name[nm] = t
    return by_id, by_name

def get_related_tags_for_category(subcat, tags, tags_by_id, tags_by_name):
    related = []
    # claves directas
    for key in ("tags", "tagIds", "tagsIds"):
        if key in subcat:
            for raw in as_list(subcat.get(key)):
                sid = str_id(raw)
                if sid in tags_by_id:
                    related.append(tags_by_id[sid])
                else:
                    nm = str(raw)
                    if nm in tags_by_name:
                        related.append(tags_by_name[nm])

    if not related:
        sc_id = str_id(subcat.get("_id"))
        sc_name = str(subcat.get("name") or subcat.get("title") or sc_id)
        for t in tags:
            cand_ids = [t.get("categoryId"), t.get("category_id"), t.get("categoryRef")]
            cand_names = [t.get("categoryName"), t.get("category")]
            if any(str_id(cid) == sc_id for cid in cand_ids if cid is not None):
                related.append(t); continue
            if any(str(cn).strip() == sc_name for cn in cand_names if cn):
                related.append(t); continue
            for arr_key in ("categories", "categoryIds", "category_ids"):
                if arr_key in t:
                    arr = as_list(t.get(arr_key))
                    if any(str_id(x) == sc_id or str(x) == sc_name for x in arr):
                        related.append(t); break

    # únicos por _id
    seen, uniq = set(), []
    for t in related:
        k = str_id(t.get("_id"))
        if k not in seen:
            seen.add(k)
            uniq.append(t)
    return uniq

def build_generation_prompt(parent_name: str, subcat_name: str, tag_text: str, avoid_titles=None) -> str:
    avoid_titles = avoid_titles or []
    avoid_block = ""
    if avoid_titles:
        avoid_list = [t.replace('"', '\\"') for t in avoid_titles[:5]]
        avoid_block = (
            "\\n- Evita usar títulos iguales o muy similares a cualquiera de estos: "
            + "; ".join(f'"{t}"' for t in avoid_list)
        )
    return f"""
Eres redactor técnico experto en Spring Boot y Lombok. Genera un artículo **en español** con la siguiente estructura JSON estricta:
{{
  "title": "...",
  "summary": "...",
  "body": "..."
}}

Reglas:
- El tema principal es "{tag_text}" dentro de la categoría "{parent_name}" y subcategoría "{subcat_name}".
- "title": atractivo, claro y conciso (máx. 70 caracteres).
- "summary": 2-3 frases que expliquen el valor del post.
- "body": HTML bien formado que incluya:
  - <h1> con el título (sin emojis en el h1).
  - Introducción breve (<p>).
  - 3-5 secciones <h2> con explicación técnica y buenas prácticas.
  - Cuando proceda, ejemplos de código reales en <pre><code class="language-..."> ... </code></pre>.
  - Una sección "Preguntas frecuentes (FAQ)" con 3-5 <h3> preguntas y respuestas <p>.
  - Una breve conclusión con llamada a la acción (CTA).
- El contenido debe ser original, correcto y usable.
- Si el tema encaja, incluye ejemplo práctico con Lombok y/o Spring Boot.
- Escapa correctamente comillas para que sea JSON válido.{avoid_block}
"""

def generate_article_with_ai(client_ai: OpenAI, parent_name: str, subcat_name: str, tag_text: str, avoid_titles=None):
    resp = client_ai.responses.create(
        model=OPENAI_MODEL,
        input=build_generation_prompt(parent_name, subcat_name, tag_text, avoid_titles=avoid_titles)
    )
    raw = resp.output_text.strip()
    try:
        data = json.loads(raw)
    except Exception:
        start = raw.find("{"); end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            data = json.loads(raw[start:end+1])
        else:
            raise ValueError("La respuesta de OpenAI no es JSON válido:\n" + raw)

    title = str(data.get("title", "")).strip()
    summary = str(data.get("summary", "")).strip()
    body = str(data.get("body", "")).strip()
    if not title or not body:
        raise ValueError("Faltan 'title' o 'body' en la respuesta de OpenAI.")
    return title, summary, body

def find_author_id(db) -> ObjectId:
    """Busca el usuario fijo 'adminUser' (o el de entorno) en la colección de usuarios."""
    username = AUTHOR_USERNAME
    query = {
        "$or": [
            {"username": {"$regex": f"^{username}$", "$options": "i"}},
            {"userName": {"$regex": f"^{username}$", "$options": "i"}},
            {"name": {"$regex": f"^{username}$", "$options": "i"}},
        ]
    }
    user = db[USERS_COLL].find_one(query)
    if not user:
        raise RuntimeError(f"No se encontró el usuario '{username}' en la colección '{USERS_COLL}'.")
    uid = user.get("_id")
    if not isinstance(uid, ObjectId):
        if not ObjectId.is_valid(str(uid)):
            raise RuntimeError(f"El _id del usuario '{username}' no es un ObjectId válido: {uid}")
        uid = ObjectId(str(uid))
    return uid

# ============ NUEVO: ventana "semana actual" (Europa/Madrid) ============
def current_week_window_utc_for_madrid(start_weekday: int = 1):
    """
    Devuelve (inicio_utc, fin_utc) de la semana actual en Europe/Madrid.
    start_weekday: 1=lunes ... 7=domingo (por defecto lunes a domingo).
    """
    tz_madrid = ZoneInfo("Europe/Madrid")
    today = datetime.now(tz_madrid).date()
    weekday = today.isoweekday()  # 1-7
    delta_days = (weekday - start_weekday) % 7
    start_local = datetime.combine(today - timedelta(days=delta_days), time(0, 0), tzinfo=tz_madrid)
    end_local = start_local + timedelta(days=7)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)

def today_window_utc_for_madrid():
    """Devuelve (inicio_utc, fin_utc) del día actual en Europa/Madrid."""
    tz_madrid = ZoneInfo("Europe/Madrid")
    today_madrid = datetime.now(tz_madrid).date()
    start_madrid = datetime.combine(today_madrid, time(0, 0), tzinfo=tz_madrid)
    end_madrid = start_madrid + timedelta(days=1)
    return start_madrid.astimezone(timezone.utc), end_madrid.astimezone(timezone.utc)

# ============ Auxiliares usados en main() ============
def build_hierarchy(categories):
    by_id = {str_id(c.get("_id")): c for c in categories}
    by_parent = {}
    for c in categories:
        pid = str_id(c.get("parent")) if c.get("parent") else None
        by_parent.setdefault(pid, []).append(c)
    return by_id, by_parent

def guess_parent_and_subcat_for_tag(tag, categories, by_id, by_parent):
    """Heurística para asociar un tag a (parent, subcategory)."""
    cand_ids = [tag.get("categoryId"), tag.get("category_id"), tag.get("categoryRef")]
    cand_names = [tag.get("categoryName"), tag.get("category")]
    arr_keys = ("categories", "categoryIds", "category_ids")

    ids_norm = [str_id(x) for x in cand_ids if x]
    names_norm = [str(x).strip() for x in cand_names if x]

    for cid in ids_norm:
        c = by_id.get(cid)
        if c:
            parent_id = str_id(c.get("parent")) if c.get("parent") else None
            if parent_id:
                return by_id.get(parent_id), c
            else:
                children = by_parent.get(str_id(c.get("_id")), [])
                if children:
                    return c, random.choice(children)

    for name in names_norm:
        for c in categories:
            if str(c.get("name") or c.get("title") or "").strip() == name:
                parent_id = str_id(c.get("parent")) if c.get("parent") else None
                if parent_id:
                    return by_id.get(parent_id), c
                else:
                    children = by_parent.get(str_id(c.get("_id")), [])
                    if children:
                        return c, random.choice(children)

    for key in arr_keys:
        if key in tag:
            for raw in as_list(tag.get(key)):
                cid = str_id(raw)
                c = by_id.get(cid)
                if c:
                    parent_id = str_id(c.get("parent")) if c.get("parent") else None
                    if parent_id:
                        return by_id.get(parent_id), c
                    else:
                        children = by_parent.get(str_id(c.get("_id")), [])
                        if children:
                            return c, random.choice(children)

    parent_candidates = [c for c in categories if str_id(c.get("_id")) in by_parent]
    if not parent_candidates:
        return None, None
    parent = random.choice(parent_candidates)
    children = by_parent.get(str_id(parent.get("_id")), [])
    subcat = random.choice(children) if children else None
    return parent, subcat

def find_subcats_with_tags(categories, by_parent, tags, tags_by_id, tags_by_name):
    """Devuelve lista de subcategorías que tienen al menos 1 tag relacionado."""
    subcats_with_tags = []
    for parent_id, subs in by_parent.items():
        if parent_id is None:
            continue
        for sc in subs:
            rel = get_related_tags_for_category(sc, tags, tags_by_id, tags_by_name)
            if rel:
                subcats_with_tags.append((parent_id, sc, rel))
    return subcats_with_tags

# ======= CAMBIO: permitir tags aunque ya tengan artículos =========
def pick_random_subcat_and_tag_without_article(db, categories, by_id, by_parent, tags, tags_by_id, tags_by_name):
    """
    Elige aleatoriamente una subcategoría con tags y devuelve (parent, subcat, tag),
    SIN descartar tags que ya tengan artículos previos.
    """
    candidates = find_subcats_with_tags(categories, by_parent, tags, tags_by_id, tags_by_name)
    random.shuffle(candidates)

    for parent_id, subcat, rel_tags in candidates:
        random.shuffle(rel_tags)
        t = random.choice(rel_tags)
        parent = by_id.get(parent_id) if parent_id else None
        return parent, subcat, t

    if candidates:
        parent_id, subcat, rel_tags = random.choice(candidates)
        t = random.choice(rel_tags)
        parent = by_id.get(parent_id) if parent_id else None
        return parent, subcat, t

    if tags:
        t = random.choice(tags)
        parent, subcat = guess_parent_and_subcat_for_tag(t, categories, by_id, by_parent)
        return parent, subcat, t

    return None, None, None

def get_recent_titles(db, limit=50):
    cur = db[ARTICLES_COLL].find({}, {"title": 1}).sort("createdAt", -1).limit(limit)
    titles = [d.get("title", "") for d in cur if d.get("title")]
    if len(titles) < limit:
        cur2 = db[ARTICLES_COLL].find({}, {"title": 1}).sort("_id", -1).limit(limit)
        titles2 = [d.get("title", "") for d in cur2 if d.get("title")]
        seen, final = set(), []
        for t in titles + titles2:
            if t not in seen:
                seen.add(t)
                final.append(t)
        return final[:limit]
    return titles

def ensure_article_for_tag(db, client_ai, tag, parent, subcat, recent_titles, author_id):
    """Genera e inserta un artículo para un tag SIEMPRE (aunque ya exista alguno). Devuelve True si creó algo."""
    tag_id = ObjectId(str_id(tag.get("_id")))

    # Diferente: ya no se aborta si existe; solo se usan títulos para evitar parecidos
    existing_for_tag = list(db[ARTICLES_COLL].find({"tags": tag_id}, {"title": 1}))
    existing_titles_for_tag = [d.get("title", "") for d in existing_for_tag if d.get("title")]

    parent_name = parent.get("name") if parent else str_id(parent.get("_id")) if parent else "General"
    subcat_name = subcat.get("name") if subcat else str_id(subcat.get("_id")) if subcat else "General"
    tag_text = tag_name(tag)

    # Evita títulos recientes y del mismo tag
    avoid_titles = (recent_titles[:10] if recent_titles else []) + existing_titles_for_tag[:20]

    max_attempts = 5
    attempt = 0
    title = summary = body = None

    while attempt < max_attempts:
        attempt += 1
        t, s, b = generate_article_with_ai(client_ai, parent_name, subcat_name, tag_text, avoid_titles=avoid_titles)
        if is_too_similar(t, recent_titles[:20], threshold=0.86) or is_too_similar(t, existing_titles_for_tag, threshold=0.86):
            notify("Título similar detectado", f"Intento {attempt}: '{t}'. Reintentando...", level="warning", always_email=True)
            avoid_titles.append(t)
            continue
        title, summary, body = t, s, b
        break

    if not title or not body:
        notify("No se pudo generar título único", "Tras varios intentos no se logró un título suficientemente diferente.", level="error", always_email=True)
        return False

    base_slug = slugify(title)
    slug = next_available_slug(db, base_slug)
    now = now_utc()

    doc = {
        "title": title,
        "slug": slug,
        "summary": summary,
        "body": body,
        "category": ObjectId(str_id(subcat.get("_id"))) if subcat else None,
        "tags": [tag_id],
        "author": author_id,
        "status": "published",
        "likes": [],
        "favoritedBy": [],
        "isVisible": True,
        "publishDate": now,
        "generatedAt": now,
        "createdAt": now,
        "updatedAt": now,
        "images": None,
    }

    # Inserta
    res = db[ARTICLES_COLL].insert_one(doc)
    notify("Artículo publicado",
           f"Título: {title}<br>Slug: {SITE}/post/{slug if SITE else slug}<br>Tag: {tag_text} (id={str_id(tag.get('_id'))})",
           level="success", always_email=True)
    # actualiza recientes para ayudar al siguiente tag
    recent_titles.insert(0, title)
    if len(recent_titles) > 50:
        del recent_titles[50:]
    return True

# ============ MAIN ============
def main():
    notify("Inicio de proceso", "Comenzando ejecución de publicación automática.", level="info", always_email=True)

    # Validaciones de entorno mínimas
    missing = []
    if not OPENAIAPIKEY: missing.append("OPENAIAPIKEY")
    if not MONGODB_URI:  missing.append("MONGODB_URI")
    if not DB_NAME:      missing.append("DB_NAME")
    if not ARTICLES_COLL: missing.append("ARTICLES_COLL")
    if not USERS_COLL:    missing.append("USERS_COLL")
    if not CATEGORY_COLL: missing.append("CATEGORY_COLL")
    if not TAGS_COLL:     missing.append("TAGS_COLL")

    if missing:
        msg = "Faltan variables de entorno: " + ", ".join(missing)
        notify("Configuración incompleta", msg, level="error", always_email=True)
        sys.exit(1)

    # Conexión a Mongo
    try:
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        db = client[DB_NAME]
        notify("Conexión a MongoDB", f"Base de datos '{DB_NAME}' conectada correctamente.", level="success", always_email=True)
    except Exception as e:
        notify("Error de conexión a MongoDB", str(e), level="error", always_email=True)
        sys.exit(1)

    # ===== Limitar a 1 artículo por semana (Europa/Madrid, lunes-domingo) =====
    try:
        start_utc, end_utc = current_week_window_utc_for_madrid(start_weekday=1)  # 1 = lunes
        already_this_week = db[ARTICLES_COLL].count_documents({
            "publishDate": {"$gte": start_utc, "$lt": end_utc},
            "status": "published"
        })

        if already_this_week >= 1:
            last_doc = db[ARTICLES_COLL].find(
                {"publishDate": {"$gte": start_utc, "$lt": end_utc}, "status": "published"},
                {"title": 1, "slug": 1, "publishDate": 1}
            ).sort("publishDate", -1).limit(1)
            last_article = next(iter(last_doc), None)
            if last_article:
                last_title = last_article.get("title", "(sin título)")
                last_slug  = last_article.get("slug", "")
                last_date  = last_article.get("publishDate")
                link = f"{SITE}/post/{last_slug}" if SITE and last_slug else last_slug
                notify("Límite semanal alcanzado",
                       f"Ya existe al menos un artículo esta semana.<br><b>Título:</b> {last_title}<br><b>Slug:</b> {link}<br><b>Fecha:</b> {last_date.isoformat() if last_date else 'N/D'}",
                       level="warning", always_email=True)
            else:
                notify("Límite semanal alcanzado", "Ya existe al menos un artículo esta semana (no se pudo recuperar el detalle).", level="warning", always_email=True)

            print("🟨 Ya hay un artículo publicado esta semana. Se cancela la ejecución.")
            sys.exit(0)   # cortar ejecución si ya hay uno esta semana

    except Exception as e:
        notify("Error comprobando límite semanal", str(e), level="error", always_email=True)
        sys.exit(1)

    # Carga básica necesaria para continuar
    try:
        categories = list(db[CATEGORY_COLL].find({}))
        tags = list(db[TAGS_COLL].find({}))
        notify("Datos cargados", f"Categorías: {len(categories)}; Tags: {len(tags)}.", level="info", always_email=True)
    except Exception as e:
        notify("Error consultando colecciones", str(e), level="error", always_email=True)
        sys.exit(1)

    if not categories:
        notify("Sin categorías", "No hay categorías en la colección.", level="warning", always_email=True)
        return

    if not tags:
        notify("Sin tags", "No hay tags en la colección.", level="warning", always_email=True)
        return

    # Autor
    try:
        author_id = find_author_id(db)
        notify("Autor encontrado", f"{AUTHOR_USERNAME} (id={author_id})", level="success", always_email=True)
    except Exception as e:
        notify("Autor no encontrado", str(e), level="error", always_email=True)
        sys.exit(1)

    # Índices/jerarquía
    by_id, by_parent = build_hierarchy(categories)
    tags_by_id, tags_by_name = index_tags(tags)

    # Títulos recientes para control de parecido
    recent_titles = get_recent_titles(db, limit=50)
    notify("Control de similitud", f"Títulos recientes cargados: {len(recent_titles)}", level="info", always_email=True)

    # Cliente OpenAI
    try:
        client_ai = OpenAI(api_key=OPENAIAPIKEY)
        notify("OpenAI listo", f"Modelo: {OPENAI_MODEL}", level="info", always_email=True)
    except Exception as e:
        notify("Error inicializando OpenAI", str(e), level="error", always_email=True)
        sys.exit(1)

    # Elegir subcategoría y tag (permitiendo repetidos)
    parent, subcat, tag = pick_random_subcat_and_tag_without_article(
        db, categories, by_id, by_parent, tags, tags_by_id, tags_by_name
    )

    if not tag:
        notify("Selección fallida", "No se pudo seleccionar (subcategoría, tag) para generar un artículo.", level="error", always_email=True)
        sys.exit(1)

    notify("Selección realizada",
           f"Parent: {parent.get('name') if parent else 'N/D'}; Subcat: {subcat.get('name') if subcat else 'N/D'}; Tag: {tag_name(tag)}",
           level="info", always_email=True)

    # Publica exactamente 1 artículo (cumpliendo el límite semanal ya comprobado)
    created = False
    try:
        created = ensure_article_for_tag(db, client_ai, tag, parent, subcat, recent_titles, author_id)
    except Exception as e:
        notify("Error generando/insertando artículo", f"Tag '{tag_name(tag)}' :: {e}", level="error", always_email=True)

    if created:
        notify("Proceso terminado", "Artículos creados: 1 (límite semanal alcanzado).", level="success", always_email=True)
        print("\n🟦 Límite semanal alcanzado (1). Proceso detenido.")
        print("\n🟩 Proceso terminado. Artículos creados: 1")
    else:
        notify("Proceso terminado", "Artículos creados: 0 (posiblemente ya existía un título muy similar).", level="warning", always_email=True)
        print("\n🟩 Proceso terminado. Artículos creados: 0")

if __name__ == "__main__":
    main()
