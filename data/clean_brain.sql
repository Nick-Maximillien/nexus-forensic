SET standard_conforming_strings = on;
COPY public.forensic_agent_audittask (id, case_id, claim_payload, query_intent, status, started_at, completed_at, verdict_json, retrieved_protocols, final_report, agent_trace, notification_sent, notification_channel) FROM stdin;

COPY public.forensic_corpus_clinicalprotocol (id, title, version, issuing_body, specialty, valid_from, valid_until, is_active, min_facility_level) FROM stdin;

COPY public.forensic_corpus_forensicrule (id, rule_code, rule_type, text_description, logic_config, scope_tags, intent_tags, search_vector, created_at, protocol_id, applicable_facility_levels) FROM stdin;

COPY public.forensic_corpus_ruleembedding (id, vector, rule_id) FROM stdin;

