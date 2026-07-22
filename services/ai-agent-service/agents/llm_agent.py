from llm.client import LLMClient


class LLMAuditAgent:

    def __init__(self):
        self.client = LLMClient()


    def analyze_finding(
        self,
        finding,
        code
    ):

        prompt = f"""

You are a senior software architect.

Analyze this audit finding.

Finding:
{finding}

Code:
{code}

Return:

1. Is this a real issue?
2. Severity
3. Explanation
4. Recommended fix

"""

        return self.client.complete(prompt)