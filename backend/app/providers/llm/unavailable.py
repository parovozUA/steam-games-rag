from app.providers.llm.errors import FailureCategory, ProviderFailure


class UnavailableLLMAdapter:
    def __init__(self, name: str, model: str):
        self.name = name
        self.model = model

    async def generate_structured(self, **kwargs):
        raise ProviderFailure(f"{self.name} API key is not configured", FailureCategory.AUTH, False)
