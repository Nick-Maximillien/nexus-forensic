from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import get_user_model
from .models import LawyerProfile, NGOProfile, DonorProfile, AdminProfile

User = get_user_model()

# ================== JWT Token Serializer ==================
class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['email'] = user.email
        token['role'] = user.role
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data['email'] = self.user.email
        data['role'] = self.user.role
        return data

# ================== Signup Serializer ==================
class SignupSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)
    role = serializers.ChoiceField(choices=User.Roles.choices)

    class Meta:
        model = User
        fields = ['email', 'password', 'role', 'username']

    def create(self, validated_data):
        user = User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            role=validated_data.get('role', User.Roles.LAWYER),
            username=validated_data.get('username', validated_data['email'])
        )
        return user

# ================== Role-specific Serializers ==================
class LawyerProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = LawyerProfile
        fields = ['specialty', 'verified', 'cases_managed', 'rating']

class NGOProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = NGOProfile
        fields = ['organization_name', 'verified', 'funded_cases']

class DonorProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = DonorProfile
        fields = ['display_name', 'contribution_count', 'total_contributed']

class AdminProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdminProfile
        fields = ['permissions']

from rest_framework import serializers
from django.contrib.auth import get_user_model

User = get_user_model()

class MirrorUserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(required=True)
    organization_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    practicing_certificate = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    role = serializers.ChoiceField(choices=User.Roles.choices)
    password = serializers.CharField(write_only=True, required=True, max_length=256)

    class Meta:
        model = User
        fields = ['email', 'password', 'full_name', 'role', 'organization_name', 'practicing_certificate']

    def create(self, validated_data):
        """
        Create a new User instance from validated data.
        Maps full_name -> username, handles optional fields safely.
        """
        full_name = validated_data.get("full_name", "")
        username = full_name.strip().replace(" ", "_").lower() or validated_data.get("email").split("@")[0]
        password = validated_data.get("password")
        if not password:
            raise serializers.ValidationError("Password is required for mirroring")
        
        user = User.objects.create(
            email=validated_data["email"],
            username=username,
            role=validated_data.get("role", User.Roles.LAWYER),
            # Optional fields are ignored by default in the User model, can be set via signals or later updates
        )
        user.set_password(password)
        user.save()  

        return user
