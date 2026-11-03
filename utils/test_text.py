from django.test import SimpleTestCase

from utils.text import detect_language, normalize_person_name, normalize_text, repair_title, sentence_case


class NormalizeTextTests(SimpleTestCase):
    def test_mixed_script_words(self):
        self.assertEqual(normalize_text('Yangi О‘zbekistonda'), 'Yangi O‘zbekistonda')
        self.assertEqual(normalize_text('Qаlblаrgа ko‘chаyotgаn'), 'Qalblarga ko‘chayotgan')
        self.assertEqual(normalize_text("о'rtasidagi"), 'o‘rtasidagi')

    def test_pure_cyrillic_untouched(self):
        text = '«История доктора»: медийный поворот'
        self.assertEqual(normalize_text(text), text)
        self.assertEqual(normalize_text('Ўзбекистон'), 'Ўзбекистон')

    def test_apostrophes(self):
        self.assertEqual(normalize_text("bog'liqlik"), 'bog‘liqlik')
        self.assertEqual(normalize_text('Sun’iy intellekt'), 'Sun’iy intellekt')
        self.assertEqual(normalize_text("ma`lumot"), 'ma’lumot')

    def test_ligature_and_spaces(self):
        self.assertEqual(normalize_text('bibliograﬁyasi  tasniﬁ'), 'bibliografiyasi tasnifi')

    def test_quotes_kept(self):
        self.assertEqual(normalize_text('“Mehr kutubxonasi” loyihasi'), '“Mehr kutubxonasi” loyihasi')


class RepairTitleTests(SimpleTestCase):
    def test_broken_title(self):
        self.assertEqual(
            repair_title('Yangi davr g arb tafakkurida mutolaa madaniyati sotsial ‘ modelining namoyon bо lish shakllarI'),
            'Yangi davr g‘arb tafakkurida mutolaa madaniyati sotsial modelining namoyon bo‘lish shakllari',
        )
        self.assertEqual(
            repair_title('“Alisher Navoiy ensiklopediyasi” – yangi O zbekiston ilm-fani yutug i'),
            '“Alisher Navoiy ensiklopediyasi” – yangi O‘zbekiston ilm-fani yutug‘i',
        )
        self.assertEqual(
            repair_title('О zbekiston Respublikasi arxiv ishi tashkiliy tuzilmasining ‘ rivojlanishi tahlili'),
            'O‘zbekiston Respublikasi arxiv ishi tashkiliy tuzilmasining rivojlanishi tahlili',
        )

    def test_good_title_unchanged(self):
        self.assertEqual(repair_title('Kutubxona dilbari'), 'Kutubxona dilbari')
        self.assertEqual(repair_title('XXI asr kutubxonasi'), 'XXI asr kutubxonasi')


class PersonNameTests(SimpleTestCase):
    def test_uppercase_words(self):
        self.assertEqual(normalize_person_name('KUSHBAKOV Kamoliddin Baxromovich'), 'Kushbakov Kamoliddin Baxromovich')
        self.assertEqual(normalize_person_name('Oygul DULANBAYEVA'), 'Oygul Dulanbayeva')
        self.assertEqual(normalize_person_name("Shoyim BО'TAYEV"), 'Shoyim Bo‘tayev')
        self.assertEqual(normalize_person_name('ЦАЙ Ирина Константиновна'), 'Цай Ирина Константиновна')

    def test_initials_kept(self):
        self.assertEqual(normalize_person_name('Gaziyev A.A.'), 'Gaziyev A.A.')


class SentenceCaseTests(SimpleTestCase):
    def test_section_names(self):
        self.assertEqual(sentence_case('MUTOLAA MADANIYATI'), 'Mutolaa madaniyati')
        self.assertEqual(sentence_case('JAMIYAT. MADANIYAT. KITOB'), 'Jamiyat. Madaniyat. Kitob')
        self.assertEqual(sentence_case('TADQIQOTLAR. ИССЛЕДОВАНИЯ'), 'Tadqiqotlar. Исследования')
        self.assertEqual(sentence_case('YIG’MA ELEKTRON KATALOG'), 'Yig‘ma elektron katalog')


class DetectLanguageTests(SimpleTestCase):
    def test_languages(self):
        self.assertEqual(detect_language('Yangi О‘zbekistonda axborot-kutubxona xizmatini tashkil qilish'), 'uz')
        self.assertEqual(detect_language('Respublika ilmiy qishloq xо‘jaligi kutubxonasida'), 'uz')
        self.assertEqual(detect_language('Трансформация высшего библиотечного образования'), 'ru')
        self.assertEqual(detect_language('Ўзбекистонда кутубхона иши'), 'uz-cyrl')
        self.assertEqual(detect_language('A study of digital libraries and reading'), 'en')
