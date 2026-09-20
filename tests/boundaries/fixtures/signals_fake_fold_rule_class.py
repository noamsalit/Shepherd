# EVASION fixture (C6): a locally declared lookalike, carrying no evidence field
# and no frozen dataclass decorator, used to suppress the vocabulary scan.
class FoldRule:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs


TABLE = (FoldRule(evidence="§SubagentStop"),)
