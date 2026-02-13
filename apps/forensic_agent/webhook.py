import json
import logging
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

logger = logging.getLogger(__name__)

@csrf_exempt
def meta_webhook(request):
    """
    Handles Webhook Verification (GET) and Incoming Messages (POST).
    """
    # -----------------------------------------------------------
    # 1. VERIFICATION STEP (This is what the Dashboard checks)
    # -----------------------------------------------------------
    if request.method == 'GET':
        mode = request.GET.get('hub.mode')
        token = request.GET.get('hub.verify_token')
        challenge = request.GET.get('hub.challenge')

        if mode == 'subscribe' and token == settings.META_WEBHOOK_VERIFY_TOKEN:
            logger.info(" Meta Webhook Verified!")
            return HttpResponse(challenge, status=200)
        else:
            logger.warning(" Webhook Verification Failed (Wrong Token)")
            return HttpResponse('Forbidden', status=403)

    # -----------------------------------------------------------
    # 2. INCOMING MESSAGES (POST) - For future "Reply" logic
    # -----------------------------------------------------------
    elif request.method == 'POST':
        try:
            body = json.loads(request.body)
            # Just log it for now so you see it works
            logger.info(f" Incoming Meta Webhook: {body}")
            return JsonResponse({'status': 'received'}, status=200)
        except Exception as e:
            logger.error(f"Webhook Error: {e}")
            return JsonResponse({'status': 'error'}, status=400)

    return HttpResponse('Method Not Allowed', status=405)