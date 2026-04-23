from rest_framework import viewsets
from django.db.models import Q
from .models import Program
from .serializers import ProgramSerializer
from shared.permissions import ReadOnlyOrAdminWrite


class ProgramViewSet(viewsets.ModelViewSet):
    queryset = Program.objects.select_related('department')
    serializer_class = ProgramSerializer
    permission_classes = [ReadOnlyOrAdminWrite]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params

        department_id = params.get('department')
        if department_id:
            qs = qs.filter(department_id=department_id)

        program_type = params.get('type')
        if program_type:
            types = [t.strip().lower() for t in program_type.split(',') if t.strip()]
            q = Q()
            for t in types:
                q |= Q(type__iexact=t)
            qs = qs.filter(q)

        level_type = params.get('level_type') or params.get('school_level')
        if level_type:
            qs = qs.filter(department__school_level__level_type=level_type)

        high_school = params.get('high_school')
        if high_school in ['1', 'true', 'True', 'yes', 'YES']:
            qs = qs.filter(
                department__school_level__level_type__in=['junior_high', 'senior_high']
            )

        return qs
