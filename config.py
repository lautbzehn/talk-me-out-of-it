"""Settings shared by the whole engine. Change the model here and everything follows."""

# Chosen 10.25.2026 from the eval comparison: more reliable than qwen2.5:7b and it can reach Skip,
# at about twice the time per council. qwen2.5:7b is still downloaded as the faster fallback.
MODEL = "qwen2.5:14b"
TEMPERATURE = 0.6  # 0 gives the same answer every time; higher gives more varied voices
MAX_ATTEMPTS = 3  # how many tries the model gets to produce valid output
MAX_TOOL_STEPS = 5  # most model turns allowed while gathering tool results
MAX_TOOL_NUDGES = 2  # times we remind the model to use a required tool

# Safety limits. A small model can get stuck and never stop talking, so every call is capped.
# One tool-gathering turn: tool requests only. Lowered from 400 on 10.25.2026: every 14B reply that hit
# 400 was the same calls repeated in a loop, and a normal step with two calls is about 80 tokens.
MAX_TOOL_TURN_TOKENS = 200
MAX_ANSWER_TOKENS = 800  # the final structured answer (a normal one is around 200)
REQUEST_TIMEOUT_SECONDS = 180  # give up on a single model call after this long (the 14B Judge takes about 64)

# How much text the model can read at once, in tokens (a token is roughly three quarters of a word).
# Ollama runs this model at 4096 by default. A tiebreak round plus the reply can get close to that,
# and an overflow silently drops the start of the conversation: the system prompt with the rules.
CONTEXT_TOKENS = 8192


TOOL_TEMPERATURE = 0.0  # tool arguments need precision, not variety

# The intake check is a yes/no classifier, so it runs cold and short.
INTAKE_TEMPERATURE = 0.0
MAX_INTAKE_TOKENS = 150

# Rounds: opening and rebuttal always run. A tiebreak round runs only when the council is split.
MAX_ROUNDS = 3


def chat_options(max_tokens: int, temperature: float = TEMPERATURE) -> dict:
    """The model settings sent with every call, including the hard cap on reply length."""
    return {"temperature": temperature, "num_predict": max_tokens, "num_ctx": CONTEXT_TOKENS}
