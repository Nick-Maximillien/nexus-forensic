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
        maintenance_commands = [
            'migrate', 
            'makemigrations', 
            'collectstatic', 
            'test', 
            'shell', 
            'dbshell'
        ]
        
        is_maintenance = any(cmd in sys.argv for cmd in maintenance_commands)

        if is_maintenance:
            return

        #  Warmup toggle 
        WARMUP_ENABLED = True   # ← change to True when you want warmup

        if not WARMUP_ENABLED:
            print("------------------------------------------------", flush=True)
            print("  NEXUS FORENSIC BRAIN WARMUP DISABLED (STATIC TOGGLE)", flush=True)
            print("------------------------------------------------", flush=True)
            return

        print("------------------------------------------------", flush=True)
        print("  TRIGGERING NEXUS FORENSIC BRAIN WARMUP...", flush=True)
        print("    (This loads the model into RAM now to avoid lag later)", flush=True)
        print("------------------------------------------------", flush=True)

        try:
            from .ingestion.llm_normalizer import warmup_forensic_brain
            warmup_forensic_brain()
        except Exception as e:
            print(f" [WARMUP SKIPPED] Could not load brain: {e}", flush=True)
