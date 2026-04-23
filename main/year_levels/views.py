from rest_framework import viewsets
from .models import YearLevel
from .serializers import YearLevelSerializer
from shared.permissions import ReadOnlyOrAdminWrite


class YearLevelViewSet(viewsets.ModelViewSet):
    queryset = YearLevel.objects.select_related('program')
    serializer_class = YearLevelSerializer
    permission_classes = [ReadOnlyOrAdminWrite]

    def get_queryset(self):
        qs = super().get_queryset()
        program_id = self.request.query_params.get('program_id')
        if program_id:
            qs = qs.filter(program_id=program_id)
        return qs
