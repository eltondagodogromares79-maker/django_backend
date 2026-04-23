from rest_framework import viewsets, status, permissions
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Section, Enrollment, StudentSubject
from .serializers import SectionSerializer, EnrollmentSerializer, StudentSubjectSerializer, TranscriptEnrollmentSerializer, PublicSectionSerializer
from shared.permissions import ReadOnlyOrAdminWrite, IsStudentOrTeacherOrAdmin


class SectionViewSet(viewsets.ModelViewSet):
    queryset = Section.objects.select_related('year_level', 'adviser', 'year_level__program')
    serializer_class = SectionSerializer
    permission_classes = [ReadOnlyOrAdminWrite]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params

        program_id = params.get('program')
        if program_id:
            qs = qs.filter(year_level__program_id=program_id)

        year_level_id = params.get('year_level')
        if year_level_id:
            qs = qs.filter(year_level_id=year_level_id)

        adviser_id = params.get('adviser')
        if adviser_id:
            qs = qs.filter(adviser_id=adviser_id)

        unassigned = params.get('unassigned')
        if unassigned in ['1', 'true', 'True', 'yes', 'YES']:
            qs = qs.filter(adviser__isnull=True)

        high_school = params.get('high_school')
        if high_school in ['1', 'true', 'True', 'yes', 'YES']:
            qs = qs.filter(
                year_level__program__department__school_level__level_type__in=['junior_high', 'senior_high']
            )

        return qs

    @action(detail=True, methods=['get'], permission_classes=[IsStudentOrTeacherOrAdmin])
    def enrollments(self, request, pk=None):
        section = self.get_object()
        enrollments = Enrollment.objects.filter(section=section).select_related('student__user')
        serializer = EnrollmentSerializer(enrollments, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], permission_classes=[IsStudentOrTeacherOrAdmin])
    def available_subjects(self, request, pk=None):
        """Returns subjects available for selection in this section (college only)."""
        from subjects.models import SectionSubject
        section = self.get_object()
        if section.is_high_school:
            return Response({'detail': 'High school subjects are auto-assigned.'}, status=status.HTTP_400_BAD_REQUEST)
        term_id = request.query_params.get('term')
        qs = SectionSubject.objects.filter(section=section).select_related('subject', 'instructor__user', 'adviser__user')
        if term_id:
            qs = qs.filter(term_id=term_id)
        from subjects.serializers import SectionSubjectSerializer
        return Response(SectionSubjectSerializer(qs, many=True).data)


class EnrollmentViewSet(viewsets.ModelViewSet):
    queryset = Enrollment.objects.select_related('student__user', 'section', 'term')
    serializer_class = EnrollmentSerializer
    permission_classes = [ReadOnlyOrAdminWrite]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'student':
            return Enrollment.objects.filter(student__user=user).order_by('-enrolled_at')
        if user.role == 'adviser':
            return Enrollment.objects.filter(section__adviser__user=user)
        if user.role == 'instructor':
            return Enrollment.objects.filter(
                section__section_subjects__instructor__user=user
            ).distinct()
        return super().get_queryset()

    @action(detail=False, methods=['get'], permission_classes=[IsStudentOrTeacherOrAdmin], url_path='transcript')
    def transcript(self, request):
        user = request.user
        qs = Enrollment.objects.select_related(
            'section__year_level__program', 'term', 'school_year', 'year_level', 'student__user'
        ).prefetch_related('student_subjects__section_subject__subject')
        if user.role == 'student':
            qs = qs.filter(student__user=user)
        else:
            student_id = request.query_params.get('student')
            if student_id:
                qs = qs.filter(student_id=student_id)
        serializer = TranscriptEnrollmentSerializer(qs.order_by('-enrolled_at'), many=True)
        return Response(serializer.data)


class StudentSubjectViewSet(viewsets.ModelViewSet):
    queryset = StudentSubject.objects.select_related(
        'enrollment__student__user', 'section_subject__subject',
        'section_subject__instructor__user', 'section_subject__adviser__user'
    )
    serializer_class = StudentSubjectSerializer
    permission_classes = [ReadOnlyOrAdminWrite]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'student':
            current = Enrollment.objects.filter(student__user=user, is_current=True).first()
            if current and current.school_year_id:
                return StudentSubject.objects.filter(enrollment__student__user=user, school_year_id=current.school_year_id)
            return StudentSubject.objects.filter(enrollment__student__user=user)
        return super().get_queryset()


class PublicSectionListView(viewsets.ReadOnlyModelViewSet):
    queryset = Section.objects.select_related('year_level', 'adviser__user', 'school_year')
    serializer_class = PublicSectionSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        search = (self.request.query_params.get('search') or '').strip()
        if search:
            qs = qs.filter(
                Q(name__icontains=search) |
                Q(adviser__user__first_name__icontains=search) |
                Q(adviser__user__last_name__icontains=search) |
                Q(school_year__name__icontains=search)
            )
        return qs


class PublicSectionPagination(PageNumberPagination):
    page_size = 12
    page_size_query_param = 'page_size'
    max_page_size = 50


class PublicSectionListViewPaginated(PublicSectionListView):
    pagination_class = PublicSectionPagination
