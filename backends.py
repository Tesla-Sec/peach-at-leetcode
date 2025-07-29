class BackendBase:
    def chat_completion(self, messages, model, max_tokens):
        raise NotImplementedError

    def vision_completion(self, messages, model, max_tokens, detail):
        raise NotImplementedError

    def transcribe_audio(self, file_path, model):
        raise NotImplementedError

class OpenAIBackend(BackendBase):
    def __init__(self, api_key):
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key) if api_key else None

    def chat_completion(self, messages, model, max_tokens):
        if not self.client:
            raise RuntimeError("OpenAI client not initialized")
        resp = self.client.chat.completions.create(model=model, messages=messages, max_tokens=max_tokens)
        return resp.choices[0].message.content

    def vision_completion(self, messages, model, max_tokens, detail):
        if not self.client:
            raise RuntimeError("OpenAI client not initialized")
        resp = self.client.chat.completions.create(model=model, messages=messages, max_tokens=max_tokens)
        return resp.choices[0].message.content

    def transcribe_audio(self, file_path, model):
        if not self.client:
            raise RuntimeError("OpenAI client not initialized")
        with open(file_path, 'rb') as audio_file:
            trans_resp = self.client.audio.transcriptions.create(model=model, file=audio_file)
        return trans_resp.text

class BackendFactory:
    @staticmethod
    def create(backend_name, api_key=None):
        name = (backend_name or 'openai').lower()
        if name == 'openai':
            return OpenAIBackend(api_key)
        # Placeholder for other backends
        return OpenAIBackend(api_key)
