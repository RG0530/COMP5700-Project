## zero-shot

```text
Extract Kubernetes security KDEs from both documents. A KDE can map to multiple requirements and should be normalized to snake_case names. Return ONLY valid JSON. Do not use markdown fences. Use exactly this shape: {"element1":{"name":"...","requirements":["...","..."]},"element2":{"name":"...","requirements":["..."]}}. If no KDEs are found, return {}.

Document A (<doc1_name>) candidate requirements:
<doc1_text>

Document B (<doc2_name>) candidate requirements:
<doc2_text>
```

## few-shot

```text
You extract KDEs from requirements documents.
Example Input: 2.1.1 Enable audit Logs; 4.4.2 Consider external secret storage.
Example Output: {"element1":{"name":"audit_logging","requirements":["Enable audit Logs"]},"element2":{"name":"external_secret_storage","requirements":["Consider external secret storage"]}}

Return ONLY valid JSON. Do not use markdown fences. Use exactly this shape: {"element1":{"name":"...","requirements":["...","..."]},"element2":{"name":"...","requirements":["..."]}}. If no KDEs are found, return {}.

Document A (<doc1_name>) candidate requirements:
<doc1_text>

Document B (<doc2_name>) candidate requirements:
<doc2_text>
```

## chain-of-thought

```text
Think silently and extract KDEs that represent configuration and policy controls. Do not output explanation. Return ONLY valid JSON. Do not use markdown fences. Use exactly this shape: {"element1":{"name":"...","requirements":["...","..."]},"element2":{"name":"...","requirements":["..."]}}. If no KDEs are found, return {}.

Document A (<doc1_name>) candidate requirements:
<doc1_text>

Document B (<doc2_name>) candidate requirements:
<doc2_text>
```
