from openai import OpenAI
import os


client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)


def ask_llm(
    prompt: str,
    model: str | None = None
):

    response = client.chat.completions.create(
        model=model or os.getenv(
            "LLM_MODEL",
            "gpt-5.5-mini"
        ),
        messages=[
            {
                "role": "system",
                "content":
                "You are QuantGrid AI Engineering Assistant."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    return response.choices[0].message.content