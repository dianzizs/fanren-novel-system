"""Target profile definitions for retrieval.

Each target has:
- text_field: Which field to use for text matching
- id_field: Which field is the document ID
- exact_alias_fields: Fields to check for exact alias matches
"""

TARGET_PROFILES = {
    "chapter_chunks": {
        "text_field": "text",
        "id_field": "id",
        "exact_alias_fields": [],
    },
    "event_timeline": {
        "text_field": "text",
        "id_field": "event_id",
        "exact_alias_fields": [],
    },
    "character_card": {
        "text_field": "retrieval_text",
        "id_field": "id",
        "exact_alias_fields": ["canonical_name", "aliases", "titles"],
    },
}
