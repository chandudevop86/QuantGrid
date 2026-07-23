import os

from models.openai_llm import OpenAILLM
from models.claude_llm import ClaudeLLM
from models.ollama_llm import OllamaLLM


def get_llm():

    provider = os.getenv(
        "LLM_PROVIDER",
        "ollama"
    )

    if provider == "openai":

        return OpenAILLM(
            os.getenv("OPENAI_API_KEY")
        )

    if provider == "claude":

        return ClaudeLLM(
            os.getenv("ANTHROPIC_API_KEY")
        )

    return OllamaLLM()