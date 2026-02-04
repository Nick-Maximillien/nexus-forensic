from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, serializers as drf_serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.generics import RetrieveUpdateAPIView
import requests
from rest_framework import status
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated




from .serializers import (
    SignupSerializer, CustomTokenObtainPairSerializer,
    LawyerProfileSerializer, NGOProfileSerializer,
    DonorProfileSerializer, AdminProfileSerializer, MirrorUserSerializer
)
from .signals import trigger_wallet_creation

from .models import User

User = get_user_model()

# ================== Signup ==================
class SignupView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()

            token_serializer = CustomTokenObtainPairSerializer(data={
                'email': request.data['email'],
                'password': request.data['password']
            })
            token_serializer.is_valid(raise_exception=True)
            tokens = token_serializer.validated_data

            return Response({
                'message': 'Signup successful.',
                'access': tokens['access'],
                'refresh': tokens['refresh'],
                'email': user.email,
                'role': user.role,
                'username': user.username,
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# ================== Login (JWT) ==================
class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

# ================== Health Check ==================
class HealthCheckView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"status": "ok"})


# ================== Superuser Creation (Dev Only) ==================
@csrf_exempt
def create_superuser_view(request):
    if request.method != "POST":
        return Response({"error": "POST required"}, status=405)

    if not User.objects.filter(email="admin@hakichain.com").exists():
        User.objects.create_superuser(
            email="admin@hakichain.com",
            password="admin123",
            username="admin",
            role=User.Roles.ADMIN
        )
        return Response({"message": "✅ Superuser created: admin@hakichain.com / admin123"})
    return Response({"message": "❌ Superuser already exists."})

# ================== RoleProfileView ==================
class RoleProfileView(RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        role_serializers = {
            User.Roles.LAWYER: LawyerProfileSerializer,
            User.Roles.NGO: NGOProfileSerializer,
            User.Roles.DONOR: DonorProfileSerializer,
            User.Roles.ADMIN: AdminProfileSerializer,
        }
        serializer = role_serializers.get(self.request.user.role)
        if not serializer:
            raise drf_serializers.ValidationError("Unknown user role")
        return serializer

    def get_object(self):
        role_profiles = {
            User.Roles.LAWYER: 'lawyer_profile',
            User.Roles.NGO: 'ngo_profile',
            User.Roles.DONOR: 'donor_profile',
            User.Roles.ADMIN: 'admin_profile',
        }
        attr = role_profiles.get(self.request.user.role)
        if not attr:
            raise drf_serializers.ValidationError("Unknown user role")
        return getattr(self.request.user, attr)
    

from django.db import transaction

class MirrorUserView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        data = request.data.copy()
        user_type = data.get("user_type", "LAWYER").upper()
        data["role"] = user_type
        data.pop("user_type", None)

        serializer = MirrorUserSerializer(data=data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data.get("email")
        created = False

        def create_or_update_user():
            nonlocal created
            try:
                user = User.objects.get(email=email)
                print(f"🔄 User already exists: updating {email}")
                for field, value in serializer.validated_data.items():
                    if field not in ["email", "password"]:
                        setattr(user, field, value)
                password = serializer.validated_data.get("password")
                if password:
                    user.set_password(password)
                user.save()
                created = False
            except User.DoesNotExist:
                user = serializer.save()
                created = True
            return user

        # Wrap in transaction.atomic + on_commit to ensure DB commit first
        with transaction.atomic():
            user = create_or_update_user()
            transaction.on_commit(lambda: trigger_wallet_creation(user.id, user.email))

        return Response(
            {"message": "User mirrored", "created": created},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )

    

from django.db import transaction 

class SaveWalletView(APIView):
    permission_classes = [AllowAny]

    @transaction.atomic # <-- FORCE COMMIT
    def post(self, request):
        user_id = request.data.get("user_id")
        wallet_address = request.data.get("wallet_address")
        public_key = request.data.get("public_key")
        private_key_encrypted = request.data.get("private_key_encrypted")

        if not user_id or not wallet_address or not public_key or not private_key_encrypted:
            return Response({"error": "Missing fields"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user_id_int = int(user_id)
        except (ValueError, TypeError):
            return Response({"error": f"Invalid user_id: {user_id}"}, status=status.HTTP_400_BAD_REQUEST)
        
        # V V V THE ROBUST WRITE FIX V V V
        update_count = User.objects.filter(id=user_id_int).update(
            wallet_address=wallet_address,
            public_key=public_key,
            private_key_encrypted=private_key_encrypted
        )
        # ^ ^ ^ THE ROBUST WRITE FIX ^ ^ ^

        if update_count == 0:
            print(f"❌ Wallet save failed: User ID {user_id_int} not found")
            return Response({"error": "User not found or not updated"}, status=status.HTTP_404_NOT_FOUND)
        
        # Success printing relies on the update being completed.
        # Fetch the user again to show the saved data in the log.
        user = User.objects.get(id=user_id_int)
        print(f"💳 Saving wallet for user {user.email} (ID: {user.id})")
        print(f"   Wallet Address (incoming): {wallet_address}")
        print(f"   Public Key (incoming): {public_key}")
        print(f"   Encrypted Private Key (incoming): {private_key_encrypted}")
        print(f"✅ Wallet saved to DB for user {user.email}")
        print(f"   New DB Wallet Address: {user.wallet_address}")
        print(f"   New DB Public Key: {user.public_key}")
        print(f"   New DB Encrypted Private Key: {user.private_key_encrypted}")
        
        return Response({"message": "Wallet saved"}, status=status.HTTP_200_OK)



class GetWalletView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic # <-- Required for select_for_update()
    def get(self, request):
        print("=== GetWalletView Called ===")
        print(f"Request user (from token): {request.user.email} ({request.user.role}) (is_authenticated={request.user.is_authenticated})")

        # V V V THE SYNCHRONIZED READ FIX V V V
        try:
            # Forces the query to read the LATEST COMMITTED data
            user = User.objects.select_for_update().get(pk=request.user.pk)
        except User.DoesNotExist:
            print(f"❌ User {request.user.email} not found in DB")
            return Response({"error": "User not found"}, status=404)
        # ^ ^ ^ THE SYNCHRONIZED READ FIX ^ ^ ^

        print(f"User wallet_address: {user.wallet_address}")
        print(f"User public_key: {getattr(user, 'public_key', None)}")

        if not user.wallet_address:
            print("❌ Wallet not found for user")
            return Response({"error": "Wallet not found"}, status=404)

        print("✅ Returning wallet info")
        return Response({
            "wallet_address": user.wallet_address,
            "public_key": user.public_key,
        })



class SignTransactionView(APIView):
    """
    Authenticated endpoint to retrieve the user's encrypted private key
    and forward it, along with the transaction data, to the Node.js signing server.
    """
    permission_classes = [IsAuthenticated]
    
    # Configure Node.js signing endpoint
    NODE_SIGNING_URL = getattr(settings, "NODE_SIGNING_URL", "http://localhost:4000/sign-and-send-tx") 

    def post(self, request):
        # 1. Fetch user data (Wallet Address and Encrypted Private Key)
        user = request.user
        
        # Check if wallet data exists
        if not user.private_key_encrypted or not user.wallet_address:
            return Response({"error": "User wallet not initialized or private key missing"}, 
                            status=status.HTTP_400_BAD_REQUEST)

        # 2. Extract transaction payload from the client
        # The client will send the *intended* contract call data (function, args, value, etc.)
        tx_payload = request.data.get("tx_payload")
        
        if not tx_payload:
            return Response({"error": "Missing transaction payload (tx_payload)"}, 
                            status=status.HTTP_400_BAD_REQUEST)

        # 3. Compile ALL necessary data for Node.js
        forward_data = {
            "wallet_address": user.wallet_address,
            "private_key_encrypted": user.private_key_encrypted,
            "tx_payload": tx_payload,
            "user_id": user.id,
            "email": user.email,
        }
        
        # 4. Forward to Node.js signing server
        try:
            print(f"📡 Forwarding signing request for user {user.id} to Node.js...")
            node_response = requests.post(
                self.NODE_SIGNING_URL, 
                json=forward_data, 
                timeout=30
            )
            node_response.raise_for_status() # Raise error for bad status codes

            # 5. Return the result (txHash) directly to the client
            return Response(node_response.json(), status=status.HTTP_200_OK)

        except requests.exceptions.HTTPError as e:
            print(f"❌ Node.js signing failed (HTTP Error): {e}")
            try:
                error_details = e.response.json().get('error', e.response.text)
            except:
                error_details = e.response.text
            return Response({"error": f"Transaction signing failed on server.", "details": error_details}, 
                            status=e.response.status_code)

        except requests.exceptions.RequestException as e:
            print(f"❌ Failed to reach Node.js server: {e}")
            return Response({"error": "Failed to connect to signing server"}, 
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)
        

