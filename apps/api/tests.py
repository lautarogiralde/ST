from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.api.views import ItinerarioViewSet, ParadaViewSet
from apps.cobranza.models import Cobranza
from apps.core.models import Transportista
from apps.itinerarios.models import EstadoItinerario, EstadoParada, Itinerario, Parada
from apps.remitos.models import Comercio, EstadoRemito, Marca, Remito

User = get_user_model()


class RegistrarCobranzaTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(username="12345678", password="secret123")
        self.transportista = Transportista.objects.create(usuario=self.user)
        self.itinerario = Itinerario.objects.create(
            fecha=date.today(),
            estado=EstadoItinerario.ASIGNADO,
            transportista=self.transportista,
        )
        self.comercio = Comercio.objects.create(
            razon_social="Comercio Test",
            cuit="30112233445",
            domicilio="Calle Falsa 123",
        )
        self.marca = Marca.objects.create(
            nombre="Marca Test",
            cuit="30998877665",
            activo=True,
        )
        self.parada = Parada.objects.create(
            itinerario=self.itinerario,
            comercio=self.comercio,
            orden=1,
            estado=EstadoParada.PENDIENTE,
        )
        self.remito = Remito.objects.create(
            numero="R-001",
            marca=self.marca,
            comercio=self.comercio,
            total=Decimal("100.00"),
            estado=EstadoRemito.ASIGNADO,
            parada=self.parada,
        )

    def test_cobranza_parcial_no_cierra_la_visita(self):
        payload = [{"medio": "efectivo", "monto": "70.00"}]
        request = self.factory.post(
            f"/api/paradas/{self.parada.id}/registrar-cobranza/",
            payload,
            format="json",
        )
        force_authenticate(request, user=self.user)

        response = ParadaViewSet.as_view({"post": "registrar_cobranza"})(
            request,
            pk=self.parada.pk,
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Cobranza.objects.filter(parada=self.parada).exists())

        self.parada.refresh_from_db()
        self.remito.refresh_from_db()
        self.assertEqual(self.parada.estado, EstadoParada.PENDIENTE)
        self.assertEqual(self.remito.estado, EstadoRemito.ASIGNADO)


class IniciarItinerarioTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(username="12345678", password="secret123")
        self.transportista = Transportista.objects.create(usuario=self.user)
        self.itinerario = Itinerario.objects.create(
            fecha=date.today(),
            estado=EstadoItinerario.ASIGNADO,
            transportista=self.transportista,
        )

    def test_iniciar_itinerario_asignado_pasa_a_en_curso(self):
        request = self.factory.post("/api/itinerarios/iniciar/")
        force_authenticate(request, user=self.user)

        response = ItinerarioViewSet.as_view({"post": "iniciar"})(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["estado"], EstadoItinerario.EN_CURSO)
        self.itinerario.refresh_from_db()
        self.assertEqual(self.itinerario.estado, EstadoItinerario.EN_CURSO)

    def test_iniciar_itinerario_ya_en_curso_retorna_200_y_mantiene_estado(self):
        self.itinerario.estado = EstadoItinerario.EN_CURSO
        self.itinerario.save()

        request = self.factory.post("/api/itinerarios/iniciar/")
        force_authenticate(request, user=self.user)

        response = ItinerarioViewSet.as_view({"post": "iniciar"})(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["mensaje"], "El itinerario ya se encuentra en curso.")
        self.assertEqual(response.data["estado"], EstadoItinerario.EN_CURSO)

    def test_iniciar_sin_itinerario_asignado_falla(self):
        self.itinerario.estado = EstadoItinerario.FINALIZADO
        self.itinerario.save()

        request = self.factory.post("/api/itinerarios/iniciar/")
        force_authenticate(request, user=self.user)

        response = ItinerarioViewSet.as_view({"post": "iniciar"})(request)

        self.assertEqual(response.status_code, 400)
        self.assertIn("No posees ningún itinerario asignado para iniciar.", str(response.data))

    def test_itinerario_en_curso_es_reconocido_por_get_itinerario_activo(self):
        self.itinerario.estado = EstadoItinerario.EN_CURSO
        self.itinerario.save()

        request = self.factory.get("/api/itinerarios/paradas/")
        force_authenticate(request, user=self.user)

        response = ItinerarioViewSet.as_view({"get": "paradas"})(request)
        self.assertEqual(response.status_code, 200)

    def test_itinerario_solo_asignado_no_permite_acceso_a_paradas(self):
        # El itinerario sigue en ASIGNADO
        request = self.factory.get("/api/itinerarios/paradas/")
        force_authenticate(request, user=self.user)

        response = ItinerarioViewSet.as_view({"get": "paradas"})(request)
        self.assertEqual(response.status_code, 400)
        self.assertIn("No posees ningún itinerario en curso en este momento.", str(response.data))

    def test_iniciar_itinerario_de_otra_fecha_falla(self):
        from datetime import timedelta
        self.itinerario.fecha = date.today() + timedelta(days=1)
        self.itinerario.save()

        request = self.factory.post("/api/itinerarios/iniciar/")
        force_authenticate(request, user=self.user)

        response = ItinerarioViewSet.as_view({"post": "iniciar"})(request)
        self.assertEqual(response.status_code, 400)
        self.assertIn("No posees ningún itinerario asignado para iniciar.", str(response.data))

    def test_itinerario_activo_de_otra_fecha_no_se_recupera(self):
        from datetime import timedelta
        self.itinerario.fecha = date.today() - timedelta(days=1)
        self.itinerario.estado = EstadoItinerario.EN_CURSO
        self.itinerario.save()

        request = self.factory.get("/api/itinerarios/paradas/")
        force_authenticate(request, user=self.user)

        response = ItinerarioViewSet.as_view({"get": "paradas"})(request)
        self.assertEqual(response.status_code, 400)
        self.assertIn("No posees ningún itinerario en curso en este momento.", str(response.data))
