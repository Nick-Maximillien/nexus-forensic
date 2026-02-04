import time
from apps.forensic_corpus.models import ForensicRule, RuleEmbedding, ClinicalProtocol
from apps.forensic_rag.utils import get_embedding

# 1. Target the Protocol with missing vectors
title = "2023 ESC Guidelines for the management of acute coronary syndromes"
protocol = ClinicalProtocol.objects.get(title=title)

# 2. Find rules that have NO embedding
missing_vectors = ForensicRule.objects.filter(protocol=protocol, embedding__isnull=True)
count = missing_vectors.count()

print(f" Found {count} rules missing vectors. Starting generation...")

# 3. Loop and Generate
for i, rule in enumerate(missing_vectors):
    try:
        print(f"[{i+1}/{count}] Generating vector for {rule.rule_code}...")
        
        # Call Vertex AI to get the vector (768 dimensions)
        vector_data = get_embedding(rule.text_description)
        
        # Save to Database
        RuleEmbedding.objects.create(rule=rule, vector=vector_data)
        
        # Sleep to avoid hitting Vertex AI rate limits (Quota safety)
        time.sleep(0.5) 
        
    except Exception as e:
        print(f" Failed on {rule.rule_code}: {e}")

print(" Repair Complete. The Brain is now online.")