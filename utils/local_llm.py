"""
Local LLM (Ollama) yordamida maqola faylidan metama'lumotlarni ajratish.
Gemini o'rniga ishlatiladi — Django FileField (PDF/DOCX) to'g'ridan-to'g'ri
local LLM API ga yuboriladi.

Pipeline:
  1) POST /api/v1/documents/upload/        — faylni yuklash (bir marta)
  2) GET  /api/v1/documents/{id}/status/   — ready bo'lguncha polling
  3) POST /api/v1/documents/{id}/query/    — har bir field uchun alohida savol

LLM JSON ni yaxshi qaytarmaydi, shuning uchun 5 ta sodda inglizcha savol
beriladi va `answer_uz` (API avtomatik o'zbekchaga tarjima qilgan javob) raw
matn sifatida olinadi. Authors/keywords vergul yoki yangi qator bo'yicha
bo'linadi. LLM "topa olmadim" / "I cannot find" desa, o'sha field bo'sh qoladi.

Base URL: https://sodiqdevpython.jprq.live (settings.LOCAL_LLM_BASE_URL bilan o'zgartiriladi)
"""
from __future__ import annotations

import re
import time

import requests
from django.conf import settings

DEFAULT_BASE = 'https://sodiqdevpython.jprq.live'

UPLOAD_TIMEOUT = (10, 60)
STATUS_TIMEOUT = (10, 15)
QUERY_TIMEOUT  = (10, 45)
POLL_INTERVAL  = 3
POLL_DEADLINE  = 90

# Har bir field uchun bitta sodda inglizcha savol. LLM ingliz tilida yaxshi javob beradi;
# API `source_language: "en"` ko'rsatib, `answer_uz` da o'zbekcha tarjimani qaytaradi.
QUESTIONS: list[tuple[str, str]] = [
    ('title',
     "What is the full title of this article? Reply with only the title text. "
     "Do not add any labels, prefixes, quotes, or explanation."),
    ('authors',
     "List the full names of all authors of this article. Reply with only their names "
     "separated by commas. Do not add labels, numbers, affiliations, or explanation."),
    ('keywords',
     "List 5 to 8 keywords for this article. Reply with only the keywords separated by commas. "
     "Do not add labels, numbering, or explanation."),
    ('abstract',
     "Write the abstract of this article in 2 to 5 sentences. Reply with only the abstract text. "
     "Do not add any labels or prefixes."),
    ('references',
     "List all bibliographic references / works cited in this article. Reply with each reference "
     "on its own line. Do not add any labels, headers, or commentary."),
]

# LLM "topa olmadim" turidagi javoblari — bo'shga aylantiramiz
NEGATIVE_RE = re.compile(
    r"^(i\s+(cannot|can\s*not|can'?t|do\s*not|don'?t|am\s+unable)|"
    r"there\s+(is|are)\s+no|no\s+(information|data|title|authors?|keywords?|abstract|references?)|"
    r"not\s+(found|available|provided|specified|mentioned)|"
    r"unable\s+to|sorry|n\s*/\s*a|none(\s+(found|available|listed))?|"
    r"topilmadi|topa\s+olmadim|topa\s+olmayman|mavjud\s+emas|ma'?lumot\s+yo'?q|aniqlan?madi)",
    re.IGNORECASE
)

# Field labellari (LLM ba'zan "Title: ..." deb boshlaydi — kesib tashlash)
LABEL_RE = re.compile(
    r"^\s*(title|sarlavha|authors?|mualliflar?|keywords?|kalit\s*so'?zlar?|"
    r"abstract|abstrakt|annotatsiya|references?|adabiyotlar?|ma'?lumotnomalar?)"
    r"\s*[:：\-–—]+\s*",
    re.IGNORECASE
)


def _base() -> str:
    return getattr(settings, 'LOCAL_LLM_BASE_URL', DEFAULT_BASE).rstrip('/')


def _clean(text: str) -> str:
    """LLM javobidan label prefikslar, markdown wrapper va tirnoqlarni olib tashlaydi."""
    if not text:
        return ''
    s = text.strip()
    # Markdown wrapperlar, label, prefikslarni stabilizatsiya bo'lguncha takror tozalaymiz
    for _ in range(4):
        prev = s
        s = re.sub(r'^[*_`#>~\s]+', '', s)
        s = re.sub(r'[*_`#~]+$', '', s).rstrip()
        s = LABEL_RE.sub('', s).strip()
        if s == prev:
            break
    # Surrounding quotes
    if len(s) >= 2 and s[0] in '"\'`«' and s[-1] in '"\'`»':
        s = s[1:-1].strip()
    return s


def _is_negative(text: str) -> bool:
    if not text:
        return True
    return bool(NEGATIVE_RE.match(text.strip()))


def _split_items(text: str) -> list[str]:
    """Authors/keywords ro'yxati uchun: vergul, nuqta-vergul, yangi qator bo'yicha bo'lish."""
    if not text:
        return []
    parts = re.split(r'[,;\n]+', text)
    out: list[str] = []
    for p in parts:
        item = p.strip()
        # 1. / "- " kabi raqam-prefikslarni olib tashlash
        item = re.sub(r'^\s*[\-\*•]\s*|^\s*\d+[.)]\s*', '', item).strip()
        # surrounding quotes
        if len(item) >= 2 and item[0] in '"\'`«' and item[-1] in '"\'`»':
            item = item[1:-1].strip()
        if item and not _is_negative(item) and len(item) <= 200:
            out.append(item)
    return out


def _ask(base: str, doc_id, question: str) -> str:
    """Bitta savol → `answer_uz` raw matn (xato bo'lsa bo'sh satr)."""
    try:
        r = requests.post(
            f'{base}/api/v1/documents/{doc_id}/query/',
            json={'question': question, 'source_language': 'en'},
            timeout=QUERY_TIMEOUT,
        )
    except requests.RequestException:
        return ''
    if r.status_code != 200:
        return ''
    try:
        d = r.json()
    except Exception:
        return ''
    return (d.get('answer_uz') or d.get('answer_en') or d.get('answer') or '').strip()


def upload_and_wait(file_field, filename: str | None = None) -> tuple[str | None, str | None]:
    """
    Django FileField (PDF/DOCX) ni LLM ga yuklaydi va ready bo'lguncha kutadi.
    Qaytaradi: (doc_id, None) muvaffaqiyatda yoki (None, error_message) xato bo'lsa.
    """
    if not file_field:
        return None, 'Fayl yo\'q'

    base = _base()

    try:
        file_field.open('rb')
        raw = file_field.read()
    except Exception as exc:
        return None, f'Faylni o\'qib bo\'lmadi: {exc}'
    finally:
        try:
            file_field.close()
        except Exception:
            pass

    name = filename or getattr(file_field, 'name', 'document')
    short_name = name.rsplit('/', 1)[-1].rsplit('\\', 1)[-1] or 'document'

    try:
        r = requests.post(
            f'{base}/api/v1/documents/upload/',
            files={'file': (short_name, raw)},
            timeout=UPLOAD_TIMEOUT,
        )
    except requests.Timeout:
        return None, 'Local LLM ulanish vaqti tugadi (upload)'
    except requests.RequestException as exc:
        return None, f'Local LLM ga ulanmadi: {exc}'

    if r.status_code not in (200, 201, 202):
        return None, f'Local LLM upload xatosi ({r.status_code}): {r.text[:200]}'

    try:
        doc_id = r.json().get('id')
    except Exception:
        return None, 'Local LLM upload javobi noto\'g\'ri'

    if doc_id is None:
        return None, 'Local LLM hujjat ID qaytarmadi'

    # Status polling
    deadline = time.monotonic() + POLL_DEADLINE
    while True:
        if time.monotonic() > deadline:
            return None, 'Local LLM hujjatni tayyorlashga ulgurmadi (timeout)'
        try:
            sr = requests.get(
                f'{base}/api/v1/documents/{doc_id}/status/',
                timeout=STATUS_TIMEOUT,
            )
            sd = sr.json()
        except requests.RequestException:
            time.sleep(POLL_INTERVAL)
            continue

        status = sd.get('status')
        if sd.get('ready') is True or status == 'ready':
            return str(doc_id), None
        if status == 'error':
            return None, sd.get('error_message') or 'Local LLM tahlilida xato'
        time.sleep(POLL_INTERVAL)


def ask(doc_id: str, question_en: str, source_language: str = 'en') -> tuple[str | None, str | None]:
    """
    Yuklangan hujjatga savol beradi va `answer_uz` (avtomatik tarjima qilingan) javobini qaytaradi.
    `source_language` — savol qaysi tilda yozilgan ('en' yoki 'uz').
    Qaytaradi: (answer_text, None) yoki (None, error).
    Hujjat topilmasa ('not found' / 404) — (None, 'not_found') qaytadi (caller qayta upload qilishi mumkin).
    """
    base = _base()
    try:
        r = requests.post(
            f'{base}/api/v1/documents/{doc_id}/query/',
            json={'question': question_en, 'source_language': source_language},
            timeout=QUERY_TIMEOUT,
        )
    except requests.Timeout:
        return None, 'Local LLM javobi juda uzoq cho\'zildi'
    except requests.RequestException as exc:
        return None, f'Local LLM ga ulanmadi: {exc}'

    if r.status_code == 404:
        return None, 'not_found'
    if r.status_code != 200:
        return None, f'Local LLM xatosi ({r.status_code}): {r.text[:200]}'

    try:
        d = r.json()
    except Exception:
        return None, 'Local LLM javobi JSON emas'

    ans = (d.get('answer_uz') or d.get('answer_en') or d.get('answer') or '').strip()
    if not ans:
        return None, d.get('error') or 'Local LLM bo\'sh javob qaytardi'
    return ans, None


def extract_metadata_from_file(file_field, filename: str | None = None) -> dict:
    """
    Django FileField (PDF/DOCX) → metama'lumot.
    Qaytaradi:
      {'ok': True, 'title', 'authors', 'keywords', 'abstract', 'references', 'error': None}
      yoki upload/poll fail bo'lsa {'ok': False, 'error': '...'}.
    Query bosqichida ayrim savollar fail bo'lsa — o'sha fieldlar bo'sh qoladi, qolganlari saqlanadi.
    """
    doc_id, err = upload_and_wait(file_field, filename)
    if err:
        return {'ok': False, 'error': err}

    base = _base()
    answers: dict[str, str] = {}
    for key, question in QUESTIONS:
        raw_ans = _ask(base, doc_id, question)
        cleaned = _clean(raw_ans)
        if _is_negative(cleaned):
            cleaned = ''
        answers[key] = cleaned

    return {
        'ok':         True,
        'doc_id':     doc_id,
        'title':      answers['title'],
        'authors':    _split_items(answers['authors']),
        'keywords':   _split_items(answers['keywords']),
        'abstract':   answers['abstract'],
        'references': answers['references'],
        'error':      None,
    }
