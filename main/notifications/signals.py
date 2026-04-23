from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from assignments.models import Assignment, AssignmentSubmission
from attendance.models import AttendanceSession
from learning_materials.models import LearningMaterial
from quizzes.models import Quiz, QuizAttempt
from sections.models import StudentSubject, Enrollment
from .models import Notification
from .utils import push_notification


def _serialize_notification(notification):
    return {
        'id': str(notification.id),
        'kind': notification.kind,
        'title': notification.title,
        'body': notification.body,
        'target_id': str(notification.target_id),
        'section_subject_id': str(notification.section_subject_id) if notification.section_subject_id else None,
        'is_read': notification.is_read,
        'read_at': notification.read_at.isoformat() if notification.read_at else None,
        'created_at': notification.created_at.isoformat(),
    }


def _student_user_ids(section_subject):
    return (
        StudentSubject.objects.filter(section_subject=section_subject)
        .values_list('enrollment__student__user_id', flat=True)
        .distinct()
    )


def _student_user_ids_by_section(section):
    return (
        Enrollment.objects.filter(section=section, is_current=True, status='enrolled')
        .values_list('student__user_id', flat=True)
        .distinct()
    )


def _build_context(section_subject):
    if not section_subject:
        return ''
    subject = getattr(section_subject, 'subject', None)
    section = getattr(section_subject, 'section', None)
    subject_code = getattr(subject, 'code', '') if subject else ''
    section_name = getattr(section, 'name', '') if section else ''
    if subject_code and section_name:
        return f"{subject_code} — {section_name}"
    return subject_code or section_name


def _teacher_user_ids(section_subject):
    if not section_subject:
        return []
    teacher = section_subject.instructor or section_subject.adviser
    if not teacher and section_subject.section_id and section_subject.section.adviser_id:
        teacher = section_subject.section.adviser
    if not teacher:
        return []
    return [str(teacher.user_id)]


def _create_notifications(kind, section_subject, title, target_id, body=None):
    if not section_subject:
        return
    body_text = body if body is not None else _build_context(section_subject)
    for user_id in _student_user_ids(section_subject):
        notification = Notification.objects.create(
            user_id=user_id,
            kind=kind,
            title=title,
            body=body_text,
            target_id=target_id,
            section_subject=section_subject,
        )
        push_notification(user_id, _serialize_notification(notification))


def _create_teacher_notifications(kind, section_subject, title, target_id, body=None):
    if not section_subject:
        return
    body_text = body if body is not None else _build_context(section_subject)
    for user_id in _teacher_user_ids(section_subject):
        notification = Notification.objects.create(
            user_id=user_id,
            kind=kind,
            title=title,
            body=body_text,
            target_id=target_id,
            section_subject=section_subject,
        )
        push_notification(user_id, _serialize_notification(notification))


@receiver(post_save, sender=Assignment)
def notify_assignment(sender, instance, created, **kwargs):
    if not created:
        return
    title = f"New assignment: {instance.title}"
    _create_notifications('assignment', instance.section_subject, title, instance.id)


@receiver(post_save, sender=LearningMaterial)
def notify_lesson(sender, instance, created, **kwargs):
    if not created:
        return
    title = f"New learning material: {instance.title}"
    _create_notifications('lesson', instance.section_subject, title, instance.id)


@receiver(post_save, sender=Quiz)
def notify_quiz(sender, instance, created, **kwargs):
    if not created:
        return
    title = f"New quiz: {instance.title}"
    _create_notifications('quiz', instance.section_subject, title, instance.id)


@receiver(post_save, sender=AttendanceSession)
def notify_attendance_session(sender, instance, created, **kwargs):
    if not created:
        return
    if getattr(instance, 'is_online_class', False):
        title = instance.title or 'Online class started'
        kind = 'online_class'
    else:
        title = instance.title or 'Attendance session scheduled'
        kind = 'attendance'
    context = _build_context(instance.section_subject) or (instance.section.name if instance.section_id else '')
    body = context
    if instance.scheduled_at:
        schedule_text = instance.scheduled_at.strftime('%b %d, %Y %I:%M %p')
        body = f"{context} • {schedule_text}" if context else schedule_text
    for user_id in _student_user_ids_by_section(instance.section):
        notification = Notification.objects.create(
            user_id=user_id,
            kind=kind,
            title=title,
            body=body,
            target_id=instance.id,
            section_subject=instance.section_subject,
        )
        push_notification(user_id, _serialize_notification(notification))


@receiver(post_save, sender=AssignmentSubmission)
def notify_assignment_submission(sender, instance, created, **kwargs):
    if not created:
        return
    assignment = instance.assignment
    student_name = instance.student.user.get_full_name() if instance.student_id else 'A student'
    context = _build_context(assignment.section_subject)
    title = 'New assignment submission'
    body = f"{student_name} submitted \"{assignment.title}\""
    if context:
        body = f"{body} in {context}"
    _create_teacher_notifications('assignment_submission', assignment.section_subject, title, assignment.id, body=body)


@receiver(post_save, sender=QuizAttempt)
def notify_quiz_submission(sender, instance, created, update_fields=None, **kwargs):
    if not instance.submitted_at:
        return
    if not created:
        previous = getattr(instance, '_previous_submitted_at', None)
        if previous is not None:
            return
    quiz = instance.quiz
    student_name = instance.student.user.get_full_name() if instance.student_id else 'A student'
    context = _build_context(quiz.section_subject)
    title = 'New quiz submission'
    body = f"{student_name} submitted \"{quiz.title}\""
    if context:
        body = f"{body} in {context}"
    _create_teacher_notifications('quiz_submission', quiz.section_subject, title, quiz.id, body=body)


@receiver(pre_save, sender=QuizAttempt)
def cache_quiz_attempt_previous(sender, instance, **kwargs):
    if not instance.pk:
        instance._previous_submitted_at = None
        return
    try:
        instance._previous_submitted_at = QuizAttempt.objects.filter(pk=instance.pk).values_list('submitted_at', flat=True).first()
    except Exception:
        instance._previous_submitted_at = None
