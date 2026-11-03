from django.test import RequestFactory, SimpleTestCase

from utils.cache import NS_CATALOG, request_cache_key


class RequestCacheKeyTests(SimpleTestCase):
    def key(self, host, path='/api/issues/archive/', query=None, secure=True):
        factory = RequestFactory()
        request = factory.get(path, query or {}, HTTP_HOST=host, secure=secure)
        return request_cache_key(request, NS_CATALOG)

    def test_each_domain_has_own_key(self):
        self.assertNotEqual(self.key('journal.kutubxona.uz'), self.key('api.journal.kutubxona.uz'))

    def test_scheme_changes_key(self):
        self.assertNotEqual(self.key('journal.kutubxona.uz'), self.key('journal.kutubxona.uz', secure=False))

    def test_same_request_same_key(self):
        self.assertEqual(self.key('journal.kutubxona.uz'), self.key('journal.kutubxona.uz'))

    def test_query_changes_key(self):
        self.assertNotEqual(self.key('journal.kutubxona.uz', query={'page': 1}), self.key('journal.kutubxona.uz', query={'page': 2}))
