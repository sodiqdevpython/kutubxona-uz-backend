"""
Yuklanadigan fayllar uchun validatorlar.

Qoida:
  • Rasm maydonlari  — istalgan keng tarqalgan rasm formati (SVG'dan tashqari).
  • Hujjat maydonlari — PDF va Word (.doc / .docx).
  • Chat ilovalari   — yuqoridagilarning hammasi + bir nechta idoraviy format.

SVG ataylab ro'yxatga kiritilmagan: u XML bo'lib, ichida JavaScript saqlay
oladi va brauzerda sayt bilan bir xil origin'da bajariladi. Rasm sifatida
PNG/WebP ishlatilsin.

Validatorlar migratsiyalarga yoziladi, shuning uchun modul darajasidagi
funksiyalar (lambda emas) bo'lishi shart.
"""
import os

from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible

# ── Ruxsat etilgan kengaytmalar ──────────────────────────────────────────────

IMAGE_EXTENSIONS = (
    '.jpg', '.jpeg', '.jpe', '.png', '.gif', '.webp',
    '.bmp', '.tif', '.tiff', '.heic', '.heif', '.avif', '.ico',
)

DOCUMENT_EXTENSIONS = (
    '.pdf',
    '.doc', '.docx', '.docm', '.dot', '.dotx', '.rtf', '.odt',
)

# Chatda admin yuborishi mumkin bo'lgan qo'shimcha formatlar
EXTRA_ATTACHMENT_EXTENSIONS = (
    '.xls', '.xlsx', '.csv',
    '.ppt', '.pptx',
    '.txt', '.zip', '.rar', '.7z',
)

ATTACHMENT_EXTENSIONS = (
    DOCUMENT_EXTENSIONS + IMAGE_EXTENSIONS + EXTRA_ATTACHMENT_EXTENSIONS
)

# ── Hajm chegaralari ─────────────────────────────────────────────────────────

MB = 1024 * 1024
MAX_IMAGE_SIZE      = 15 * MB
MAX_DOCUMENT_SIZE   = 50 * MB
MAX_ATTACHMENT_SIZE = 50 * MB


@deconstructible
class FileKindValidator:
    """Fayl kengaytmasi va hajmini tekshiradi."""

    def __init__(self, extensions, max_size, label):
        self.extensions = tuple(extensions)
        self.max_size   = max_size
        self.label      = label

    def __call__(self, value):
        name = getattr(value, 'name', '') or ''
        ext  = os.path.splitext(name)[1].lower()

        if ext not in self.extensions:
            raise ValidationError(
                '%(label)s uchun «%(ext)s» formati qo\'llab-quvvatlanmaydi. '
                'Ruxsat etilganlari: %(allowed)s',
                params={
                    'label':   self.label,
                    'ext':     ext or '(kengaytmasiz)',
                    'allowed': ', '.join(e.lstrip('.') for e in self.extensions),
                },
                code='invalid_extension',
            )

        size = getattr(value, 'size', None)
        if size is not None and size > self.max_size:
            raise ValidationError(
                '%(label)s hajmi %(limit)s MB dan oshmasligi kerak '
                '(yuborilgani: %(actual)s MB).',
                params={
                    'label':  self.label,
                    'limit':  self.max_size // MB,
                    'actual': round(size / MB, 1),
                },
                code='file_too_large',
            )

    def __eq__(self, other):
        return (
            isinstance(other, FileKindValidator)
            and self.extensions == other.extensions
            and self.max_size == other.max_size
            and self.label == other.label
        )


# ── Tayyor validatorlar ──────────────────────────────────────────────────────

validate_image = FileKindValidator(
    IMAGE_EXTENSIONS, MAX_IMAGE_SIZE, 'Rasm',
)
validate_document = FileKindValidator(
    DOCUMENT_EXTENSIONS, MAX_DOCUMENT_SIZE, 'Hujjat',
)
validate_attachment = FileKindValidator(
    ATTACHMENT_EXTENSIONS, MAX_ATTACHMENT_SIZE, 'Fayl',
)
