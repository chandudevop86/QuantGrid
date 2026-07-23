import os
import requests


class OllamaLLM:

    def __init__(self):
        self.url = os.getenv(
            "OLLAMA_BASE_URL",
            "http://localhost:11434"
        )
        self.model = os.getenv(
            "OLLAMA_MODEL",
            "qwen2.5-coder:7b"
        )

    def generate(self, prompt):
        response = requests.post(
            f"{self.url}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
            },
            timeout=300,
        )

        response.raise_for_status()

        return response.json()["response"]


if __name__ == "__main__":
    llm = OllamaLLM()

    print("Testing Ollama...")
    print("-" * 40)

    result = llm.generate("Say hello in one sentence.")

    print(result)