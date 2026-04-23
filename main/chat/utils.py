from typing import Optional
from django.utils import timezone
from django.db import transaction
from users.models import CustomUser, Student, Instructor, Adviser
from sections.models import Enrollment, Section
from subjects.models import SectionSubject
from .models import ChatRoom, ChatRoomMember


def parse_room_key(room_key: str):
    if room_key.startswith('section:'):
        return ChatRoom.RoomType.SECTION, room_key.split('section:', 1)[1]
    if room_key.startswith('dm:'):
        return ChatRoom.RoomType.DIRECT, None
    if room_key.startswith('group:'):
        return ChatRoom.RoomType.GROUP, None
    return ChatRoom.RoomType.GROUP, None


def parse_direct_room_members(room_key: str):
    if not room_key.startswith('dm:'):
        return None
    parts = room_key.split(':')
    if len(parts) != 3:
        return None
    return parts[1], parts[2]


def _get_student_current_or_latest_enrollment(student: Optional[Student]):
    if not student:
        return None
    enrollment = (
        Enrollment.objects.select_related('section__year_level__program')
        .filter(student=student, is_current=True)
        .first()
    )
    if enrollment:
        return enrollment
    return (
        Enrollment.objects.select_related('section__year_level__program')
        .filter(student=student)
        .order_by('-enrolled_at')
        .first()
    )


def _get_student_scope(user: CustomUser):
    student = Student.objects.filter(user=user).first()
    enrollment = _get_student_current_or_latest_enrollment(student)
    if not enrollment or not enrollment.section_id:
        return None, None
    section_id = str(enrollment.section_id)
    program_id = str(enrollment.section.year_level.program_id) if enrollment.section and enrollment.section.year_level_id else None
    return section_id, program_id


def _get_instructor_scope(user: CustomUser):
    instructor = Instructor.objects.filter(user=user).first()
    if not instructor:
        return set(), set()
    section_subjects = SectionSubject.objects.filter(instructor=instructor).select_related('section__year_level__program')
    section_ids = {str(section_id) for section_id in section_subjects.values_list('section_id', flat=True)}
    program_ids = {
        str(program_id)
        for program_id in section_subjects.values_list('section__year_level__program_id', flat=True)
        if program_id
    }
    return section_ids, program_ids


def _get_adviser_scope(user: CustomUser):
    adviser = Adviser.objects.prefetch_related('sections').filter(user=user).first()
    if not adviser:
        return set(), set()
    section_ids = {str(section_id) for section_id in adviser.sections.values_list('id', flat=True)}
    program_ids = {str(adviser.program_id)} if adviser.program_id else set()
    return section_ids, program_ids


def get_allowed_chat_contacts_queryset(user: CustomUser):
    if user.role == 'admin' or user.is_staff:
        return CustomUser.objects.filter(is_active=True).exclude(id=user.id)

    if user.role == 'student':
        section_id, program_id = _get_student_scope(user)
        if not section_id and not program_id:
            return CustomUser.objects.none()

        if section_id or program_id:
            from django.db.models import Q

            enrollment_q = Q()
            if section_id:
                enrollment_q |= Q(section_id=section_id)
            if program_id:
                enrollment_q |= Q(section__year_level__program_id=program_id)

            section_subject_q = Q()
            if section_id:
                section_subject_q |= Q(section_id=section_id)
            if program_id:
                section_subject_q |= Q(section__year_level__program_id=program_id)

            section_q = Q()
            if section_id:
                section_q |= Q(id=section_id)
            if program_id:
                section_q |= Q(year_level__program_id=program_id)

            student_ids = Enrollment.objects.filter(is_current=True).filter(enrollment_q).values_list('student__user_id', flat=True)
            instructor_ids = SectionSubject.objects.filter(section_subject_q, instructor__isnull=False).values_list('instructor__user_id', flat=True)
            adviser_ids = SectionSubject.objects.filter(section_subject_q, adviser__isnull=False).values_list('adviser__user_id', flat=True)
            section_adviser_ids = Section.objects.filter(section_q, adviser__isnull=False).values_list('adviser__user_id', flat=True)
            return (
                CustomUser.objects.filter(is_active=True, id__in=set(student_ids) | set(instructor_ids) | set(adviser_ids) | set(section_adviser_ids))
                .exclude(id=user.id)
                .distinct()
            )
        return CustomUser.objects.none()

    if user.role == 'instructor':
        section_ids, program_ids = _get_instructor_scope(user)
        if not section_ids and not program_ids:
            return CustomUser.objects.none()
        from django.db.models import Q

        q = Q()
        if section_ids:
            q |= Q(section_id__in=section_ids)
        if program_ids:
            q |= Q(section__year_level__program_id__in=program_ids)
        student_ids = Enrollment.objects.filter(
            is_current=True
        ).filter(q).values_list('student__user_id', flat=True)
        return CustomUser.objects.filter(is_active=True, id__in=student_ids).exclude(id=user.id).distinct()

    if user.role == 'adviser':
        section_ids, program_ids = _get_adviser_scope(user)
        if not section_ids and not program_ids:
            return CustomUser.objects.none()
        from django.db.models import Q

        q = Q()
        if section_ids:
            q |= Q(section_id__in=section_ids)
        if program_ids:
            q |= Q(section__year_level__program_id__in=program_ids)
        student_ids = Enrollment.objects.filter(
            is_current=True
        ).filter(q).values_list('student__user_id', flat=True)
        return CustomUser.objects.filter(is_active=True, id__in=student_ids).exclude(id=user.id).distinct()

    return CustomUser.objects.none()


def user_can_direct_message(user: CustomUser, other_user: CustomUser) -> bool:
    if user.role == 'admin' or user.is_staff:
        return other_user.is_active and other_user.id != user.id
    return get_allowed_chat_contacts_queryset(user).filter(id=other_user.id).exists()


def get_or_create_room(
    room_key: str,
    room_type: Optional[str] = None,
    section_id: Optional[str] = None,
    created_by: Optional[CustomUser] = None,
    created_by_id: Optional[str] = None,
):
    inferred_type, inferred_section_id = parse_room_key(room_key)
    final_type = room_type or inferred_type
    final_section_id = section_id or inferred_section_id

    defaults = {'room_type': final_type}
    if final_type == ChatRoom.RoomType.SECTION and final_section_id:
        if not Section.objects.filter(id=final_section_id).exists():
            raise ValueError('Invalid section id for room')
        defaults['section_id'] = final_section_id
    if created_by:
        defaults['created_by'] = created_by
    if created_by_id and 'created_by' not in defaults:
        defaults['created_by_id'] = created_by_id

    room, _ = ChatRoom.objects.get_or_create(room_key=room_key, defaults=defaults)
    return room


def user_can_access_room(user: CustomUser, room: ChatRoom) -> bool:
    if user.role == 'admin' or user.is_staff:
        return True

    if room.room_type == ChatRoom.RoomType.SECTION:
        return user_in_section(user, room.section_id)

    if room.room_type == ChatRoom.RoomType.DIRECT:
        members = parse_direct_room_members(room.room_key)
        if not members:
            return False
        left_id, right_id = members
        user_id = str(user.id)
        if user_id not in {left_id, right_id}:
            return False
        other_id = right_id if left_id == user_id else left_id
        other_user = CustomUser.objects.filter(id=other_id, is_active=True).first()
        if not other_user:
            return False
        return user_can_direct_message(user, other_user)

    return ChatRoomMember.objects.filter(room=room, user=user).exists()


def user_in_section(user: CustomUser, section_id: Optional[str]) -> bool:
    if not section_id:
        return False

    if user.role == 'student':
        student = Student.objects.select_related('user').filter(user=user).first()
        if not student:
            return False
        return Enrollment.objects.filter(student=student, section_id=section_id, is_current=True).exists()

    if user.role == 'adviser':
        adviser = Adviser.objects.select_related('user').filter(user=user).first()
        if not adviser:
            return False
        return adviser.sections.filter(id=section_id).exists()

    if user.role == 'instructor':
        instructor = Instructor.objects.select_related('user').filter(user=user).first()
        if not instructor:
            return False
        return SectionSubject.objects.filter(instructor=instructor, section_id=section_id).exists()

    return False


def ensure_members(room: ChatRoom, member_ids):
    members = [str(member_id) for member_id in member_ids]
    existing = set(
        ChatRoomMember.objects.filter(room=room, user_id__in=members).values_list('user_id', flat=True)
    )
    to_create = [
        ChatRoomMember(room=room, user_id=member_id)
        for member_id in members
        if member_id not in existing
    ]
    if to_create:
        ChatRoomMember.objects.bulk_create(to_create, ignore_conflicts=True)


def update_read_receipt(room: ChatRoom, user: CustomUser, last_read_at):
    if not last_read_at:
        last_read_at = timezone.now()
    with transaction.atomic():
        receipt, _ = ChatReadReceipt.objects.select_for_update().get_or_create(room=room, user=user, defaults={'last_read_at': last_read_at})
        receipt.last_read_at = last_read_at
        receipt.save(update_fields=['last_read_at', 'updated_at'])
    return receipt

from .models import ChatReadReceipt  # placed at end to avoid circular import
