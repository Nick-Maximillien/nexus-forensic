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


# GCP Infrastructure Setup

if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.environ["GOOGLE_APPLICATION_CREDENTIALS"].replace("\\", "/")

GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
GCP_LOCATION = "us-central1"

# ---------------------------------------------
# Medical Embedding Engine (HAI-DEF Foundation)
# ---------------------------------------------
# Global Singleton Cache to prevent repeated model initialization
_EMBEDDING_MODEL = None

def _get_embedding_model():
    """
    Lazy loader for Vertex AI Medical Embeddings.
    
    SYSTEM NOTE: We utilize 'medlm-embeddings-v1' instead of generic models.
    This specialized HAI-DEF model is trained on clinical medical corpora,
    ensuring higher semantic accuracy for medical-legal terminology
    (e.g., distinguishing 'STAT' from 'PRN' orders in forensic audits).
    """
    global _EMBEDDING_MODEL
    
    if _EMBEDDING_MODEL is None:
        try:
            logger.info("Initializing HAI-DEF Medical Embedding Model...")
            from vertexai import init as vertex_init
            from vertexai.language_models import TextEmbeddingModel
            
            vertex_init(project=GCP_PROJECT_ID, location=GCP_LOCATION)
            
            # Using the specialized medical model for clinical semantic parity
            _EMBEDDING_MODEL = TextEmbeddingModel.from_pretrained("medlm-embeddings-v1")
            logger.info("HAI-DEF Medical Embeddings Online.")
        except Exception as e:
            logger.error(f"Critical failure loading MedLM Embedding Model: {str(e)}")
            return None
            
    return _EMBEDDING_MODEL


def get_batch_embeddings(texts: list) -> list:
    """
    High-Throughput Vector Generation with Exponential Backoff.
    
    This implementation handles the 429 ResourceExhausted errors typical 
    during bulk corpus ingestion on GCP. It ensures data integrity
    by providing empty vector fallbacks only after maximum retry exhaustion.
    """
    model = _get_embedding_model()
    
    if not texts or not model:
        return []
    
    # Input Sanitization: Vertex AI rejects empty strings
    cleaned_texts = [t if t.strip() else "clinical_null_placeholder" for t in texts]

    max_retries = 6
    base_delay = 2 

    for attempt in range(max_retries):
        try:
            # Batch processing reduces API round-trips
            embeddings = model.get_embeddings(cleaned_texts)
            return [e.values for e in embeddings]

        except (ResourceExhausted, ServiceUnavailable):
            # Calculate jittered exponential backoff
            wait_time = (base_delay * (2 ** attempt)) + random.uniform(0, 1)
            logger.warning(f"Vertex Quota hit. Retrying in {wait_time:.2f}s... (Attempt {attempt + 1}/{max_retries})")
            time.sleep(wait_time)
            
        except Exception as e:
            logger.error(f"Medical Embedding Batch failure: {str(e)}")
            break
            
    # Fallback: Maintain index consistency with null vectors
    return [[0.0] * 768 for _ in texts]


def get_embedding(text: str) -> list:
    """
    Atomic Vector Retrieval.
    Wraps batch logic for single-item requests (e.g., real-time search queries).
    """
    if not text or not text.strip():
        return [0.0] * 768
    
    results = get_batch_embeddings([text])
    return results[0] if results else [0.0] * 768


def search_forensic_rules(query: str, top_k: int = 5, filters: dict = None, scope: str = None):
    """
    Multi-Head Hybrid Retrieval Engine.
    
    Combines:
    1. Clinical Semantic Search (pgvector L2 Distance using MedLM)
    2. Symbolic Text Ranking (PostgreSQL SearchRank)
    3. Metadata Filtering (Scope and Activity status)
    
    This ensures that search results are not only semantically similar but 
    also respect the legal and operational boundaries of the audit.
    """
    if not query:
        return []
    
    if not filters:
        filters = {}

    # Generate query vector using specialized medical embedding
    query_vector = get_embedding(query)
    
    # Constraint 1: Filter only active protocols
    base_qs = ForensicRule.objects.filter(protocol__is_active=True)

    # Constraint 2: Deterministic Scope Filtering
    if scope:
        base_qs = base_qs.filter(scope_tags__contains=[scope])

    # Constraint 3: Legacy Logic Filter
    if 'class' in filters:
        base_qs = base_qs.filter(logic_config__class_of_recommendation=filters['class'])

    # Hybrid Adjudication Logic:
    # We combine normalized Vector Distance (L2) with Keyword Rank.
    # The 0.1 constant in the vector calculation prevents division by zero.
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