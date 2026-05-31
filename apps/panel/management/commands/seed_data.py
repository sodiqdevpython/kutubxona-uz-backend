"""
Demo ma'lumotlarni bazaga yuklash.

Ishlatish:
    cd C:/kutubxona.uz/backend
    .\\venv\\Scripts\\python.exe manage.py seed_data

Nima qo'shiladi:
    ✓  7 ta yo'nalish (category)
    ✓  8 ta muallif (author)
    ✓  1 ta jurnal + 12 ta jurnal soni (issue)
    ✓  6 ta maqola — 1.pdf...6.pdf dan (4 tasi journal da, 2 tasi drag uchun)
    ✓  5 ta topshirish (3 kutilmoqda, 2 tasdiqlangan ammo journal-siz)

Idempotent: ikkinchi marta ishlatilsa yangi narsalar qo'shmaydi.
"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

MAQOLA_DIR = Path(r'C:\kutubxona.uz\maqola')

# ── Yo'nalishlar ──────────────────────────────────────────────────────────────

CATEGORIES = [
    "Arxiv ishi",
    "Nodir nashrlar",
    "Katalogizatsiya",
    "Bibliografiya",
    "Raqamlashtirish",
    "Konservatsiya",
    "Tarix",
]

# ── Mualliflar ────────────────────────────────────────────────────────────────

AUTHORS = [
    dict(
        tag="DR",
        name="Dilshod Rahimov",
        role="Qo'lyozmalar bo'limi mudiri",
        org="O'zbekiston Milliy kutubxonasi",
        degree="Kutubxonashunoslik fanlari doktori",
        bio=(
            "O'zbekiston Milliy kutubxonasi Sharq qo'lyozmalari bo'limining mudiri. "
            "18 yildan beri qo'lyozma fondlarini raqamli kataloglash sohasida ishlaydi. "
            "Xiva xonligi davri va Buxoro madrasalari qo'lyozmalari bo'yicha 18 ta ilmiy maqola muallifi."
        ),
        avatar_idx=0,
    ),
    dict(
        tag="NS",
        name="Nodira Sodiqova",
        role="Katta ilmiy xodim",
        org="ToshDShI Sharqshunoslik instituti",
        degree="Tarix fanlari nomzodi",
        bio=(
            "Nodir qo'lyozmalar, toshbosma nashrlar va eski o'zbek imlosini o'rganish bo'yicha mutaxassis. "
            "Alisher Navoiy va Boburga oid qo'lyozmalarni tahlil qilishga ixtisoslashgan."
        ),
        avatar_idx=1,
    ),
    dict(
        tag="AY",
        name="Akmal Yusupov",
        role="Katalogizatsiya bo'limi",
        org="O'zbekiston Milliy kutubxonasi",
        degree="Pedagogika fanlari nomzodi",
        bio=(
            "BIBFRAME 2.0 va Linked Data standartlarini O'zbekiston kutubxonalarida joriy etish bo'yicha "
            "yetakchi mutaxassis. 22 ta nashr muallifi."
        ),
        avatar_idx=2,
    ),
    dict(
        tag="GK",
        name="Gulchehra Karimova",
        role="Bibliografiya bo'limi",
        org="Alisher Navoiy nomidagi davlat adabiyot muzeyi",
        degree="Filologiya fanlari nomzodi",
        bio=(
            "O'zbek matbuoti tarixi, jadid davri nashriyotchiligi va bibliografik ko'rsatkichlar bo'yicha "
            "tadqiqotchi."
        ),
        avatar_idx=3,
    ),
    dict(
        tag="BT",
        name="Bobur Tursunov",
        role="Konservator",
        org="Termiz arxeologiya muzeyi",
        degree="",
        bio=(
            "Arxiv hujjatlarini uzoq muddatli saqlash, namlik ta'sirini bartaraf etish va "
            "raqamli nusxa olish jarayonlari bo'yicha amaliy mutaxassis."
        ),
        avatar_idx=4,
    ),
    dict(
        tag="MI",
        name="Madina Iskandarova",
        role="Raqamlashtirish loyihasi",
        org="O'zbekiston Milliy kutubxonasi",
        degree="",
        bio=(
            "Sun'iy intellekt, OCR va kompyuter ko'rish texnologiyalarini eski o'zbek va arab "
            "matnlariga moslashtirishni tadqiq qiladi."
        ),
        avatar_idx=0,
    ),
    dict(
        tag="OA",
        name="Oybek Anvarov",
        role="Nashriyot ishi mutaxassisi",
        org="O'zbekiston Yozuvchilar uyushmasi",
        degree="Tarix fanlari nomzodi",
        bio="Jadid matbuoti, 1900–1930 yillar O'rta Osiyo davriy nashriyotchiligi tarixini o'rganadi.",
        avatar_idx=2,
    ),
    dict(
        tag="KH",
        name="Kamoliddin Husaynov",
        role="Akademik",
        org="O'zbekiston FA Sharqshunoslik instituti",
        degree="Tarix fanlari doktori",
        bio=(
            "O'zbekiston Fanlar akademiyasi Sharqshunoslik instituti akademigi. "
            "32 ta ilmiy maqola va 5 ta monografiya muallifi."
        ),
        avatar_idx=3,
    ),
]

# ── Jurnal sonlari ────────────────────────────────────────────────────────────
# (volume, number, year, season, date_label, palette, is_current, is_upcoming)

ISSUES = [
    (42, 1, 2026, "Bahor", "Mart 2026",      0, True,  False),
    (42, 2, 2026, "Yoz",   "Iyun 2026",      1, False, True),
    (42, 3, 2026, "Kuz",   "Sentabr 2026",   2, False, True),
    (42, 4, 2026, "Qish",  "Dekabr 2026",    3, False, True),
    (41, 1, 2025, "Bahor", "Mart 2025",      1, False, False),
    (41, 2, 2025, "Yoz",   "Iyun 2025",      4, False, False),
    (41, 3, 2025, "Kuz",   "Sentabr 2025",   5, False, False),
    (41, 4, 2025, "Qish",  "Dekabr 2025",    0, False, False),
    (40, 1, 2024, "Bahor", "Mart 2024",      3, False, False),
    (40, 2, 2024, "Yoz",   "Iyun 2024",      2, False, False),
    (40, 3, 2024, "Kuz",   "Sentabr 2024",   1, False, False),
    (40, 4, 2024, "Qish",  "Dekabr 2024",    4, False, False),
]

# ── Maqolalar ─────────────────────────────────────────────────────────────────
# issue=None → journal siz (drag-drop demo uchun)
# issue=(vol, n) → o'sha journal soniga qo'shiladi

ARTICLES = [
    dict(
        pdf="1.pdf",
        title="Sharq qo'lyozmalari kataloglashning raqamli usullari",
        excerpt=(
            "O'zbekiston Milliy kutubxonasidagi XV–XIX asr qo'lyozmalarini RDF asosida "
            "tasniflash bo'yicha to'rt yillik tajriba xulosalari va katalog tuzilmasining yangi modeli."
        ),
        category="Arxiv ishi",
        authors=["DR", "AY"],
        year=2026, quarter=1, pages=24, min_read=14,
        cites=24,  views=8, img_variant=0, status="open",
        issue=(42, 1), published_at=date(2026, 3, 15),
    ),
    dict(
        pdf="2.pdf",
        title="«Mahbub ul-qulub»ning 1907-yilgi nashri — paleografik tahlil",
        excerpt=(
            "Toshkent toshbosma nashriyotida chiqqan kamyob nusxaning matn varianti, "
            "marginaliya yozuvlari va paleografik tahlili."
        ),
        category="Nodir nashrlar",
        authors=["NS"],
        year=2026, quarter=1, pages=32, min_read=22,
        cites=48,  views=6, img_variant=1, status="open",
        issue=(42, 1), published_at=date(2026, 3, 18),
    ),
    dict(
        pdf="3.pdf",
        title="BIBFRAME 2.0 standartining O'zbekiston kutubxonalarida joriy etilishi",
        excerpt=(
            "MARC21'dan BIBFRAME ga o'tishdagi asosiy yo'qotishlar va imkoniyatlar — "
            "uchta shahar kutubxonasidagi tajriba asosida."
        ),
        category="Katalogizatsiya",
        authors=["AY", "GK"],
        year=2026, quarter=1, pages=18, min_read=18,
        cites=12,  views=4,    img_variant=2, status="open",
        issue=(42, 1), published_at=date(2026, 3, 22),
    ),
    dict(
        pdf="4.pdf",
        title="O'zbek matbuoti tarixi: 1870–1925 yillar bibliografik ko'rsatkichi",
        excerpt=(
            "Ellik beshta davriy nashr va o'n besh ming maqolani qamragan ko'rsatkichning "
            "ish metodikasi va tuzish tamoyillari."
        ),
        category="Bibliografiya",
        authors=["GK"],
        year=2025, quarter=4, pages=48, min_read=26,
        cites=34,  views=3,    img_variant=3, status="lock",
        issue=(41, 4), published_at=date(2025, 12, 10),
    ),
    # ── Quyidagi ikki maqola journal da yo'q — Topshirishlar sahifasida
    #    drag-drop qilish uchun tayyor ──────────────────────────────────
    dict(
        pdf="5.pdf",
        title="OCR ning eski o'zbek imlosiga moslashtirilgan modeli",
        excerpt=(
            "Arab grafikasidagi bosma matnlar uchun fine-tuned transformer modelining "
            "dastlabki natijalari va xatolik tahlili."
        ),
        category="Raqamlashtirish",
        authors=["MI", "DR"],
        year=2026, quarter=2, pages=12, min_read=12,
        cites=5,   views=2,    img_variant=0, status="open",
        issue=None, published_at=None,
    ),
    dict(
        pdf="6.pdf",
        title="Termiz arxivlaridagi sovuq urush davri hujjatlarining konservatsiyasi",
        excerpt=(
            "Past namlik sharoitida saqlangan qog'oz hujjatlar va raqamli nusxa olishning "
            "optimal rejimlari — 2018–2023 yillar tajribasi."
        ),
        category="Konservatsiya",
        authors=["BT"],
        year=2026, quarter=2, pages=14, min_read=16,
        cites=8,   views=1,    img_variant=1, status="open",
        issue=None, published_at=None,
    ),
]

# ── Kutilayotgan topshirishlar (hali ko'rib chiqilmagan) ──────────────────────

PENDING_SUBMISSIONS = [
    dict(
        pdf="1.pdf",
        chat_id=100000001, tg_name="Sardor Umarov", tg_username="sardor_uz",
        title="Raqamli arxivlashtirish: yangi yondashuv va amaliy tajriba",
        authors="Sardor Umarov, Jasur Toshmatov",
        keywords="raqamlashtirish, arxiv, metadata, OAIS, saqlash",
        abstract=(
            "Maqolada arxiv hujjatlarini raqamli formatga o'tkazishning zamonaviy "
            "metodologiyasi va OAIS modeliga asoslangan uzoq muddatli saqlash tizimi "
            "ko'rib chiqiladi. 2,300 ta hujjat ustida o'tkazilgan tajriba natijalari keltirilgan."
        ),
        references=(
            "1. ISO 14721:2012 OAIS Reference Model.\n"
            "2. Karimov A. Raqamli kutubxona asoslari. Toshkent, 2024.\n"
            "3. Lavoie B. The OAIS Reference Model. 2014."
        ),
    ),
    dict(
        pdf="2.pdf",
        chat_id=100000002, tg_name="Nilufar Azimova", tg_username="nilufar_lib",
        title="Farg'ona viloyati kutubxonalari: 1920–1940 yillar tarixi",
        authors="Nilufar Azimova",
        keywords="Farg'ona, kutubxona tarixi, jadidlar, 1920-yillar",
        abstract=(
            "Farg'ona vodiysidagi kutubxonachilik ishining 1920–1940 yillardagi "
            "rivojlanishi arxiv manbalari asosida tahlil qilingan. Jadid maorifchilarining "
            "kutubxona tarmog'ini shakllantirishdagi roli yoritilgan."
        ),
        references=(
            "1. O'zMA, F.34, ro'yxat 1.\n"
            "2. Dolimov U. Turkiston jadidchiligi. Toshkent, 2021."
        ),
    ),
    dict(
        pdf="3.pdf",
        chat_id=100000003, tg_name="Rustam Qodirov", tg_username="rustam_q",
        title="MARC21 va BIBFRAME: qiyosiy tahlil",
        authors="Rustam Qodirov, Kamola Saidova",
        keywords="MARC21, BIBFRAME, metadata, kataloglash",
        abstract=(
            "Ikki yetakchi bibliografik metadata standarti — MARC21 va BIBFRAME 2.0 "
            "ning tuzilmaviy farqlari va o'zaro o'tkazish imkoniyatlari tahlil qilinadi."
        ),
        references="1. Library of Congress. BIBFRAME 2.0 Specification. 2023.",
    ),
]


# ── Management command ────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = "Demo ma'lumotlarni bazaga yuklaydi"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Bazani tozalab qayta yaratish (ehtiyot bo'ling!)",
        )

    def ok(self, msg: str):
        self.stdout.write(self.style.SUCCESS(f"  [OK] {msg}"))

    def info(self, msg: str):
        self.stdout.write(f"  [--] {msg}")

    # ------------------------------------------------------------------
    def handle(self, *args, **options):
        from apps.articles.models import Article, ArticleAuthor, ArticleSubmission, Category
        from apps.authors.models import Author
        from apps.journals.models import Journal, Issue

        # PDF lar mavjudligini tekshirish
        missing = [p for i in range(1, 7) if not (MAQOLA_DIR / (p := f"{i}.pdf")).exists()]
        if missing:
            raise CommandError(f"Quyidagi PDF lar topilmadi: {missing}\nPapka: {MAQOLA_DIR}")

        if options["clear"]:
            self.stdout.write(self.style.WARNING("Baza tozalanmoqda…"))
            ArticleSubmission.objects.all().delete()
            Article.objects.all().delete()
            Author.objects.all().delete()
            Issue.objects.all().delete()
            Journal.objects.all().delete()
            Category.objects.all().delete()
            self.stdout.write(self.style.WARNING("  Tozalandi.\n"))

        # ── 1. Yo'nalishlar ───────────────────────────────────────────

        self.stdout.write("\n[1/5] Yo'nalishlar…")
        cat_map: dict[str, Category] = {}
        for name in CATEGORIES:
            cat, created = Category.objects.get_or_create(name=name)
            cat_map[name] = cat
            if created:
                self.ok(name)
            else:
                self.info(f"{name} — allaqachon mavjud")

        # ── 2. Mualliflar ─────────────────────────────────────────────

        self.stdout.write("\n[2/5] Mualliflar…")
        author_map: dict[str, Author] = {}
        for d in AUTHORS:
            tag = d.pop("tag")
            author, created = Author.objects.get_or_create(
                name=d["name"],
                defaults={k: v for k, v in d.items()},
            )
            if not created:
                # Mavjud bo'lsa ma'lumotlarini yangilash
                for k, v in d.items():
                    setattr(author, k, v)
                author.save()
                self.info(f"{author.name} — yangilandi")
            else:
                self.ok(author.name)
            author_map[tag] = author

        # ── 3. Jurnal va sonlari ──────────────────────────────────────

        self.stdout.write("\n[3/5] Jurnal sonlari…")
        journal, created = Journal.objects.get_or_create(
            title="Kutubxona Arxivi",
            defaults={"issn": "2181-1394"},
        )
        self.ok(f"Jurnal: {journal.title}" + (" (yangi)" if created else " (mavjud)"))

        issue_map: dict[tuple, Issue] = {}
        for vol, n, year, season, date_label, palette, is_current, is_upcoming in ISSUES:
            issue, created = Issue.objects.get_or_create(
                journal=journal, volume=vol, number=n,
                defaults=dict(
                    year=year, season=season, date_label=date_label,
                    palette=palette, is_current=is_current, is_upcoming=is_upcoming,
                ),
            )
            issue_map[(vol, n)] = issue
            if created:
                self.ok(f"Vol.{vol} №{n} {year} ({season})")
            else:
                self.info(f"Vol.{vol} №{n} — allaqachon mavjud")

        # ── 4. Maqolalar ──────────────────────────────────────────────

        self.stdout.write("\n[4/5] Maqolalar (PDF parse qilinadi)…")
        article_map: dict[str, Article] = {}

        for art_data in ARTICLES:
            pdf_name   = art_data["pdf"]
            pdf_source = MAQOLA_DIR / pdf_name
            title      = art_data["title"]

            # Allaqachon bormi?
            existing = Article.objects.filter(title=title).first()
            if existing:
                self.info(f"{title[:55]}… — allaqachon mavjud")
                article_map[pdf_name] = existing
                continue

            # Maqola yaratish
            issue_key = art_data.get("issue")
            issue_obj = issue_map[issue_key] if issue_key else None

            article = Article(
                title      = title,
                excerpt    = art_data["excerpt"],
                category   = cat_map.get(art_data["category"]),
                status     = art_data["status"],
                year       = art_data["year"],
                quarter    = art_data["quarter"],
                pages      = art_data["pages"],
                min_read   = art_data["min_read"],
                cites      = art_data["cites"],
                views      = art_data["views"],
                img_variant= art_data["img_variant"],
                issue      = issue_obj,
                published_at = art_data["published_at"],
            )
            article.save()

            # PDF ni media ga ko'chirish
            with open(pdf_source, "rb") as fh:
                article.source_file.save(
                    f"article_{pdf_name}",
                    File(fh),
                    save=True,
                )

            # Mualliflar
            for order, tag in enumerate(art_data["authors"]):
                if tag in author_map:
                    from apps.articles.models import ArticleAuthor
                    ArticleAuthor.objects.get_or_create(
                        article=article, author=author_map[tag],
                        defaults={"order": order},
                    )

            # PDF → HTML parse
            try:
                html = article.parse_source_file()
                if html:
                    article.content = html
                    article.save(update_fields=["content", "updated_at"])
                    self.ok(f"{title[:55]}… [parse OK, {len(html)} belgi]")
                else:
                    self.ok(f"{title[:55]}… [parse bo'sh]")
            except Exception as exc:
                self.ok(f"{title[:55]}… [parse xato: {exc}]")

            article_map[pdf_name] = article

        # ── 5. Topshirishlar ──────────────────────────────────────────

        self.stdout.write("\n[5/5] Topshirishlar…")

        # 5a. Tasdiqlangan topshirishlar (article 5,6 uchun — journal da yo'q)
        for art_data in ARTICLES:
            if art_data.get("issue") is not None:
                continue  # Faqat issue-siz maqolalar
            article = article_map.get(art_data["pdf"])
            if not article:
                continue
            author_tag = art_data["authors"][0]
            author_obj = author_map.get(author_tag)
            chat_id    = 200000001 + ARTICLES.index(art_data)

            sub, created = ArticleSubmission.objects.get_or_create(
                article=article,
                defaults=dict(
                    chat_id     = chat_id,
                    tg_name     = author_obj.name if author_obj else "Demo",
                    tg_username = author_obj.name.lower().replace(" ", "_")[:20] if author_obj else "",
                    title       = article.title,
                    status      = "approved",
                    author      = author_obj,
                ),
            )
            if created:
                # Source file ni ham ko'chirish
                pdf_source = MAQOLA_DIR / art_data["pdf"]
                with open(pdf_source, "rb") as fh:
                    sub.source_file.save(
                        f"sub_approved_{art_data['pdf']}",
                        File(fh),
                        save=True,
                    )
                self.ok(f"[Tasdiqlangan] {article.title[:45]}…")
            else:
                self.info(f"[Tasdiqlangan] allaqachon mavjud")

        # 5b. Kutilayotgan topshirishlar
        for pend in PENDING_SUBMISSIONS:
            pdf_source = MAQOLA_DIR / pend["pdf"]
            if ArticleSubmission.objects.filter(chat_id=pend["chat_id"]).exists():
                self.info(f"[Kutilmoqda] chat_id={pend['chat_id']} — allaqachon mavjud")
                continue

            sub = ArticleSubmission(
                chat_id     = pend["chat_id"],
                tg_name     = pend["tg_name"],
                tg_username = pend["tg_username"],
                title       = pend["title"],
                keywords    = pend.get("keywords", ""),
                abstract    = pend.get("abstract", ""),
                references  = pend.get("references", ""),
                extracted_authors = pend.get("authors", ""),
                ai_filled   = True,   # demo: AI allaqachon to'ldirgan deb hisoblanadi
                status      = "pending",
                submitted_at = timezone.now(),
            )
            sub.save()
            with open(pdf_source, "rb") as fh:
                sub.source_file.save(
                    f"sub_pending_{pend['chat_id']}.pdf",
                    File(fh),
                    save=True,
                )
            self.ok(f"[Kutilmoqda] {pend['tg_name']} — {pend['title'][:40] or '(sarlavsiz)'}…")

        # ── Xulosa ────────────────────────────────────────────────────

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("-" * 56))
        self.stdout.write(self.style.SUCCESS("  Seed muvaffaqiyatli yakunlandi!"))
        self.stdout.write(self.style.SUCCESS("-" * 56))
        self.stdout.write(f"  Yo'nalishlar : {Category.objects.count()}")
        self.stdout.write(f"  Mualliflar   : {Author.objects.count()}")
        self.stdout.write(f"  Jurnal       : {Journal.objects.count()} jurnal, {Issue.objects.count()} son")
        self.stdout.write(f"  Maqolalar    : {Article.objects.count()} (publika: {Article.objects.filter(issue__isnull=False).count()})")
        self.stdout.write(f"  Topshirishlar: {ArticleSubmission.objects.count()} (kutilmoqda: {ArticleSubmission.objects.filter(status='pending').count()})")
        self.stdout.write("")
        self.stdout.write("  Sayt         : http://localhost:8000")
        self.stdout.write("  Swagger      : http://localhost:8000/api/docs/")
        self.stdout.write("  Django admin : http://localhost:8000/admin/")
        self.stdout.write("  Frontend     : http://localhost:5173")
        self.stdout.write("")
