"""
Qidiruv uchun yozuvga bog'liq bo'lmagan moslash.

Bazadagi matn bir xil emas: «O'zbekiston», «O‘zbekiston», «Ўзбекистон» va PDF'dan
kelgan aralash «О‘zbekiston» (kirill О + lotin) ham uchraydi. Oddiy `icontains`
ularni har xil so'z deb biladi. Shuning uchun so'rovdagi har bir harf lotin va
kirill variantlarini qamraydigan regex'ga aylantiriladi; apostrof, ъ va ь esa
harflar orasida ixtiyoriy. Bazadagi matn o'zgarmaydi, migratsiya kerak emas.
"""
import re
import unicodedata
from functools import reduce
from operator import or_

from django.db.models import Q
from rest_framework import filters

# Juda uzun so'rov regex'ni og'irlashtirmasligi uchun chegara
MAX_TERM_LENGTH = 64
MAX_TERMS = 8

_APOSTROPHES = "'‘’ʻʼ`´ʹ′"
_APOSTROPHE_RE = re.compile(f'[{_APOSTROPHES}ъь]')
_OPTIONAL_APOSTROPHE = f'[{_APOSTROPHES}ъь]?'

_CYRILLIC_TO_LATIN = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
    'ж': 'j', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'x', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sh', 'ы': 'i',
    'э': 'e', 'ю': 'yu', 'я': 'ya', 'ў': 'o', 'қ': 'q', 'ғ': 'g', 'ҳ': 'h',
    'і': 'i', 'һ': 'h',
}

_E = '(?:y?[eе]|э)'

# Lotin birligi → matnda uchrashi mumkin bo'lgan shakllari. Sinflarda transliteratsiya
# bilan birga ko'rinishi bir xil harflar ham bor (PDF matnidagi lotin «p» o'rnida «р»).
_VARIANTS = {
    'sh': '(?:sh|ш|щ)', 'ch': '(?:ch|ч)', 'ts': '(?:t[sс]|ц)', 'ye': _E,
    'ya': '(?:[yй][aа]|я)', 'yu': '(?:[yй][uу]|ю)', 'yo': '(?:[yй][oо]|ё)',
    'a': '[aа]', 'b': '[bб]', 'c': '[cсц]', 'd': '[dд]', 'e': _E, 'f': '[fф]',
    'g': '[gгғ]', 'h': '[hҳһ]', 'i': '[iиіы]', 'j': '[jж]', 'k': '[kк]',
    'l': '[lл]', 'm': '[mм]', 'n': '[nн]', 'o': '[oоў]', 'p': '[pпр]',
    'q': '[qқ]', 'r': '[rр]', 's': '[sсц]', 't': '[tт]', 'u': '[uу]',
    'v': '[vв]', 'w': '[wв]', 'x': '[xх]', 'y': '[yйыу]', 'z': '[zз]',
}
_TOKEN_RE = re.compile('sh|ch|ts|ye|ya|yu|yo|.', re.S)


def term_regex(term: str) -> str:
    """Bitta so'zni iregex shabloniga aylantiradi (PostgreSQL va SQLite uchun)."""
    text = unicodedata.normalize('NFC', term).lower()
    text = _APOSTROPHE_RE.sub('', text)
    text = ''.join(_CYRILLIC_TO_LATIN.get(ch, ch) for ch in text)[:MAX_TERM_LENGTH]
    if not text:
        return re.escape(term[:MAX_TERM_LENGTH])

    parts = []
    for token in _TOKEN_RE.findall(text):
        if token.isspace():
            parts.append(r'\s+')
        else:
            parts.append(_VARIANTS.get(token) or re.escape(token))
    return _OPTIONAL_APOSTROPHE.join(parts)


def search_q(text: str, fields) -> Q:
    """Har bir so'z berilgan maydonlardan kamida bittasida bo'lishi kerak."""
    condition = Q()
    for term in text.split()[:MAX_TERMS]:
        pattern = term_regex(term)
        condition &= reduce(or_, (Q(**{f'{field}__iregex': pattern}) for field in fields))
    return condition


class FoldedSearchFilter(filters.SearchFilter):
    """`?search=` — DRF SearchFilter, lekin yozuv va apostrofga qaramaydi."""

    def construct_search(self, field_name, queryset=None):
        return f'{field_name}__iregex'

    def get_search_terms(self, request):
        return [term_regex(term) for term in list(super().get_search_terms(request))[:MAX_TERMS]]
