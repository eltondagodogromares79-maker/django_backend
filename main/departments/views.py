from rest_framework import viewsets
from .models import Department
from .serializers import DepartmentSerializer
from shared.permissions import ReadOnlyOrAdminWrite


class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.select_related('school_level', 'principal_or_dean')
    serializer_class = DepartmentSerializer
    permission_classes = [ReadOnlyOrAdminWrite]
