from models.llm_factory import get_llm


class LLMAuditAgent:

    def __init__(self):

        self.client = get_llm()

    def analyze_finding(
        self,
        finding,
        code
    ):

        prompt = ...

        return self.client.generate(prompt)
