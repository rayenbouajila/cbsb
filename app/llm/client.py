"""
app/llm/client.py

Wrapper minimal autour du SDK Anthropic. Une seule fonction publique pour
garder le reste du code decouple du SDK (facilite les tests / un futur
changement de provider).

Variables d'environnement attendues (.env) :
    ANTHROPIC_API_KEY   - obligatoire
    ANTHROPIC_MODEL      - optionnel, defaut "claude-sonnet-5"
"""

from __future__ import annotations

import os

from anthropic import Anthropic

DEFAULT_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")

_client: Anthropic | None = None


def get_anthropic_client() -> Anthropic:
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY introuvable. Ajoutez-la dans le fichier .env "
                "(meme fichier que DATABASE_URL)."
            )
        _client = Anthropic(api_key=api_key)
    return _client


def call_claude(system_prompt: str, user_prompt: str, max_tokens: int = 1500) -> str:
    """Appelle Claude et retourne le texte brut de la reponse (premier bloc
    texte). Leve une exception en cas d'erreur reseau/API - a charge de
    l'appelant (extractor.py) de catcher."""
    client = get_anthropic_client()
    response = client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    text_blocks = [block.text for block in response.content if getattr(block, "type", None) == "text"]
    return "\n".join(text_blocks).strip()
