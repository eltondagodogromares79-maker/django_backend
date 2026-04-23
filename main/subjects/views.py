from rest_framework import viewsets
from django.db.models import Q
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Subject, SectionSubject, Grade
from .serializers import SubjectSerializer, SectionSubjectSerializer, GradeSerializer
from learning_materials.models import LearningMaterial
from learning_materials.serializers import LearningMaterialSerializer
from assignments.models import Assignment
from assignments.serializers import AssignmentSerializer
from quizzes.models import Quiz
from quizzes.serializers import QuizSerializer
from shared.permissions import IsTeacherOrAdmin, IsStudentOrTeacherOrAdmin
from school_levels.models import SchoolYear
from sections.models import Enrollment


class SubjectViewSet(viewsets.ModelViewSet):
    queryset = Subject.objects.select_related('program', 'year_level')
    serializer_class = SubjectSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            permission_classes = [IsTeacherOrAdmin]
        else:
            permission_classes = [IsStudentOrTeacherOrAdmin]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'student':
            enrollments = Enrollment.objects.filter(student__user=user, is_current=True)
            if not enrollments.exists():
                enrollments = Enrollment.objects.filter(student__user=user)
            return Subject.objects.filter(
                section_subjects__section__in=enrollments.values('section')
            ).distinct()
        if user.role in ['instructor', 'adviser']:
            active = SchoolYear.objects.filter(is_active=True).first()
            qs = Subject.objects.filter(
                Q(section_subjects__instructor__user=user) |
                Q(section_subjects__adviser__user=user)
            )
            if active:
                qs = qs.filter(section_subjects__school_year=active)
            return qs.distinct()
        return super().get_queryset()

    @action(detail=True, methods=['get'], permission_classes=[IsStudentOrTeacherOrAdmin])
    def offerings(self, request, pk=None):
        subject = self.get_object()
        offerings = SectionSubject.objects.filter(subject=subject)
        serializer = SectionSubjectSerializer(offerings, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], permission_classes=[IsStudentOrTeacherOrAdmin])
    def content(self, request, pk=None):
        subject = self.get_object()
        section_subjects = SectionSubject.objects.filter(subject=subject)
        user = request.user
        if user.role == 'student':
            current = Enrollment.objects.filter(student__user=user, is_current=True).first()
            if current and current.school_year_id:
                section_subjects = section_subjects.filter(school_year_id=current.school_year_id)
        elif user.role in ['instructor', 'adviser']:
            active = SchoolYear.objects.filter(is_active=True).first()
            if active:
                section_subjects = section_subjects.filter(school_year=active)
        lessons = LearningMaterial.objects.filter(section_subject__in=section_subjects)
        assignments = Assignment.objects.filter(section_subject__in=section_subjects)
        quizzes = Quiz.objects.filter(section_subject__in=section_subjects)
        return Response({
            'subject': SubjectSerializer(subject).data,
            'lessons': LearningMaterialSerializer(lessons, many=True).data,
            'assignments': AssignmentSerializer(assignments, many=True).data,
            'quizzes': QuizSerializer(quizzes, many=True).data,
        })


class SectionSubjectViewSet(viewsets.ModelViewSet):
    queryset = SectionSubject.objects.select_related('section', 'subject', 'term', 'instructor')
    serializer_class = SectionSubjectSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            permission_classes = [IsTeacherOrAdmin]
        else:
            permission_classes = [IsStudentOrTeacherOrAdmin]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'student':
            current = Enrollment.objects.filter(student__user=user, is_current=True).first()
            if current and current.school_year_id:
                return SectionSubject.objects.filter(
                    school_year_id=current.school_year_id,
                    section_id=current.section_id,
                ).distinct()
            return SectionSubject.objects.filter(section__enrollments__student__user=user).distinct()
        if user.role in ['instructor', 'adviser']:
            qs = SectionSubject.objects.filter(instructor__user=user) | SectionSubject.objects.filter(adviser__user=user)
            active = SchoolYear.objects.filter(is_active=True).first()
            if active:
                qs = qs.filter(school_year=active)
            return qs
        return super().get_queryset()


class GradeViewSet(viewsets.ModelViewSet):
    queryset = Grade.objects.select_related('student', 'section_subject')
    serializer_class = GradeSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            permission_classes = [IsTeacherOrAdmin]
        else:
            permission_classes = [IsStudentOrTeacherOrAdmin]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'student':
            current = Enrollment.objects.filter(student__user=user, is_current=True).first()
            if current and current.school_year_id:
                return Grade.objects.filter(student__user=user, school_year_id=current.school_year_id)
            return Grade.objects.filter(student__user=user)
        if user.role in ['instructor', 'adviser']:
            qs = Grade.objects.filter(section_subject__instructor__user=user) | Grade.objects.filter(section_subject__adviser__user=user)
            active = SchoolYear.objects.filter(is_active=True).first()
            if active:
                qs = qs.filter(school_year=active)
            return qs
        return super().get_queryset()
