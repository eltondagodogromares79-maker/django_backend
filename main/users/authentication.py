from rest_framework_simplejwt.authentication import JWTAuthentication


class CookieJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        auth_header = request.headers.get("Authorization", "")
        token = None

        if auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1].strip()

        if token is None:
            token = request.COOKIES.get("access_token")

        if not token:
            return None

        validated_token = self.get_validated_token(token)
        user = self.get_user(validated_token)

        return (user, validated_token)
