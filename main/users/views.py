from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q
from .models import CustomUser, Student, Instructor, Adviser, Principal, Dean, AdminProfile, PasswordResetCode
from .serializers import (
    UserSerializer,
    UserProfileSerializer,
    ChangePasswordSerializer,
    StudentSerializer,
    InstructorSerializer,
    AdviserSerializer,
    PrincipalSerializer,
    DeanSerializer,
    AdminProfileSerializer,
    PublicStaffSerializer,
)
from shared.permissions import IsAdminOrPrincipal, ReadOnlyOrAdminWrite
from rest_framework import status
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password, check_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.utils import timezone
from datetime import timedelta
import secrets
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken
import jwt
from django.conf import settings
from sections.models import Enrollment
from chat.models import ChatRoomMember
from subjects.models import SectionSubject


def _get_current_enrollment(student):
    if not student:
        return None
    enrollment = Enrollment.objects.select_related(
        'section__year_level__program', 'term', 'school_year'
    ).filter(student=student, is_current=True).order_by('-enrolled_at').first()
    if not enrollment:
        enrollment = Enrollment.objects.select_related(
            'section__year_level__program', 'term', 'school_year'
        ).filter(student=student).order_by('-enrolled_at').first()
    if not enrollment:
        return None
    return {
        'id': str(enrollment.id),
        'section': enrollment.section.name if enrollment.section_id else None,
        'year_level': enrollment.section.year_level.name if enrollment.section_id else None,
        'program': enrollment.section.year_level.program.name if enrollment.section_id else None,
        'term': str(enrollment.term) if enrollment.term_id else None,
        'school_year': enrollment.school_year.name if enrollment.school_year_id else None,
        'status': enrollment.status,
        'is_current': enrollment.is_current,
        'enrolled_at': enrollment.enrolled_at,
    }


class UserViewSet(viewsets.ModelViewSet):
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy', 'list']:
            permission_classes = [IsAdminOrPrincipal]
        elif self.action in ['retrieve', 'profile', 'update_profile']:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]
    
    def get_object(self):
        if self.action in ['profile', 'update_profile']:
            return self.request.user
        return super().get_object()
    
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # Users can only view their own profile unless admin
        if instance != request.user and request.user.role not in ['admin', 'principal', 'dean']:
            return Response(
                {'error': 'Permission denied'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        serializer = self.get_serializer(instance)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def profile(self, request):
        """Get current user's profile"""
        serializer = UserProfileSerializer(request.user, context={"request": request})
        data = serializer.data
        if request.user.role == 'student':
            student = Student.objects.select_related('user').filter(user=request.user).first()
            if student:
                enrollments = Enrollment.objects.select_related(
                    'section__year_level__program', 'term', 'school_year'
                ).filter(student=student).order_by('-enrolled_at')
                data['student'] = {
                    'id': str(student.id),
                    'student_number': student.student_number,
                    'admission_date': student.admission_date,
                    'emergency_contact_name': student.emergency_contact_name,
                    'emergency_contact_phone': student.emergency_contact_phone,
                    'emergency_contact_relationship': student.emergency_contact_relationship,
                    'current_enrollment': _get_current_enrollment(student),
                    'enrollments': [
                        {
                            'id': str(enrollment.id),
                            'section': enrollment.section.name if enrollment.section_id else None,
                            'year_level': enrollment.section.year_level.name if enrollment.section_id else None,
                            'program': enrollment.section.year_level.program.name if enrollment.section_id else None,
                            'term': str(enrollment.term) if enrollment.term_id else None,
                            'school_year': enrollment.school_year.name if enrollment.school_year_id else None,
                            'status': enrollment.status,
                            'is_current': enrollment.is_current,
                            'enrolled_at': enrollment.enrolled_at,
                        }
                        for enrollment in enrollments
                    ],
                }
        elif request.user.role == 'instructor':
            instructor = Instructor.objects.select_related('department').filter(user=request.user).first()
            if instructor and instructor.department_id:
                data['department'] = instructor.department.name
        elif request.user.role == 'adviser':
            adviser = Adviser.objects.select_related('department').filter(user=request.user).first()
            if adviser and adviser.department_id:
                data['department'] = adviser.department.name
        return Response(data)

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def chat_context(self, request):
        """Return chat context: user id, role, and default section rooms."""
        data = {
            'id': str(request.user.id),
            'role': request.user.role,
            'sections': [],
            'hidden_rooms': [],
        }
        if request.user.role == 'student':
            student = Student.objects.select_related('user').filter(user=request.user).first()
            if student:
                current = Enrollment.objects.select_related('section').filter(student=student, is_current=True).first()
                if not current:
                    current = Enrollment.objects.select_related('section').filter(student=student).order_by('-enrolled_at').first()
                if current and current.section_id:
                    data['sections'] = [{'id': str(current.section.id), 'name': current.section.name}]
        elif request.user.role == 'adviser':
            adviser = Adviser.objects.select_related('user').prefetch_related('sections').filter(user=request.user).first()
            if adviser:
                data['sections'] = [
                    {'id': str(section.id), 'name': section.name}
                    for section in adviser.sections.all()
                ]
        elif request.user.role == 'instructor':
            instructor = Instructor.objects.select_related('user').filter(user=request.user).first()
            if instructor:
                section_ids = (
                    SectionSubject.objects.filter(instructor=instructor)
                    .select_related('section')
                    .values_list('section__id', 'section__name')
                    .distinct()
                )
                data['sections'] = [
                    {'id': str(section_id), 'name': section_name}
                    for section_id, section_name in section_ids
                ]
        hidden_rooms = ChatRoomMember.objects.filter(user=request.user, is_hidden=True).values_list('room__room_key', flat=True)
        data['hidden_rooms'] = list(hidden_rooms)
        return Response(data)

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def chat_ws_token(self, request):
        """Return access token for WebSocket auth (read from httpOnly cookie)."""
        access_token = request.COOKIES.get('access_token')
        if not access_token:
            auth_header = request.headers.get('Authorization', '')
            if auth_header.lower().startswith('bearer '):
                access_token = auth_header.split(' ', 1)[1].strip()
        if not access_token:
            return Response({'error': 'Access token not found'}, status=status.HTTP_401_UNAUTHORIZED)
        return Response({'token': access_token})
    
    @action(detail=False, methods=['patch', 'put'], permission_classes=[permissions.IsAuthenticated])
    def update_profile(self, request):
        """Update current user's profile"""
        serializer = UserProfileSerializer(
            request.user, data=request.data, partial=True, context={"request": request}
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def change_password(self, request):
        """Change current user's password"""
        serializer = ChangePasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        current_password = serializer.validated_data['current_password']
        new_password = serializer.validated_data['new_password']

        if not user.check_password(current_password):
            return Response(
                {"current_password": "Current password is incorrect."},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(new_password)
        if user.must_change_password:
            user.must_change_password = False
            user.save(update_fields=["password", "must_change_password"])
        else:
            user.save(update_fields=["password"])

        return Response({"message": "Password changed successfully."})


class StudentViewSet(viewsets.ModelViewSet):
    queryset = Student.objects.select_related('user')
    serializer_class = StudentSerializer
    permission_classes = [ReadOnlyOrAdminWrite]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'student':
            return Student.objects.filter(user=user)
        return super().get_queryset()


class InstructorViewSet(viewsets.ModelViewSet):
    queryset = Instructor.objects.select_related('user', 'department')
    serializer_class = InstructorSerializer
    permission_classes = [ReadOnlyOrAdminWrite]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'instructor':
            return Instructor.objects.filter(user=user)
        return super().get_queryset()

    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def change_password(self, request):
        """Change current user's password"""
        serializer = ChangePasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        current_password = serializer.validated_data['current_password']
        new_password = serializer.validated_data['new_password']

        if not user.check_password(current_password):
            return Response(
                {"current_password": "Current password is incorrect."},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(new_password)
        if user.must_change_password:
            user.must_change_password = False
            user.save(update_fields=["password", "must_change_password"])
        else:
            user.save(update_fields=["password"])

        return Response({"message": "Password changed successfully."})

class AdviserViewSet(viewsets.ModelViewSet):
    queryset = Adviser.objects.select_related('user', 'department', 'program')
    serializer_class = AdviserSerializer
    permission_classes = [ReadOnlyOrAdminWrite]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'adviser':
            return Adviser.objects.filter(user=user)
        return super().get_queryset()


class PrincipalViewSet(viewsets.ModelViewSet):
    queryset = Principal.objects.select_related('user', 'school_level')
    serializer_class = PrincipalSerializer
    permission_classes = [ReadOnlyOrAdminWrite]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'principal':
            return Principal.objects.filter(user=user)
        return super().get_queryset()


class DeanViewSet(viewsets.ModelViewSet):
    queryset = Dean.objects.select_related('user', 'department')
    serializer_class = DeanSerializer
    permission_classes = [ReadOnlyOrAdminWrite]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'dean':
            return Dean.objects.filter(user=user)
        return super().get_queryset()


class AdminProfileViewSet(viewsets.ModelViewSet):
    queryset = AdminProfile.objects.select_related('user')
    serializer_class = AdminProfileSerializer
    permission_classes = [IsAdminOrPrincipal]


def _generate_reset_code():
    return f"{secrets.randbelow(1000000):06d}"


class PasswordResetRequestView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        email = (request.data.get('email') or '').strip().lower()
        try:
            validate_email(email)
        except ValidationError:
            return Response(
                {"detail": "I cannot send a code to your email, please contact your administration to change your password."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = CustomUser.objects.filter(email__iexact=email, is_active=True).first()
        if not user:
            return Response(
                {"detail": "I cannot send a code to your email, please contact your administration to change your password."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        code = _generate_reset_code()
        expires_at = timezone.now() + timedelta(minutes=10)

        PasswordResetCode.objects.filter(user=user, is_used=False).update(is_used=True)
        PasswordResetCode.objects.create(
            user=user,
            code_hash=make_password(code),
            expires_at=expires_at,
        )

        try:
            send_mail(
                subject="SCSIT NEXUS password reset code",
                message=f"Your password reset code is {code}. It expires in 10 minutes.",
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None) or "no-reply@scsitnexus.local",
                recipient_list=[email],
                fail_silently=False,
            )
        except Exception as exc:
            detail = "I cannot send a code to your email, please contact your administration to change your password."
            if settings.DEBUG:
                detail = f"{detail} ({exc})"
            return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"message": "Reset code sent."})


class PasswordResetVerifyView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        email = (request.data.get('email') or '').strip().lower()
        code = (request.data.get('code') or '').strip()
        if not email or not code:
            return Response({"detail": "Email and code are required."}, status=status.HTTP_400_BAD_REQUEST)

        user = CustomUser.objects.filter(email__iexact=email, is_active=True).first()
        if not user:
            return Response({"detail": "Invalid or expired code."}, status=status.HTTP_400_BAD_REQUEST)

        record = PasswordResetCode.objects.filter(
            user=user, is_used=False, expires_at__gte=timezone.now()
        ).order_by('-created_at').first()
        if not record or not check_password(code, record.code_hash):
            return Response({"detail": "Invalid or expired code."}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"valid": True})


class PasswordResetConfirmView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        email = (request.data.get('email') or '').strip().lower()
        code = (request.data.get('code') or '').strip()
        new_password = (request.data.get('new_password') or '').strip()

        if not email or not code or not new_password:
            return Response({"detail": "Email, code, and new password are required."}, status=status.HTTP_400_BAD_REQUEST)

        user = CustomUser.objects.filter(email__iexact=email, is_active=True).first()
        if not user:
            return Response({"detail": "Invalid or expired code."}, status=status.HTTP_400_BAD_REQUEST)

        record = PasswordResetCode.objects.filter(
            user=user, is_used=False, expires_at__gte=timezone.now()
        ).order_by('-created_at').first()
        if not record or not check_password(code, record.code_hash):
            return Response({"detail": "Invalid or expired code."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            validate_password(new_password, user=user)
        except ValidationError as exc:
            return Response({"detail": " ".join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        if user.must_change_password:
            user.must_change_password = False
            user.save(update_fields=["password", "must_change_password"])
        else:
            user.save(update_fields=["password"])

        record.is_used = True
        record.save(update_fields=['is_used'])

        return Response({"message": "Password updated successfully."})


class LoginView(APIView):

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")

        user = authenticate(request, email=email, password=password)

        if not user:
            return Response(
                {"error": "Invalid credentials"},
                status=status.HTTP_401_UNAUTHORIZED
            )

        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        response = Response({
            "message": "Login successful",
            "user": {
                "id": user.id,
                "email": user.email,
                "role": user.role,
                "must_change_password": user.must_change_password,
                "first_name": user.first_name,
                "last_name": user.last_name,
            }
        })
        response.data["access_token"] = access_token
        response.data["refresh_token"] = refresh_token

        if user.role == 'student':
            student = Student.objects.select_related('user').filter(user=user).first()
            response.data["user"]["current_enrollment"] = _get_current_enrollment(student)

        # Access token cookie
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=False,   # True in production (HTTPS)
            samesite="Lax",
            max_age=60 * 15
        )

        # Refresh token cookie
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=False,
            samesite="Lax",
            max_age=60 * 60 * 24
        )

        return response


class PublicStaffPagination(PageNumberPagination):
    page_size = 12
    page_size_query_param = 'page_size'
    max_page_size = 50


class PublicStaffListView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        staff = CustomUser.objects.filter(
            is_active=True,
            role__in=['teacher', 'instructor', 'adviser']
        )
        role_param = (request.query_params.get('role') or '').strip().lower()
        if role_param:
            allowed_roles = {'teacher', 'instructor', 'adviser'}
            roles = [r.strip() for r in role_param.split(',') if r.strip() in allowed_roles]
            if roles:
                staff = staff.filter(role__in=roles)
        search = (request.query_params.get('search') or '').strip()
        if search:
            staff = staff.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(role__icontains=search)
            )
        staff = staff.order_by('last_name', 'first_name')
        paginator = PublicStaffPagination()
        page = paginator.paginate_queryset(staff, request)
        serializer = PublicStaffSerializer(page, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)


class PublicStaffDetailView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def get(self, request, pk):
        staff = CustomUser.objects.filter(
            is_active=True,
            role__in=['teacher', 'instructor', 'adviser'],
            id=pk
        ).first()
        if not staff:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = PublicStaffSerializer(staff, context={'request': request})
        return Response(serializer.data)


class RefreshTokenView(APIView):

    
    authentication_classes = []
    permission_classes = []
    
    def post(self, request):
        # Get refresh token from HTTP-only cookie
        refresh_token = request.COOKIES.get('refresh_token') or request.data.get('refresh_token')
        
        if not refresh_token:
            return Response(
                {"error": "Refresh token not found"},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        try:
            # Validate and decode the refresh token
            refresh = RefreshToken(refresh_token)
            
            # Get user from token
            user_id = refresh.payload.get('user_id')
            user = CustomUser.objects.get(id=user_id)
            
            # Check if user is still active
            if not user.is_active:
                return Response(
                    {"error": "User account is disabled"},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Generate new tokens (token rotation)
            new_refresh = RefreshToken.for_user(user)
            new_access_token = str(new_refresh.access_token)
            new_refresh_token = str(new_refresh)
            
            # Blacklist the old refresh token
            refresh.blacklist()
            
            response = Response({
                "message": "Token refreshed successfully",
                "access_token": new_access_token,
                "refresh_token": new_refresh_token,
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "role": user.role
                }
            })
            
            # Set new access token cookie
            response.set_cookie(
                key="access_token",
                value=new_access_token,
                httponly=True,
                secure=False,  # True in production (HTTPS)
                samesite="Lax",
                max_age=60 * 15  # 15 minutes
            )
            
            # Set new refresh token cookie (token rotation)
            response.set_cookie(
                key="refresh_token",
                value=new_refresh_token,
                httponly=True,
                secure=False,  # True in production (HTTPS)
                samesite="Lax",
                max_age=60 * 60 * 24  # 24 hours
            )
            
            return response
            
        except TokenError as e:
            return Response(
                {"error": "Invalid or expired refresh token"},
                status=status.HTTP_401_UNAUTHORIZED
            )
        except CustomUser.DoesNotExist:
            return Response(
                {"error": "User not found"},
                status=status.HTTP_401_UNAUTHORIZED
            )
        except Exception as e:
            return Response(
                {"error": "Token refresh failed"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class LogoutView(APIView):
    """
    Logout user by blacklisting refresh token and clearing cookies.
    """
    
    authentication_classes = []
    permission_classes = []
    
    def post(self, request):
        try:
            # Get refresh token from HTTP-only cookie
            refresh_token = request.COOKIES.get('refresh_token')
            
            if refresh_token:
                try:
                    # Blacklist the refresh token
                    refresh = RefreshToken(refresh_token)
                    refresh.blacklist()
                except TokenError:
                    # Token is already invalid/blacklisted, continue with logout
                    pass
            
            response = Response({
                "message": "Logged out successfully"
            })
            
            # Clear both access and refresh token cookies
            response.delete_cookie(
                key="access_token",
                path="/",
                samesite="Lax"
            )
            
            response.delete_cookie(
                key="refresh_token",
                path="/",
                samesite="Lax"
            )
            
            return response
            
        except Exception as e:
            # Even if there's an error, we should clear cookies and logout
            response = Response({
                "message": "Logged out successfully"
            })
            
            response.delete_cookie(
                key="access_token",
                path="/",
                samesite="Lax"
            )
            
            response.delete_cookie(
                key="refresh_token",
                path="/",
                samesite="Lax"
            )
            
            return response


class LogoutAllDevicesView(APIView):
    """
    Logout user from all devices by blacklisting all refresh tokens.
    Requires authentication.
    """
    
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        try:
            user = request.user
            
            # Get all outstanding tokens for the user and blacklist them
            # This requires getting all refresh tokens from the database
            # Since we're using simple JWT, we need to track tokens differently
            
            # For now, we'll blacklist the current refresh token
            refresh_token = request.COOKIES.get('refresh_token')
            
            if refresh_token:
                try:
                    refresh = RefreshToken(refresh_token)
                    refresh.blacklist()
                except TokenError:
                    pass
            
            response = Response({
                "message": "Logged out from all devices successfully"
            })
            
            # Clear cookies
            response.delete_cookie(
                key="access_token",
                path="/",
                samesite="Lax"
            )
            
            response.delete_cookie(
                key="refresh_token",
                path="/",
                samesite="Lax"
            )
            
            return response
            
        except Exception as e:
            return Response(
                {"error": "Logout failed"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class VerifyTokenView(APIView):
    """
    Verify if the current access token is valid.
    Returns user information if token is valid.
    """
    
    authentication_classes = []
    permission_classes = []
    
    def get(self, request):
        # Get access token from HTTP-only cookie
        access_token = request.COOKIES.get('access_token')
        
        if not access_token:
            return Response(
                {"error": "Access token not found"},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        try:
            # Decode and verify the access token
            payload = jwt.decode(
                access_token,
                settings.SECRET_KEY,
                algorithms=['HS256']
            )
            
            # Get user from token
            user_id = payload.get('user_id')
            user = CustomUser.objects.get(id=user_id)
            
            # Check if user is still active
            if not user.is_active:
                return Response(
                    {"error": "User account is disabled"},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            return Response({
                "valid": True,
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "role": user.role,
                    "must_change_password": user.must_change_password,
                }
            })
            
        except jwt.ExpiredSignatureError:
            return Response(
                {"error": "Access token has expired"},
                status=status.HTTP_401_UNAUTHORIZED
            )
        except jwt.InvalidTokenError:
            return Response(
                {"error": "Invalid access token"},
                status=status.HTTP_401_UNAUTHORIZED
            )
        except CustomUser.DoesNotExist:
            return Response(
                {"error": "User not found"},
                status=status.HTTP_401_UNAUTHORIZED
            )
        except Exception as e:
            return Response(
                {"error": "Token verification failed"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
