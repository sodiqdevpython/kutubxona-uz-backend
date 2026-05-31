"""
Gemini AI yordamida maqola faylidan metama'lumotlarni ajratish.

Faqat matn (string) yuboriladi — butun fayl emas. Tez va barqaror ishlashi uchun
strukturali JSON sxema (responseSchema) ishlatiladi.
"""
from __future__ import annotations

import json
import requests
from django.conf import settings

API_BASE = 'https://generativelanguage.googleapis.com/v1beta/models'

# Gemini'ga yuboriladigan maksimal matn (tezlik uchun). Odatda sarlavha, mualliflar,
# annotatsiya, kalit so'zlar boshida; references oxirida — shuning uchun bosh + oxirni olamiz.
HEAD_CHARS = 14000
TAIL_CHARS = 6000

RESPONSE_SCHEMA = {
    'type': 'object',
    'properties': {
        'title':      {'type': 'string'},
        'authors':    {'type': 'array', 'items': {'type': 'string'}},
        'keywords':   {'type': 'array', 'items': {'type': 'string'}},
        'abstract':   {'type': 'string'},
        'references': {'type': 'string'},
    },
    'required': ['title', 'authors', 'keywords', 'abstract', 'references'],
}

PROMPT = (
    "Sen ilmiy maqolalarni tahlil qiluvchi yordamchisan. Quyidagi maqola matnidan "
    "metama'lumotlarni ajratib ol va FAQAT JSON qaytar.\n\n"
    "Qoidalar:\n"
    "- title: maqolaning to'liq sarlavhasi (asl tilda).\n"
    "- authors: barcha mualliflarning to'liq ism-familiyasi ro'yxati. Agar topilmasa, bo'sh ro'yxat.\n"
    "- keywords: 4-8 ta kalit so'z. Matnda 'kalit so'zlar'/'keywords' bo'lsa o'shandan, "
    "bo'lmasa mazmunidan chiqar.\n"
    "- abstract: annotatsiya/abstract matni (2-5 jumla). Bo'lmasa kirish qismidan qisqacha tuz.\n"
    "- references: foydalanilgan adabiyotlar ro'yxati matn ko'rinishida. Bo'lmasa bo'sh satr.\n"
    "- Til: maqola qaysi tilda bo'lsa, shu tilda qaytar (odatda o'zbek).\n\n"
    "MAQOLA MATNI:\n"
    "----------\n"
    "{text}\n"
    "----------\n"
)


def _trim(text: str) -> str:
    text = (text or '').strip()
    if len(text) <= HEAD_CHARS + TAIL_CHARS:
        return text
    return text[:HEAD_CHARS] + '\n\n[...]\n\n' + text[-TAIL_CHARS:]


def extract_metadata(text: str) -> dict:
    """
    Maqola matnidan metama'lumot ajratadi.

    Qaytaradi: {
        'ok': bool,
        'title': str, 'authors': [str], 'keywords': [str],
        'abstract': str, 'references': str,
        'error': str | None,
    }
    """
    api_key = getattr(settings, 'GEMINI_API_KEY', '')
    model   = getattr(settings, 'GEMINI_MODEL', 'gemini-flash-latest')

    if not api_key:
        return {'ok': False, 'error': 'KEY sozlanmagan'}

    clean = _trim(text)
    if len(clean) < 40:
        return {'ok': False, 'error': 'Fayldan yetarli matn ajratilmadi'}

    url = f'{API_BASE}/{model}:generateContent'
    body = {
        'contents': [{'parts': [{'text': PROMPT.format(text=clean)}]}],
        'generationConfig': {
            'responseMimeType': 'application/json',
            'responseSchema':   RESPONSE_SCHEMA,
            'temperature':      0.2,
        },
    }
    headers = {'Content-Type': 'application/json', 'X-goog-api-key': api_key}

    try:
        resp = requests.post(url, headers=headers, json=body, timeout=45)
    except requests.RequestException as exc:
        return {'ok': False, 'error': f'Tarmoq xatosi: {exc}'}

    if resp.status_code != 200:
        return {'ok': False, 'error': f'API xatosi ({resp.status_code})'}

    try:
        raw = resp.json()['candidates'][0]['content']['parts'][0]['text']
        data = json.loads(raw)
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        return {'ok': False, 'error': f'Javobni o\'qib bo\'lmadi: {exc}'}

    return {
        'ok':         True,
        'title':      (data.get('title') or '').strip(),
        'authors':    [a.strip() for a in (data.get('authors') or []) if a and a.strip()],
        'keywords':   [k.strip() for k in (data.get('keywords') or []) if k and k.strip()],
        'abstract':   (data.get('abstract') or '').strip(),
        'references': (data.get('references') or '').strip(),
        'error':      None,
    }
