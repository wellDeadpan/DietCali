class CrossEncoderReranker:
    """sentence-transformers CrossEncoder scoring (query, description) pairs"""
    name = "cross_encoder"

    def __init__(self, model_name: str, model=None):
        self.version = model_name
        if model is None:
            from sentence_transformers import CrossEncoder
            model = CrossEncoder(model_name)
        self.model = model

    def score(self, query: str, docs: list) -> list:
        return [float(s) for s in self.model.predict([(query, d) for d in docs])]
