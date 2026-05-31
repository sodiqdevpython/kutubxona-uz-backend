from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """page_size'ni mijoz o'zgartira olishi mumkin (?page_size=N), max 100."""
    page_size             = 20
    page_size_query_param = 'page_size'
    max_page_size         = 100
