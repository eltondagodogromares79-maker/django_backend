from rest_framework import viewsets
from .models import SchoolLevel, SchoolYear, Term
from .serializers import SchoolLevelSerializer, SchoolYearSerializer, TermSerializer
from shared.permissions import ReadOnlyOrAdminWrite


class SchoolLevelViewSet(viewsets.ModelViewSet):
    queryset = SchoolLevel.objects.all()
    serializer_class = SchoolLevelSerializer
    permission_classes = [ReadOnlyOrAdminWrite]


class TermViewSet(viewsets.ModelViewSet):
    queryset = Term.objects.all()
    serializer_class = TermSerializer
    permission_classes = [ReadOnlyOrAdminWrite]


class SchoolYearViewSet(viewsets.ModelViewSet):
    queryset = SchoolYear.objects.all()
    serializer_class = SchoolYearSerializer
    permission_classes = [ReadOnlyOrAdminWrite]
