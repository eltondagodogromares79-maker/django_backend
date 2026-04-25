from django.db.models import Avg, Q
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from assignments.models import Assignment, AssignmentSubmission
from learning_materials.models import LearningMaterial
from quizzes.models import Quiz, QuizAttempt, QuizProctorEvent
from sections.models import StudentSubject, Enrollment
from subjects.models import SectionSubject, Subject
from users.models import Student, Instructor, Adviser, CustomUser
from departments.models import Department
from sections.models import Section
from attendance.models import AttendanceRecord


def _current_enrollment(student: Student):
    current = Enrollment.objects.filter(student=student, is_current=True).first()
    if current:
        return current
    return Enrollment.objects.filter(student=student).order_by('-enrolled_at').first()


class DashboardStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        role = user.role
        now = timezone.now()

        if role == 'student':
            student = Student.objects.filter(user=user).first()
            if not student:
                return Response([])
            enrollment = _current_enrollment(student)
            student_subjects = StudentSubject.objects.filter(enrollment=enrollment) if enrollment else StudentSubject.objects.filter(enrollment__student=student)
            section_subject_ids = list(student_subjects.values_list('section_subject_id', flat=True))

            assignments_qs = Assignment.objects.filter(section_subject_id__in=section_subject_ids)
            lessons_count = LearningMaterial.objects.filter(section_subject_id__in=section_subject_ids).count()
            submitted_ids = AssignmentSubmission.objects.filter(
                student=student,
                assignment_id__in=assignments_qs.values_list('id', flat=True),
            ).values_list('assignment_id', flat=True)
            assignments_due = assignments_qs.filter(due_date__gte=now).exclude(id__in=submitted_ids).count()
            quiz_attempts = QuizAttempt.objects.filter(student=student).count()
            active_subjects = student_subjects.values('section_subject_id').distinct().count()

            stats = [
                {'label': 'Active subjects', 'value': str(active_subjects), 'trend': 'Current term'},
                {'label': 'Total learning materials', 'value': str(lessons_count), 'trend': 'Available materials'},
                {'label': 'Assignments due', 'value': str(assignments_due), 'trend': 'Upcoming tasks'},
                {'label': 'Quiz attempts', 'value': str(quiz_attempts), 'trend': 'All attempts'},
                {'label': 'Attendance', 'value': '—', 'trend': 'Not tracked'},
            ]
            return Response(stats)

        if role in ['instructor', 'adviser', 'teacher']:
            section_subjects = SectionSubject.objects.filter(
                Q(instructor__user=user) | Q(adviser__user=user)
            )
            class_count = section_subjects.count()
            learners_total = StudentSubject.objects.filter(section_subject__in=section_subjects).values('enrollment__student_id').distinct().count()
            lessons_count = LearningMaterial.objects.filter(section_subject__in=section_subjects).count()
            pending_reviews = AssignmentSubmission.objects.filter(
                assignment__section_subject__in=section_subjects,
                score__isnull=True,
            ).count()
            avg_score = AssignmentSubmission.objects.filter(
                assignment__section_subject__in=section_subjects,
                score__isnull=False,
            ).aggregate(avg=Avg('score'))['avg']
            avg_display = f"{avg_score:.1f}" if avg_score is not None else '—'

            stats = [
                {'label': 'Active classes', 'value': str(class_count), 'trend': f'{learners_total} learners total'},
                {'label': 'Learning materials published', 'value': str(lessons_count), 'trend': 'Published materials'},
                {'label': 'Pending reviews', 'value': str(pending_reviews), 'trend': 'Ungraded submissions'},
                {'label': 'Average grade', 'value': avg_display, 'trend': 'Average score'},
            ]
            return Response(stats)

        # Admin / principal / dean stats
        departments_count = Department.objects.count()
        faculty_count = Instructor.objects.count() + Adviser.objects.count()
        students_count = Student.objects.count()
        subjects_count = Subject.objects.count()
        sections_count = Section.objects.count()
        active_staff = CustomUser.objects.filter(is_active=True).exclude(role='student').count()

        if role == 'admin':
            stats = [
                {'label': 'Total students', 'value': str(students_count), 'trend': 'All enrolled'},
                {'label': 'Active staff', 'value': str(active_staff), 'trend': 'Active accounts'},
                {'label': 'Courses tracked', 'value': str(subjects_count), 'trend': 'Subjects offered'},
                {'label': 'Sections', 'value': str(sections_count), 'trend': 'Active sections'},
            ]
            return Response(stats)

        if role == 'principal':
            stats = [
                {'label': 'Departments', 'value': str(departments_count), 'trend': 'School-wide'},
                {'label': 'Faculty members', 'value': str(faculty_count), 'trend': 'Active faculty'},
                {'label': 'Students', 'value': str(students_count), 'trend': 'All enrolled'},
                {'label': 'Sections', 'value': str(sections_count), 'trend': 'Active sections'},
            ]
            return Response(stats)

        if role == 'dean':
            stats = [
                {'label': 'College departments', 'value': str(departments_count), 'trend': 'Department count'},
                {'label': 'Faculty members', 'value': str(faculty_count), 'trend': 'Active faculty'},
                {'label': 'Students', 'value': str(students_count), 'trend': 'All enrolled'},
                {'label': 'Courses tracked', 'value': str(subjects_count), 'trend': 'Subjects offered'},
            ]
            return Response(stats)

        return Response([])


class ProgressView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if user.role != 'student':
            return Response({
                'completionRate': 0,
                'attendanceRate': 0,
                'onTimeSubmissions': 0,
                'streakWeeks': 0,
                'goals': [],
            })
        student = Student.objects.filter(user=user).first()
        if not student:
            return Response({
                'completionRate': 0,
                'attendanceRate': 0,
                'onTimeSubmissions': 0,
                'streakWeeks': 0,
                'goals': [],
            })
        enrollment = _current_enrollment(student)
        student_subjects = StudentSubject.objects.filter(enrollment=enrollment) if enrollment else StudentSubject.objects.filter(enrollment__student=student)
        section_subject_ids = list(student_subjects.values_list('section_subject_id', flat=True))

        assignments_qs = Assignment.objects.filter(section_subject_id__in=section_subject_ids)
        submissions_qs = AssignmentSubmission.objects.filter(student=student, assignment__in=assignments_qs).select_related('assignment')
        assignments_count = assignments_qs.count()
        submissions_count = submissions_qs.count()
        completion_rate = round((submissions_count / assignments_count) * 100) if assignments_count else 0

        on_time_count = 0
        for submission in submissions_qs:
            if submission.assignment and submission.assignment.due_date and submission.submitted_at <= submission.assignment.due_date:
                on_time_count += 1
        on_time_rate = round((on_time_count / submissions_count) * 100) if submissions_count else 0

        lessons_count = LearningMaterial.objects.filter(section_subject_id__in=section_subject_ids).count()
        quiz_count = Quiz.objects.filter(section_subject_id__in=section_subject_ids).count()
        quiz_attempts = QuizAttempt.objects.filter(student=student).count()

        return Response({
            'completionRate': completion_rate,
            'attendanceRate': 0,
            'onTimeSubmissions': on_time_rate,
            'streakWeeks': 0,
            'goals': [
                {'label': 'Learning materials available', 'value': lessons_count, 'target': lessons_count},
                {'label': 'Assignments submitted', 'value': submissions_count, 'target': assignments_count},
                {'label': 'Quiz attempts', 'value': quiz_attempts, 'target': quiz_count},
            ],
        })


class StudentPerformanceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        role = user.role
        now = timezone.now()

        if role not in ['instructor', 'adviser', 'teacher']:
            return Response({'mode': role, 'sections': []})

        mode = 'adviser' if role == 'adviser' else 'teacher'

        if mode == 'adviser':
            sections = Section.objects.filter(adviser__user=user)
            enrollments = Enrollment.objects.filter(section__in=sections, is_current=True, status='enrolled').select_related('student__user', 'section')
            student_subjects = StudentSubject.objects.filter(enrollment__in=enrollments).select_related(
                'enrollment__student__user',
                'section_subject__subject',
                'section_subject__section',
                'section_subject__instructor__user',
                'section_subject__adviser__user',
            )
            section_subjects = SectionSubject.objects.filter(section__in=sections).select_related('subject', 'section', 'instructor__user', 'adviser__user')
        else:
            section_subjects = SectionSubject.objects.filter(
                Q(instructor__user=user) | Q(adviser__user=user)
            ).select_related('subject', 'section', 'instructor__user', 'adviser__user')
            sections = Section.objects.filter(id__in=section_subjects.values_list('section_id', flat=True))
            enrollments = Enrollment.objects.filter(section__in=sections, is_current=True, status='enrolled').select_related('student__user', 'section')
            student_subjects = StudentSubject.objects.filter(
                section_subject__in=section_subjects,
                enrollment__in=enrollments,
            ).select_related(
                'enrollment__student__user',
                'section_subject__subject',
                'section_subject__section',
                'section_subject__instructor__user',
                'section_subject__adviser__user',
            )

        students = Student.objects.filter(id__in=enrollments.values_list('student_id', flat=True)).select_related('user')
        assignments = Assignment.objects.filter(section_subject__in=section_subjects).select_related('section_subject')
        quizzes = Quiz.objects.filter(section_subject__in=section_subjects).select_related('section_subject')

        assignments_by_ss = {}
        for assignment in assignments:
            assignments_by_ss.setdefault(str(assignment.section_subject_id), []).append(assignment)

        quizzes_by_ss = {}
        for quiz in quizzes:
            quizzes_by_ss.setdefault(str(quiz.section_subject_id), []).append(quiz)

        submissions = AssignmentSubmission.objects.filter(
            assignment__in=assignments,
            student__in=students,
        ).select_related('assignment', 'student')

        submissions_by_student_ss = {}
        submission_scores_by_student_ss = {}
        for submission in submissions:
            student_id = str(submission.student_id)
            assignment_id = str(submission.assignment_id)
            ss_id = str(submission.assignment.section_subject_id)
            # Bug 3 fix: key by (student_id, ss_id) so submissions are scoped per subject
            submissions_by_student_ss.setdefault((student_id, ss_id), set()).add(assignment_id)
            if submission.score is not None:
                submission_scores_by_student_ss.setdefault((student_id, ss_id), []).append(float(submission.score))

        attempts = QuizAttempt.objects.filter(
            quiz__in=quizzes,
            student__in=students,
            submitted_at__isnull=False,
        ).select_related('quiz', 'student')

        latest_attempt_by_student_quiz = {}
        for attempt in attempts:
            key = (str(attempt.student_id), str(attempt.quiz_id))
            existing = latest_attempt_by_student_quiz.get(key)
            if not existing or (attempt.submitted_at and existing.submitted_at and attempt.submitted_at > existing.submitted_at):
                latest_attempt_by_student_quiz[key] = attempt

        quiz_scores_by_student_ss = {}
        attempts_by_student_ss = {}
        for attempt in latest_attempt_by_student_quiz.values():
            student_id = str(attempt.student_id)
            ss_id = str(attempt.quiz.section_subject_id)
            attempts_by_student_ss.setdefault((student_id, ss_id), set()).add(str(attempt.quiz_id))
            quiz_scores_by_student_ss.setdefault((student_id, ss_id), []).append(float(attempt.score or 0.0))

        violation_events = QuizProctorEvent.objects.filter(
            event_type='violation',
            session__student__in=students,
            session__quiz__in=quizzes,
        ).select_related('session__quiz')

        violations_by_student_ss = {}
        for event in violation_events:
            student_id = str(event.session.student_id)
            ss_id = str(event.session.quiz.section_subject_id)
            violations_by_student_ss[(student_id, ss_id)] = violations_by_student_ss.get((student_id, ss_id), 0) + 1

        attendance_records = AttendanceRecord.objects.filter(
            student__in=students,
            session__section__in=sections,
        ).select_related('session', 'student')

        attendance_by_student_section = {}
        for record in attendance_records:
            student_id = str(record.student_id)
            section_id = str(record.session.section_id)
            key = (student_id, section_id)
            entry = attendance_by_student_section.setdefault(key, {'present': 0, 'absent': 0, 'late': 0, 'excused': 0, 'total': 0})
            entry[record.status] += 1
            entry['total'] += 1

        sections_payload = []

        if mode == 'teacher':
            for ss in section_subjects:
                ss_id = str(ss.id)
                ss_students = student_subjects.filter(section_subject_id=ss.id)
                students_payload = []
                for ss_student in ss_students:
                    student = ss_student.enrollment.student
                    student_id = str(student.id)
                    assignments_list = assignments_by_ss.get(ss_id, [])
                    quizzes_list = quizzes_by_ss.get(ss_id, [])
                    # Bug 3 fix: use scoped submitted ids per (student, section_subject)
                    submitted_ids = submissions_by_student_ss.get((student_id, ss_id), set())
                    assignment_total = len(assignments_list)
                    # Bug 1 & 2 fix: count actual submissions, and treat no-due-date assignments
                    # as missing too (student hasn't submitted = missing regardless of due date)
                    assignment_submitted = len([a for a in assignments_list if str(a.id) in submitted_ids])
                    assignment_missing = assignment_total - assignment_submitted
                    assignment_scores = submission_scores_by_student_ss.get((student_id, ss_id), [])
                    assignment_avg = round(sum(assignment_scores) / len(assignment_scores), 1) if assignment_scores else None

                    attempted_quiz_ids = attempts_by_student_ss.get((student_id, ss_id), set())
                    quiz_total = len(quizzes_list)
                    # Bug 2 fix: count all unattempted quizzes as missing, not just past-due ones
                    quiz_missing = quiz_total - len(attempted_quiz_ids)
                    quiz_scores = quiz_scores_by_student_ss.get((student_id, ss_id), [])
                    quiz_avg = round(sum(quiz_scores) / len(quiz_scores), 1) if quiz_scores else None

                    attendance = attendance_by_student_section.get((student_id, str(ss.section_id)), {'present': 0, 'absent': 0, 'late': 0, 'excused': 0, 'total': 0})
                    violations = violations_by_student_ss.get((student_id, ss_id), 0)

                    students_payload.append({
                        'student_id': student_id,
                        'student_name': student.user.get_full_name(),
                        'student_number': student.student_number,
                        'gender': student.user.gender if hasattr(student.user, 'gender') else None,
                        'assignments': {
                            'missing': assignment_missing,
                            'submitted': assignment_submitted,
                            'total': assignment_total,
                            'average_score': assignment_avg,
                        },
                        'quizzes': {
                            'missing': quiz_missing,
                            'attempted': len(attempted_quiz_ids),
                            'total': quiz_total,
                            'average_score': quiz_avg,
                        },
                        'attendance': attendance,
                        'violations': violations,
                    })

                sections_payload.append({
                    'section_id': str(ss.section_id),
                    'section_name': ss.section.name,
                    'section_subject_id': ss_id,
                    'subject_name': ss.subject.name,
                    'teacher_name': ss.instructor.user.get_full_name() if ss.instructor_id else (ss.adviser.user.get_full_name() if ss.adviser_id else None),
                    'students': students_payload,
                })
        else:
            for section in sections:
                section_id = str(section.id)
                enrollments_for_section = [en for en in enrollments if en.section_id == section.id]
                students_payload = []
                for enrollment in enrollments_for_section:
                    student = enrollment.student
                    student_id = str(student.id)
                    attendance = attendance_by_student_section.get((student_id, section_id), {'present': 0, 'absent': 0, 'late': 0, 'excused': 0, 'total': 0})
                    subject_rows = []
                    for ss in section_subjects.filter(section_id=section.id):
                        ss_id = str(ss.id)
                        assignments_list = assignments_by_ss.get(ss_id, [])
                        quizzes_list = quizzes_by_ss.get(ss_id, [])
                        submitted_ids = submissions_by_student_ss.get((student_id, ss_id), set())
                        assignment_submitted = len([a for a in assignments_list if str(a.id) in submitted_ids])
                        assignment_missing = len(assignments_list) - assignment_submitted
                        assignment_scores = submission_scores_by_student_ss.get((student_id, ss_id), [])
                        assignment_avg = round(sum(assignment_scores) / len(assignment_scores), 1) if assignment_scores else None
                        attempted_quiz_ids = attempts_by_student_ss.get((student_id, ss_id), set())
                        quiz_missing = len(quizzes_list) - len(attempted_quiz_ids)
                        quiz_scores = quiz_scores_by_student_ss.get((student_id, ss_id), [])
                        quiz_avg = round(sum(quiz_scores) / len(quiz_scores), 1) if quiz_scores else None
                        violations = violations_by_student_ss.get((student_id, ss_id), 0)
                        subject_rows.append({
                            'section_subject_id': ss_id,
                            'subject_name': ss.subject.name,
                            'teacher_name': ss.instructor.user.get_full_name() if ss.instructor_id else (ss.adviser.user.get_full_name() if ss.adviser_id else None),
                            'assignment_average': assignment_avg,
                            'quiz_average': quiz_avg,
                            'missing_assignments': assignment_missing,
                            'missing_quizzes': quiz_missing,
                            'violations': violations,
                        })

                    students_payload.append({
                        'student_id': student_id,
                        'student_name': student.user.get_full_name(),
                        'student_number': student.student_number,
                        'gender': student.user.gender if hasattr(student.user, 'gender') else None,
                        'attendance': attendance,
                        'subjects': subject_rows,
                    })

                sections_payload.append({
                    'section_id': section_id,
                    'section_name': section.name,
                    'students': students_payload,
                })

        return Response({'mode': mode, 'sections': sections_payload})


class StudentPerformanceDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, student_id):
        user = request.user
        if user.role not in ['adviser', 'instructor', 'teacher']:
            return Response({'error': 'Forbidden'}, status=403)

        student = Student.objects.filter(id=student_id).select_related('user').first()
        if not student:
            return Response({'error': 'Student not found'}, status=404)

        enrollment = Enrollment.objects.filter(student=student, is_current=True, status='enrolled').select_related('section').first()
        if not enrollment:
            return Response({'error': 'Enrollment not found'}, status=404)

        section = enrollment.section

        if user.role == 'adviser':
            if not section or not section.adviser_id or section.adviser.user_id != user.id:
                return Response({'error': 'Forbidden'}, status=403)
            section_subjects = SectionSubject.objects.filter(section=section).select_related('subject', 'instructor__user', 'adviser__user')
        else:
            section_subjects = SectionSubject.objects.filter(
                section=section
            ).filter(Q(instructor__user=user) | Q(adviser__user=user)).select_related('subject', 'instructor__user', 'adviser__user')

        assignments = Assignment.objects.filter(section_subject__in=section_subjects).select_related('section_subject')
        quizzes = Quiz.objects.filter(section_subject__in=section_subjects).select_related('section_subject')

        submissions = AssignmentSubmission.objects.filter(
            assignment__in=assignments,
            student=student,
        ).select_related('assignment')

        submissions_by_assignment = {str(sub.assignment_id): sub for sub in submissions}

        attempts = QuizAttempt.objects.filter(
            quiz__in=quizzes,
            student=student,
            submitted_at__isnull=False,
        ).select_related('quiz')

        latest_attempt_by_quiz = {}
        for attempt in attempts:
            key = str(attempt.quiz_id)
            existing = latest_attempt_by_quiz.get(key)
            if not existing or (attempt.submitted_at and existing.submitted_at and attempt.submitted_at > existing.submitted_at):
                latest_attempt_by_quiz[key] = attempt

        violations = QuizProctorEvent.objects.filter(
            event_type='violation',
            session__student=student,
            session__quiz__in=quizzes,
        ).select_related('session__quiz')
        violations_by_ss = {}
        for event in violations:
            ss_id = str(event.session.quiz.section_subject_id)
            violations_by_ss[ss_id] = violations_by_ss.get(ss_id, 0) + 1

        attendance_records = AttendanceRecord.objects.filter(student=student, session__section=section)
        attendance = {'present': 0, 'absent': 0, 'late': 0, 'excused': 0, 'total': 0}
        for record in attendance_records:
            attendance[record.status] += 1
            attendance['total'] += 1

        subjects_payload = []
        for ss in section_subjects:
            ss_id = str(ss.id)
            assignments_list = [a for a in assignments if a.section_subject_id == ss.id]
            quizzes_list = [q for q in quizzes if q.section_subject_id == ss.id]

            assignment_total_points = 0.0
            assignment_score_points = 0.0
            assignment_missing = 0
            for assignment in assignments_list:
                assignment_total_points += float(assignment.total_points or 0.0)
                submission = submissions_by_assignment.get(str(assignment.id))
                if submission and submission.score is not None:
                    assignment_score_points += float(submission.score or 0.0)
                else:
                    assignment_missing += 1

            quiz_total_points = 0.0
            quiz_score_points = 0.0
            quiz_missing = 0
            for quiz in quizzes_list:
                quiz_total_points += float(quiz.total_points or 0.0)
                attempt = latest_attempt_by_quiz.get(str(quiz.id))
                if attempt:
                    quiz_score_points += float(attempt.score or 0.0)
                else:
                    quiz_missing += 1

            subjects_payload.append({
                'section_subject_id': ss_id,
                'subject_name': ss.subject.name,
                'teacher_name': ss.instructor.user.get_full_name() if ss.instructor_id else (ss.adviser.user.get_full_name() if ss.adviser_id else None),
                'assignments_score': round(assignment_score_points, 1),
                'assignments_total': round(assignment_total_points, 1),
                'quizzes_score': round(quiz_score_points, 1),
                'quizzes_total': round(quiz_total_points, 1),
                'missing_assignments': assignment_missing,
                'missing_quizzes': quiz_missing,
                'violations': violations_by_ss.get(ss_id, 0),
            })

        return Response({
            'student_id': str(student.id),
            'student_name': student.user.get_full_name(),
            'student_number': student.student_number,
            'gender': student.user.gender if hasattr(student.user, 'gender') else None,
            'section_id': str(section.id) if section else None,
            'section_name': section.name if section else None,
            'attendance': attendance,
            'subjects': subjects_payload,
        })


class PublicStatsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        teachers_count = Instructor.objects.count() + Adviser.objects.count()
        students_count = Student.objects.count()
        subjects_count = Subject.objects.count()
        return Response({
            'teachers': teachers_count,
            'students': students_count,
            'subjects': subjects_count,
        })


class TeacherStudentsView(APIView):
    """Returns only students that belong to the requesting teacher's assigned subjects/sections."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if user.role not in ['instructor', 'adviser', 'teacher']:
            return Response([], status=200)

        if user.role == 'adviser':
            # Adviser owns sections directly
            sections = Section.objects.filter(adviser__user=user)
            enrollments = Enrollment.objects.filter(
                section__in=sections, is_current=True, status='enrolled'
            ).select_related('student__user')
        else:
            # Instructor — scoped to their section subjects
            section_subjects = SectionSubject.objects.filter(
                Q(instructor__user=user) | Q(adviser__user=user)
            )
            enrollments = Enrollment.objects.filter(
                section__in=section_subjects.values_list('section_id', flat=True),
                is_current=True,
                status='enrolled',
            ).select_related('student__user')

        seen = set()
        students = []
        for enrollment in enrollments:
            student = enrollment.student
            if str(student.id) in seen:
                continue
            seen.add(str(student.id))
            students.append({
                'id': str(student.id),
                'user': str(student.user_id),
                'user_name': student.user.get_full_name(),
                'student_number': student.student_number,
            })

        return Response(students)
