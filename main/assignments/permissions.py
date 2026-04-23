from rest_framework import permissions


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
        # Admin, principal, and dean have full access
        if request.user.role in ['admin', 'principal', 'dean']:
            return True
        
        if request.user.role in ['instructor', 'adviser']:
            if hasattr(obj, 'section_subject'):
                return obj.section_subject.instructor.user == request.user
            if hasattr(obj, 'assignment'):
                return obj.assignment.section_subject.instructor.user == request.user
        
        # Students can only access their own submissions
        if request.user.role == 'student' and hasattr(obj, 'student'):
            return obj.student.user == request.user
            
        return False


class CanGradeSubmission(permissions.BasePermission):
    """Permission to grade submissions - only instructors/advisers and admins"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ['instructor', 'adviser', 'admin', 'principal', 'dean']
    
    def has_object_permission(self, request, view, obj):
        # Admin, principal, and dean can grade any submission
        if request.user.role in ['admin', 'principal', 'dean']:
            return True
        
        if request.user.role in ['instructor', 'adviser']:
            return obj.assignment.section_subject.instructor.user == request.user
            
        return False
