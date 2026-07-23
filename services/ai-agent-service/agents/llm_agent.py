from models.llm_factory import get_llm


class LLMAuditAgent:

    def __init__(self):
        self.client = get_llm()

    def analyze_finding(self, finding, code):

        prompt = self._build_prompt(finding, code)

        return self.client.generate(prompt)

    def _build_prompt(self, finding, code):
        return f"""
Analyze this audit finding.

Finding:
{finding}

Code:
{code}

Provide:
- Root cause
- Risk
- Fix
- Example (if applicable)
"""