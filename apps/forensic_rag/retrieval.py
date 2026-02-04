from datetime import datetime
from django.db import models
from django.db.models import F
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from pgvector.django import L2Distance

from apps.forensic_corpus.models import ForensicRule, ClinicalProtocol
from apps.forensic_domain.contract import ForensicAuditPlan

class ForensicRAG:
    """
    Wire 2: The Constrained Retriever.
    Fetches the 'Law' (Protocol) that applies to the 'Crime' (Claim).
    Upgraded to support Deterministic Scope Filtering.
    """

    @staticmethod
    def retrieve_applicable_rules(
        query_embedding: list, 
        plan: ForensicAuditPlan,
        query_text: str = None,  # Required for Hybrid Keyword Search
        top_k=10
    ) -> list[ForensicRule]:
        
        try:
            event_date = datetime.fromisoformat(plan.event_timestamp).date()
        except (ValueError, TypeError):
            event_date = datetime.now().date()

        # 1. PROTOCOL FILTER (Dynamic Context)
        filters = {
            'is_active': True,
            'valid_from__lte': event_date
        }

        # Make specialty filter optional to allow Universal Search via Vector
        if plan.specialty_context and plan.specialty_context.lower() != 'auto':
            filters['specialty__iexact'] = plan.specialty_context

        active_protocols = ClinicalProtocol.objects.filter(**filters)

        # 2. BASE QUERY (Select Related for Performance)
        base_qs = ForensicRule.objects.filter(
            protocol__in=active_protocols
        ).select_related('protocol', 'embedding')

        # DETERMINISTIC SCOPE FILTER ---
        # Instead of keyword guessing, we strictly filter by the 'scope_tags'
        # array populated during ingestion (e.g., 'clinical', 'facility').
        if plan.audit_scope:
            base_qs = base_qs.filter(scope_tags__contains=[plan.audit_scope])

        # 3. HYBRID SCORING ENGINE
        if query_text:
            candidates = base_qs.annotate(
                # A. Vector Distance (Lower is better)
                vector_dist=L2Distance('embedding__vector', query_embedding),
                
                # B. Keyword Rank (Higher is better)
                rank=SearchRank(
                    SearchVector('rule_code', 'text_description'), 
                    SearchQuery(query_text)
                )
            ).annotate(
                # Normalize: Rank + (1 / (Distance + 0.1))
                # Boosts exact keyword matches significantly over fuzzy vector matches
                hybrid_score=F('rank') + (1.0 / (F('vector_dist') + 0.1))
            ).order_by('-hybrid_score')
            
        else:
            # Fallback: Pure Vector Search
            candidates = base_qs.annotate(
                vector_dist=L2Distance('embedding__vector', query_embedding)
            ).order_by('vector_dist')

        # 4. EXECUTE AND RETURN
        return list(candidates[:top_k])