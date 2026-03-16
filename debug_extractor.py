from ollama import Client

client = Client()

abstract = """We present a transformer-based inpainting method for real-time 
3D streaming in surgical environments. Our approach leverages attention 
mechanisms to reconstruct occluded regions in laparoscopic video feeds."""

prompt = f"""Extract 3-5 factual claims from this abstract.
Return ONLY a JSON array like this exact format:
[{{"text": "claim here", "confidence": 0.9, "topic_tags": ["tag"]}}]

Abstract:
{abstract}

JSON:"""

print("=== RAW OUTPUT phi3:mini ===")
response = client.chat(
    model="phi3:mini",
    messages=[{"role": "user", "content": prompt}],
    options={"temperature": 0.1}
)
print(repr(response.message.content))