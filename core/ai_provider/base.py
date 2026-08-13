#
# /chizu/core/ai_provider/base.py 
#
class BaseProvider:
    def __init__(self, api_key):
        self.api_key = api_key

    def chat(self, messages, config):
        raise NotImplementedError

    def stream(self, messages, config):
        raise NotImplementedError