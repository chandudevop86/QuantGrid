from openai import OpenAI
from models.base_llm import BaseLLM


class OpenAILLM(BaseLLM):

    def __init__(self, api_key):

        self.client = OpenAI(api_key=api_key)

    def generate(self, prompt):

        response = self.client.chat.completions.create(
            model="gpt-5.5",
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        return response.choices[0].message.content
    import anthropic
from models.base_llm import BaseLLM


class ClaudeLLM(BaseLLM):

    def __init__(self, api_key):

        self.client = anthropic.Anthropic(
            api_key=api_key
        )

    def generate(self, prompt):

        response = self.client.messages.create(
            model="claude-sonnet-4",
            max_tokens=2000,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        return response.content[0].text
    import requests
from models.base_llm import BaseLLM


class OllamaLLM(BaseLLM):

    def __init__(
        self,
        model="llama3"
    ):

        self.model = model

    def generate(self, prompt):

        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False
            }
        )

        return response.json()["response"]