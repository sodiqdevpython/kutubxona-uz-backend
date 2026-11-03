import re

from django.test import SimpleTestCase

from utils.search import term_regex


class TermRegexTests(SimpleTestCase):
    def assertFinds(self, query, text):
        self.assertRegex(text, re.compile(term_regex(query), re.I), f'{query!r} → {text!r}')

    def assertSkips(self, query, text):
        self.assertNotRegex(text, re.compile(term_regex(query), re.I), f'{query!r} → {text!r}')

    def test_apostrophe_kinds_and_missing_apostrophe(self):
        for query in ("O'zbekiston", 'O‘zbekiston', 'O’zbekiston', 'Oʻzbekiston', 'Ozbekiston'):
            for text in ("O'zbekiston", 'O‘zbekiston', 'Oʻzbekistonda', 'Ozbekiston'):
                self.assertFinds(query, text)

    def test_mixed_script_from_pdf(self):
        self.assertFinds("O'zbekiston", 'Yangi О‘zbekistonda')
        self.assertFinds('toraev', "Aziz TО'RAEV")

    def test_cyrillic_and_latin_both_ways(self):
        self.assertFinds('Ўзбекистон', 'O‘zbekiston')
        self.assertFinds("O'zbekiston", 'Ўзбекистон')
        self.assertFinds('маълумот', "ma'lumot")
        self.assertFinds('malumot', 'маълумот')
        self.assertFinds('Шаҳар', 'shahar')
        self.assertFinds('kitobxonlik', 'Китобхонлик')
        self.assertFinds('Европа', 'Yevropa')
        self.assertFinds('Yevropa', 'Европа')

    def test_different_words_do_not_match(self):
        self.assertSkips('kutubxona', 'O‘zbekiston')
        self.assertSkips('shahar', 'sahar')

    def test_regex_characters_are_literal(self):
        self.assertFinds('c++', 'C++ tili')
        self.assertSkips('a.b', 'axb')

    def test_only_apostrophe_is_literal(self):
        self.assertFinds("'", "ma'lumot")
        self.assertSkips("'", 'kitob')
