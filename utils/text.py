"""
Matnni bir xil ko'rinishga keltirish.

PDF parser va qo'lda kiritishdan kelgan matnda bir so'z ichida kirill va lotin
aralashib ketadi («О‘zbekiston» — kirill О), ligaturalar (ﬁ) va uch xil apostrof
uchraydi. Bu saralash va ko'rinishni buzadi. Bu yerda faqat yozuv shakli
to'g'rilanadi: so'z o'zgartirilmaydi, yangi matn qo'shilmaydi.

Apostrof qoidasi: o/g dan keyin ‘ (U+2018), qolgan joyda tutuq belgisi ’ (U+2019).
Modifikator harflar (U+02BB/U+02BC) ishlatilmaydi: sayt shrifti IBM Plex Sans'da
ular juda keng chiqadi («so ʻz»).
"""
import re
import unicodedata

O_G_MARK = '‘'
GLOTTAL_MARK = '’'
_APOSTROPHES = "'‘’ʻʼ`´ʹ′"

_LIGATURES = {'ﬀ': 'ff', 'ﬁ': 'fi', 'ﬂ': 'fl', 'ﬃ': 'ffi', 'ﬄ': 'ffl', 'ﬅ': 'st', 'ﬆ': 'st'}

# Lotin harfiga ko'rinishi bir xil kirill harflari
_HOMOGLYPHS = {
    'а': 'a', 'е': 'e', 'о': 'o', 'р': 'p', 'с': 'c', 'у': 'y', 'х': 'x', 'і': 'i', 'ј': 'j',
    'А': 'A', 'В': 'B', 'Е': 'E', 'К': 'K', 'М': 'M', 'Н': 'H', 'О': 'O', 'Р': 'P',
    'С': 'C', 'Т': 'T', 'У': 'Y', 'Х': 'X', 'І': 'I', 'Ј': 'J',
}

_LATIN = re.compile(r'[A-Za-z]')
_CYRILLIC = re.compile(r'[Ѐ-ӿ]')
_WORD = re.compile(rf"[^\W\d_]+(?:[{_APOSTROPHES}][^\W\d_]+)*[{_APOSTROPHES}]?", re.UNICODE)
_APOSTROPHE_IN_WORD = re.compile(rf"(?<=[A-Za-z])[{_APOSTROPHES}]")


def _fix_homoglyphs(word: str) -> str:
    """Lotin so'z ichidagi kirill harflarini almashtiradi (aralash so'zlardagina)."""
    if not (_LATIN.search(word) and _CYRILLIC.search(word)):
        return word
    letters = [ch for ch in word if _CYRILLIC.match(ch)]
    if not all(ch in _HOMOGLYPHS for ch in letters):
        return word
    return ''.join(_HOMOGLYPHS.get(ch, ch) for ch in word)


def _fix_apostrophes(word: str) -> str:
    """Lotin so'zdagi apostroflar: o/g dan keyin ‘, qolgan joyda ’. Oxirgi yopuvchi qo'shtirnoq tegmaydi."""
    def repl(match: re.Match) -> str:
        prev = word[match.start() - 1].lower()
        at_end = match.end() == len(word)
        if prev in 'og':
            return O_G_MARK
        return match.group(0) if at_end else GLOTTAL_MARK
    return _APOSTROPHE_IN_WORD.sub(repl, word)


def normalize_text(text: str) -> str:
    """Aralash yozuv, ligatura, apostrof va ortiqcha bo'shliqni to'g'rilaydi."""
    if not text:
        return text
    text = unicodedata.normalize('NFC', text)
    for src, dst in _LIGATURES.items():
        text = text.replace(src, dst)
    text = _WORD.sub(lambda m: _fix_apostrophes(_fix_homoglyphs(m.group(0))), text)
    return re.sub(r'[ \t ]{2,}', ' ', text).strip()


# PDF'dan chiqqanda apostrof bo'shliqqa aylangan bo'laklar (faqat aniq holatlar)
_BROKEN_FRAGMENTS = [
    (re.compile(r'\b([OoОо]) (?=zbek)'), rf'\1{O_G_MARK}'),
    (re.compile(r'\b([Gg]) (?=arb)'), rf'\1{O_G_MARK}'),
    (re.compile(r'\b([Bb][oо]) (?=lish)'), rf'\1{O_G_MARK}'),
    (re.compile(r'\b(yutug) (?=i\b)', re.I), rf'\1{O_G_MARK}'),
]
_STRAY_APOSTROPHE = re.compile(rf'(?<=\s)[{_APOSTROPHES}](?=\s)')
_TRAILING_CAPITAL = re.compile(r'([a-z]{2,})([A-Z])(?=\W*$)')


def repair_title(title: str) -> str:
    """Sarlavhadagi PDF xatolari: tushib qolgan apostrof, ortiqcha belgi, oxirgi katta harf."""
    if not title:
        return title
    text = _STRAY_APOSTROPHE.sub('', unicodedata.normalize('NFC', title))
    text = normalize_text(text)
    for pattern, repl in _BROKEN_FRAGMENTS:
        text = pattern.sub(repl, text)
    text = _TRAILING_CAPITAL.sub(lambda m: m.group(1) + m.group(2).lower(), text)
    return normalize_text(text)


def _letters(text: str) -> list[str]:
    return [ch for ch in text if ch.isalpha()]


def _title_case_word(word: str) -> str:
    letters = _letters(word)
    if len(letters) < 2 or '.' in word or not all(ch.isupper() for ch in letters):
        return word
    return word[0] + word[1:].lower()


def normalize_person_name(name: str) -> str:
    """«KUSHBAKOV Kamoliddin» → «Kushbakov Kamoliddin». So'zlar tartibi o'zgarmaydi."""
    text = normalize_text(name)
    return ' '.join(_title_case_word(word) for word in text.split())


def sentence_case(text: str) -> str:
    """Jurnal rubrikasi: «MUTOLAA MADANIYATI» → «Mutolaa madaniyati», nuqtadan keyin yana katta harf."""
    text = normalize_text(text)
    letters = _letters(text)
    if not letters or not all(ch.isupper() for ch in letters):
        return text
    parts = re.split(r'(\.\s+)', text.lower())
    return ''.join(part[:1].upper() + part[1:] if i % 2 == 0 else part for i, part in enumerate(parts))


def detect_language(text: str) -> str:
    """Sarlavha tili: 'uz' (lotin), 'uz-cyrl', 'ru' yoki 'en'. Aralash so'zlar avval tozalanadi."""
    clean = normalize_text(text or '')
    latin = len(_LATIN.findall(clean))
    cyrillic = len(_CYRILLIC.findall(clean))
    if cyrillic > latin:
        return 'uz-cyrl' if re.search(r'[ўқғҳЎҚҒҲ]', clean) else 'ru'
    words = re.findall(r"[a-z]+", clean.lower())
    english = {'the', 'and', 'of', 'in', 'for', 'with', 'study', 'library', 'libraries', 'research', 'analysis', 'digital', 'on'}
    uzbek = {'va', 'bilan', 'uchun', 'haqida', 'asosida', 'kutubxona', 'kitob'}
    if sum(w in english for w in words) >= 2 and not any(w in uzbek for w in words):
        return 'en'
    return 'uz'
