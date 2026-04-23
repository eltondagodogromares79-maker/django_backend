from rest_framework import permissions


class IsAdminOrPrincipal(permissions.BasePermission):
    """Permission for admins, principals, and deans only"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ['admin', 'principal', 'dean']


class IsTeacherOrAdmin(permissions.BasePermission):
    """Permission for instructors/advisers, admins, principals, and deans"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ['instructor', 'adviser', 'admin', 'principal', 'dean']


class IsStudentOrTeacherOrAdmin(permissions.BasePermission):
    """Permission for students, instructors/advisers, admins, principals, and deans"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ['student', 'instructor', 'adviser', 'admin', 'principal', 'dean']


class IsOwnerOrTeacherOrAdmin(permissions.BasePermission):
    """Permission for object owner, instructors/advisers, admins, principals, and deans"""
    def has_object_permission(self, request, view, obj):
        if request.user.role in ['admin', 'principal', 'dean']:
            return True
        
        if request.user.role in ['instructor', 'adviser']:
            if hasattr(obj, 'instructor'):
                return getattr(obj.instructor, 'user', None) == request.user
            if hasattr(obj, 'section_subject') and hasattr(obj.section_subject, 'instructor'):
                return obj.section_subject.instructor.user == request.user
            if hasattr(obj, 'quiz') and hasattr(obj.quiz, 'section_subject'):
                return obj.quiz.section_subject.instructor.user == request.user
            if hasattr(obj, 'assignment') and hasattr(obj.assignment, 'section_subject'):
                return obj.assignment.section_subject.instructor.user == request.user
        
        if request.user.role == 'student' and hasattr(obj, 'student'):
            return getattr(obj.student, 'user', None) == request.user
            
        return False


class ReadOnlyOrAdminWrite(permissions.BasePermission):
    """Read-only for all authenticated users, write for admins only"""
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return request.user.is_authenticated
        return request.user.is_authenticated and request.user.role in ['admin', 'principal', 'dean']
