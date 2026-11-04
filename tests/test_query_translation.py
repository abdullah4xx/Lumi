import unittest

from lumi.query import translate_query


class QueryTranslationTests(unittest.TestCase):
    def test_known_arabic_words_are_translated(self):
        self.assertEqual(translate_query("بحيرة شروق"), "lake sunrise")

    def test_unknown_arabic_words_are_not_dropped(self):
        self.assertEqual(translate_query("بحيرة خيالية"), "lake خيالية")

    def test_unrecognized_arabic_query_is_preserved(self):
        self.assertEqual(translate_query("كلمةغيرمعروفة"), "كلمةغيرمعروفة")
