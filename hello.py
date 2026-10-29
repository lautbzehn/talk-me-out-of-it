"""Phase 1: the smallest possible call to the local model.

Run with:  .venv/bin/python hello.py
"""

import ollama

from config import MODEL

response = ollama.chat(
    model=MODEL,
    messages=[
        {"role": "user", "content": "In one sentence, talk me out of buying a $600 gadget."}
    ],
)

print(response.message.content)
