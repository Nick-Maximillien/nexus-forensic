import os
import logging
import time
import random
from pathlib import Path
from django.db import models
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable
from pgvector.django import L2Distance 

from apps.forensic_corpus.models import ForensicRule 

logger = logging.getLogger(__name__)

# ----------------------------
#  Setup GCP Credentials
# ----------------------------

if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.environ["GOOGLE_APPLICATION_CREDENTIALS"].replace("\\", "/")

# ----------------------------
#  Vertex AI Initialization (Lazy Loaded)
# ----------------------------
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
GCP_LOCATION = "us-central1"

# Global Singleton Cache
_EMBEDDING_MODEL = None

def _get_embedding_model():
    """
    Lazy loader for Vertex AI.
    Prevents 'import vertexai' from blocking the server boot process.
    """
    global _EMBEDDING_MODEL
    
    if _EMBEDDING_MODEL is None:
        try:
            logger.info("🔌 Connecting to Vertex AI (Embeddings)...")
            # Heavy imports moved INSIDE the function
            from vertexai import init as vertex_init
            from vertexai.language_models import TextEmbeddingModel
            
            vertex_init(project=GCP_PROJECT_ID, location=GCP_LOCATION)
            _EMBEDDING_MODEL = TextEmbeddingModel.from_pretrained("text-embedding-004")
            logger.info("✅ Vertex AI Embeddings Online.")
        except Exception as e:
            logger.error(f"Failed to load TextEmbeddingModel: {e}")
            return None
            
    return _EMBEDDING_MODEL


def get_batch_embeddings(texts: list) -> list:
    """
    Generates embeddings for a list of texts with Exponential Backoff.
    Crucial for handling 429 Quota errors during bulk ingestion.
    """
    # Initialize Model (Lazy)
    model = _get_embedding_model()
    
    if not texts or not model: return []
    
    # Clean inputs (Vertex AI fails on empty strings)
    cleaned_texts = [t if t.strip() else "empty_placeholder" for t in texts]

    max_retries = 6
    base_delay = 2 

    for attempt in range(max_retries):
        try:
            # Vertex AI accepts a list of texts
            embeddings = model.get_embeddings(cleaned_texts)
            return [e.values for e in embeddings]

        except (ResourceExhausted, ServiceUnavailable) as e:
            wait_time = (base_delay * (2 ** attempt)) + random.uniform(0, 1)
            logger.warning(f"Quota exceeded. Retrying in {wait_time:.2f}s... (Attempt {attempt + 1}/{max_retries})")
            time.sleep(wait_time)
            
        except Exception as e:
            logger.error(f"Batch embedding failed: {e}")
            break
            
    # Fallback: Return empty vectors if all retries fail
    return [[0.0] * 768 for _ in texts]


def get_embedding(text: str) -> list:
    """
    Wrapper for single text that uses the robust retry logic.
    """
    if not text or not text.strip(): return [0.0] * 768
    
    # Reuse the batch logic to handle quotas/retries automatically
    results = get_batch_embeddings([text])
    return results[0] if results else [0.0] * 768


def search_forensic_rules(query: str, top_k: int = 5, filters: dict = None, scope: str = None):
    """
    Performs a Hybrid Semantic Search (Vector + Keyword).
    [UPGRADE] Added 'scope' parameter to align with System Grade filtering.
    """
    if not query: return []
    if not filters: filters = {}

    query_vector = get_embedding(query)
    
    # Base Query
    base_qs = ForensicRule.objects.filter(protocol__is_active=True)

    # 1. Filter by Class (Legacy support)
    if 'class' in filters:
        base_qs = base_qs.filter(logic_config__class_of_recommendation=filters['class'])

    # 2.  Filter by Scope (Deterministic)
    if scope:
        base_qs = base_qs.filter(scope_tags__contains=[scope])

    # 3. Hybrid Scoring
    results = base_qs.annotate(
        vector_dist=L2Distance('embedding__vector', query_vector),
        rank=SearchRank(
            SearchVector('rule_code', 'text_description'), 
            SearchQuery(query)
        )
    ).annotate(
        hybrid_score=models.F('rank') + (1.0 / (models.F('vector_dist') + 0.1))
    ).order_by('-hybrid_score')[:top_k].select_related('protocol')

    return results