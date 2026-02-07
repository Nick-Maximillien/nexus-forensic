import sys
from django.apps import AppConfig

class ForensicCorpusConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.forensic_corpus"
    verbose_name = "Forensic Corpus (Authoritative Law)"

    def ready(self):
        """
        PERFORMANCE FIX: Trigger Warmup on Startup
        This loads the 4GB GGUF into RAM immediately when the Docker container starts.
        """
        # 1. Define commands where we definitely DO NOT want to load the 4GB model
        #    (to save RAM during builds/migrations)
        maintenance_commands = [
            'migrate', 
            'makemigrations', 
            'collectstatic', 
            'test', 
            'shell', 
            'dbshell'
        ]
        
        # 2. Check if we are running a maintenance command
        #    We check if any argument in sys.argv matches our blocklist
        is_maintenance = any(cmd in sys.argv for cmd in maintenance_commands)

        # 3. If it is NOT maintenance, we assume it is the Server (Gunicorn, Runserver, Uvicorn, etc.)
        #    This 'Fail-Open' logic is much safer for Docker production environments.
        if is_maintenance:
            return

        print("------------------------------------------------", flush=True)
        print("  TRIGGERING MEDGATE BRAIN WARMUP...", flush=True)
        print("    (This loads the model into RAM now to avoid lag later)", flush=True)
        print("------------------------------------------------", flush=True)

        try:
            # Import inside ready() to avoid AppRegistryNotReady errors
            from .ingestion.llm_normalizer import warmup_forensic_brain
            warmup_forensic_brain()
        except Exception as e:
            # Non-fatal (e.g. if model file is missing in dev)
            print(f" [WARMUP SKIPPED] Could not load brain: {e}", flush=True)