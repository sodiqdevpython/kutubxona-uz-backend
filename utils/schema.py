"""
drf-spectacular uchun sxema sozlamalari.

Loyihadagi bot va admin-panel endpointlarining ko'pchiligi oddiy `APIView`
bo'lib, ular ad-hoc JSON qaytaradi (`{'ok': True}` kabi) va `serializer_class`
ga ega emas. Standart `AutoSchema` bunday view'ni uchratganda har bir
`manage.py` chaqiruvida "unable to guess serializer" degan ERROR yozadi —
loglar shu sababli to'lib ketardi.

Bu yerdagi `ProjectAutoSchema` xuddi shunday natija beradi (bunday view'lar
sxemada tanasiz ko'rinadi), lekin ortiqcha xato yozmaydi. Aniq shakl kerak
bo'lgan joyda `@extend_schema(request=…, responses=…)` ishlating —
masalan `apps/partner/views.py` da shunday qilingan.
"""
from drf_spectacular.openapi import AutoSchema
from rest_framework.generics import GenericAPIView
from rest_framework.views import APIView


class ProjectAutoSchema(AutoSchema):

    def _get_serializer(self):
        view = self.view

        # GenericAPIView / ViewSet — standart mantiq to'liq ishlaydi
        if isinstance(view, GenericAPIView):
            return super()._get_serializer()

        if isinstance(view, APIView):
            has_hint = (
                callable(getattr(view, 'get_serializer', None))
                or callable(getattr(view, 'get_serializer_class', None))
                or hasattr(view, 'serializer_class')
            )
            if not has_hint:
                # Ad-hoc JSON qaytaruvchi APIView — tanasiz hujjatlanadi.
                # (Standart AutoSchema ham aynan shunday qiladi, faqat
                #  qo'shimcha ravishda ERROR yozadi.)
                return None

        return super()._get_serializer()
