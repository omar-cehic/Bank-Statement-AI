import requests
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

OLLAMA_BASE_URL = os.environ.get('OLLAMA_URL', 'http://localhost:11434')
OLLAMA_URL = OLLAMA_BASE_URL.rstrip('/') + '/api/generate'
OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'llama3')
OLLAMA_TIMEOUT = 10

VALID_CATEGORIES = [
    "Payments",
    "Restaurants",
    "Fast Food",
    "Gas",
    "Groceries",
    "Entertainment",
    "Shopping",
    "Subscriptions",
    "Health",
    "Travel",
    "Other",
    "Uncategorized",
]

CATEGORY_LIST_STR = ", ".join(VALID_CATEGORIES)


def build_prompt(description):
    return (
        f"Categorize this bank transaction into exactly one of these categories. "
        f"You must choose from this list only — do not invent new categories. "
        f"If nothing fits well, choose Other:\n"
        f"{CATEGORY_LIST_STR}\n\n"
        f"Transaction: {description}\n\n"
        f"Reply with only the category name from the list above. "
        f"One word or short phrase only. No explanation."
    )


def categorize_with_ollama(description):
    """
    Send a transaction description to Ollama/llama3 for categorization.

    Args:
        description (str): Transaction description/merchant name

    Returns:
        str: One of the valid category names, or 'Uncategorized' on failure
    """
    if not description or not description.strip():
        return "Uncategorized"

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": build_prompt(description),
        "stream": False,
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=OLLAMA_TIMEOUT)
        response.raise_for_status()

        raw = response.json().get("response", "").strip().strip("\"'.,").strip()

        # Exact match first (case-insensitive)
        for category in VALID_CATEGORIES:
            if category.lower() == raw.lower():
                return category

        # Partial match fallback — model may include filler words
        for category in VALID_CATEGORIES:
            if category.lower() in raw.lower():
                return category

        print(f"  [Ollama] Unexpected response: '{raw}' — defaulting to Uncategorized")
        return "Uncategorized"

    except requests.exceptions.Timeout:
        print(f"  [Ollama] Timed out after {OLLAMA_TIMEOUT}s — defaulting to Uncategorized")
        return "Uncategorized"
    except requests.exceptions.ConnectionError:
        print("  [Ollama] Connection refused — is Ollama running at http://localhost:11434?")
        return "Uncategorized"
    except Exception as e:
        print(f"  [Ollama] Error: {e} — defaulting to Uncategorized")
        return "Uncategorized"


# ── Dashboard AI helpers ──────────────────────────────────────────────────────

def build_summary_prompt(context):
    return (
        f"You are a personal finance assistant. "
        f"Here is a summary of someone's credit card statement:\n\n"
        f"{context}\n\n"
        f"Write 2-3 sentences of insight about their spending patterns. "
        f"Be specific — reference actual dollar amounts and category names from the data. "
        f"Be direct and helpful, not generic."
    )


def build_chat_prompt(context, question):
    return (
        f"You are a personal finance assistant. "
        f"Here is a summary of someone's credit card statement:\n\n"
        f"{context}\n\n"
        f"Answer this question based only on the spending data above:\n"
        f"{question}\n\n"
        f"Be specific — reference actual numbers from the data. "
        f"Keep your answer to 2-3 sentences."
    )


def _call_ollama_freeform(prompt, timeout=30):
    """
    Send a freeform prompt to Ollama and return the raw response string.
    Used by the dashboard summary and chat features.

    Args:
        prompt (str): The full prompt to send
        timeout (int): Request timeout in seconds (default 30 — longer than
                       categorization since responses are more detailed)

    Returns:
        str: The model's response, or an error message string on failure
    """
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
    }
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
        response.raise_for_status()
        return response.json().get("response", "").strip()
    except requests.exceptions.Timeout:
        return "Ollama timed out — try again or check that Ollama is running."
    except requests.exceptions.ConnectionError:
        return "Could not connect to Ollama. Make sure it is running at http://localhost:11434."
    except Exception as e:
        return f"Ollama error: {e}"


def get_spending_summary(context):
    """
    Generate a 2-3 sentence spending insight from the provided context string.

    Args:
        context (str): Formatted spending summary (totals, categories, merchants)

    Returns:
        str: AI-generated insight paragraph, or error message on failure
    """
    return _call_ollama_freeform(build_summary_prompt(context))


def get_chat_response(context, question):
    """
    Answer a user's question about their spending using the provided context.

    Args:
        context (str): Formatted spending summary
        question (str): User's freeform question

    Returns:
        str: AI-generated answer, or error message on failure
    """
    return _call_ollama_freeform(build_chat_prompt(context, question))


def test_ollama_categorizer():
    """Test Ollama categorization with 5 sample uncategorized transactions"""
    print("Ollama LLM Categorizer Test")
    print("=" * 50)
    print(f"Model:   {OLLAMA_MODEL}")
    print(f"URL:     {OLLAMA_URL}")
    print(f"Timeout: {OLLAMA_TIMEOUT}s")
    print()

    test_cases = [
        "ZIPRECRUITER INC SANTA MONICA CA",       # Expected: Subscriptions
        "SQ *NORTHSHORE BARBER CHICAGO IL",        # Expected: Other
        "CITY OF CHICAGO PARKING CHICAGO IL",      # Expected: Other or Travel
        "USPS PO 0543770050 SKOKIE IL",            # Expected: Other
        "EXPEDIA HOTEL BOOKING SEATTLE WA",        # Expected: Travel
    ]

    print("Sending 5 sample uncategorized transactions to llama3:")
    print("-" * 50)

    for i, description in enumerate(test_cases, 1):
        print(f"[{i}/5] {description}")
        category = categorize_with_ollama(description)
        print(f"       -> {category}")
        print()

    print("Test completed.")


if __name__ == "__main__":
    test_ollama_categorizer()
