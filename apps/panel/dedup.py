"""
Muallif moslashtirish (dedup) — parser/qo'lda kelgan ism familiya bo'yicha
mavjud profillarni qidiradi.

Qoida (foydalanuvchi tasdiqlagan): faqat QO'LDA/PARSER orqali yaratilgan profillar
(telegram_chat_id IS NULL) nomzod bo'la oladi. Telegram profillari bot egaligida
qoladi va parser maqolasi ularga biriktirilmaydi.
"""
from apps.authors.models import Author
from utils.journal_parser import normalize, surname_token


def author_candidates(name: str) -> list[Author]:
    """Ism familiyaga mos (qo'lda/parser) mualliflar ro'yxati.

    Moslik: to'liq ism normalizatsiya bo'yicha teng YOKI familiya bo'lagi teng.
    """
    name = (name or '').strip()
    if not name:
        return []

    target_norm    = normalize(name)
    target_surname = normalize(surname_token(name))
    if not target_norm:
        return []

    out = []
    qs = Author.objects.filter(telegram_chat_id__isnull=True).order_by('name')
    for a in qs:
        a_norm    = normalize(a.name)
        a_surname = normalize(surname_token(a.name))
        if a_norm == target_norm or (target_surname and target_surname == a_surname):
            out.append(a)
    return out
