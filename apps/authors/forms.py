"""Profillarni birlashtirish formalari (Django admin uchun)."""
from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import AutocompleteSelect

from .merge import MERGE_FIELDS
from .models import Author


def _author_field(label, help_text):
    # AutocompleteSelect haqiqiy FK maydonini talab qiladi — mavjud
    # `ArticleAuthor.author` dan foydalanamiz (u ham Author'ga ishora qiladi).
    from apps.articles.models import ArticleAuthor

    return forms.ModelChoiceField(
        queryset=Author.objects.all(),
        label=label,
        help_text=help_text,
        widget=AutocompleteSelect(
            ArticleAuthor._meta.get_field('author'),
            admin.site,
            attrs={'style': 'width: 420px'},
        ),
    )


class MergePickForm(forms.Form):
    """1-qadam: qaysi ikki profil birlashtiriladi."""

    target = None   # __init__ da o'rnatiladi
    source = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['target'] = _author_field(
            'Saqlanadigan profil',
            "Birlashtirilgandan keyin shu profil qoladi.",
        )
        self.fields['source'] = _author_field(
            "Qo'shiladigan profil",
            "Bu profil o'chiriladi, hamma narsasi yuqoridagiga ko'chadi.",
        )

    def clean(self):
        data = super().clean()
        target, source = data.get('target'), data.get('source')
        if target and source and target.pk == source.pk:
            raise forms.ValidationError(
                "Ikkala maydonda bir xil profil tanlangan — turlichasini tanlang."
            )
        return data


class MergeFieldsForm(forms.Form):
    """
    2-qadam: har bir maydon qaysi profildan olinadi.

    Har bir maydon uchun ikkita radio: saqlanadigan profildan (`target`)
    yoki qo'shiladigandan (`source`).
    """

    def __init__(self, *args, target: Author = None, source: Author = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.target = target
        self.source = source

        for field, label in MERGE_FIELDS:
            t_val = getattr(target, field, None) if target else None
            s_val = getattr(source, field, None) if source else None

            # Standart tanlov: qiymati bor tomon. Ikkalasida ham bo'lsa — target.
            if _is_empty(t_val) and not _is_empty(s_val):
                initial = 'source'
            else:
                initial = 'target'

            self.fields[f'f_{field}'] = forms.ChoiceField(
                choices=[('target', 'Saqlanadigan'), ('source', "Qo'shiladigan")],
                widget=forms.RadioSelect,
                initial=initial,
                required=True,
                label=label,
            )

    def choices(self) -> dict:
        """{'name': 'target'|'source', …}"""
        return {
            field: self.cleaned_data[f'f_{field}']
            for field, _label in MERGE_FIELDS
            if f'f_{field}' in self.cleaned_data
        }

    def rows(self):
        """Shablon uchun: (maydon, label, target qiymati, source qiymati, bound field)."""
        for field, label in MERGE_FIELDS:
            yield {
                'name':    field,
                'label':   label,
                'target':  getattr(self.target, field, None) if self.target else None,
                'source':  getattr(self.source, field, None) if self.source else None,
                'field':   self[f'f_{field}'],
                'is_image': field == 'avatar',
            }


def _is_empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    # FileField/ImageField
    if hasattr(value, 'name'):
        return not value.name
    return False
