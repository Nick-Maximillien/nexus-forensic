import re
from datetime import datetime
from django.db import models
from django.db.models import F, Q
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from pgvector.django import L2Distance

from apps.forensic_corpus.models import ForensicRule, ClinicalProtocol
from apps.forensic_domain.contract import ForensicAuditPlan

class ForensicRAG:
    """
    Wire 2: The Multi-Head Constrained Retriever.
    Fetches the 'Law' (Protocol) that applies to the 'Crime' (Claim).
    Upgraded: Scope-Aware partitioning (Facility vs Clinical).
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

        if plan.specialty_context and plan.specialty_context.lower() != 'auto':
            filters['specialty__iexact'] = plan.specialty_context

        active_protocols = ClinicalProtocol.objects.filter(**filters)

        # 2. BASE QUERY (Select Related for Performance)
        base_qs = ForensicRule.objects.filter(
            protocol__in=active_protocols
        ).select_related('protocol', 'embedding')

        # Deterministic Facility Level Filter
        if plan.facility_level:
            base_qs = base_qs.filter(applicable_facility_levels__contains=[plan.facility_level])

        # DETERMINISTIC SCOPE FILTER
        if plan.audit_scope:
            base_qs = base_qs.filter(scope_tags__contains=[plan.audit_scope])

        # DEMOGRAPHIC FILTER (Prevent Pediatric/Adult Mismatch)
        effective_age = plan.patient_age
        if effective_age is None and query_text:
            yr_match = re.search(r'(\d+)\s*[-]?\s*y(?:ea)?rs?\s*old', query_text, re.IGNORECASE)
            if yr_match:
                effective_age = int(yr_match.group(1))
            elif re.search(r'(\d+)\s*[-]?\s*m(?:on)?ths?\s*old', query_text, re.IGNORECASE):
                effective_age = 0 

        if effective_age is not None:
            if effective_age >= 18:
                base_qs = base_qs.exclude(scope_tags__contains=['pediatric'])
                base_qs = base_qs.exclude(protocol__specialty='pediatrics')
            else:
                base_qs = base_qs.exclude(scope_tags__contains=['adult'])

        # 3. SCOPE-CONDITIONAL MULTI-HEAD RETRIEVAL
        # Multi-Head split is ONLY enforced for Clinical Audits.
        if plan.audit_scope == 'clinical':
            # HEAD A: The Clinical Truth (NASCOP, Handbooks, Clinical Protocols etc)
            clinical_filters = Q(protocol__issuing_body__icontains="NASCOP") | \
                              Q(protocol__title__icontains="Handbook") | \
                              Q(protocol__title__icontains="Guidelines")
            clinical_qs = base_qs.filter(clinical_filters)

            # HEAD B: The Certification Stamp (KQMH Core Standards / Quality Model)
            cert_filters = Q(protocol__title__icontains="KQMH") | \
                          Q(protocol__title__icontains="Quality Model") | \
                          Q(protocol__title__icontains="Core Standards")
            cert_qs = base_qs.filter(cert_filters)

            # Helper to apply Hybrid Scoring Engine to a specific head
            def get_scored_results(qs, limit):
                if query_text:
                    return qs.annotate(
                        vector_dist=L2Distance('embedding__vector', query_embedding),
                        rank=SearchRank(
                            SearchVector('rule_code', 'text_description'), 
                            SearchQuery(query_text)
                        )
                    ).annotate(
                        hybrid_score=F('rank') + (1.0 / (F('vector_dist') + 0.1))
                    ).order_by('-hybrid_score')[:limit]
                else:
                    return qs.annotate(
                        vector_dist=L2Distance('embedding__vector', query_embedding)
                    ).order_by('vector_dist')[:limit]

            # EXECUTE FUSION (Force a 60/40 Split for Clinical cases)
            head_a_limit = 6
            head_b_limit = 4
            return list(get_scored_results(clinical_qs, head_a_limit)) + list(get_scored_results(cert_qs, head_b_limit))

        else:
            # IoT / Infrastructure / Research Mode: perform targeted top_k search
            # Hard Exclusion of any clinical/identifiers for non-clinical scopes
            base_qs = base_qs.exclude(
                Q(rule_code__icontains="HIV") |
                Q(protocol__issuing_body__icontains="NASCOP") | 
                Q(protocol__title__icontains="Handbook") | 
                Q(protocol__title__icontains="HIV")
            )

            if query_text:
                candidates = base_qs.annotate(
                    vector_dist=L2Distance('embedding__vector', query_embedding),
                    rank=SearchRank(
                        SearchVector('rule_code', 'text_description'), 
                        SearchQuery(query_text)
                    )
                ).annotate(
                    hybrid_score=F('rank') + (1.0 / (F('vector_dist') + 0.1))
                ).order_by('-hybrid_score')
            else:
                candidates = base_qs.annotate(
                    vector_dist=L2Distance('embedding__vector', query_embedding)
                ).order_by('vector_dist')

            return list(candidates[:top_k])