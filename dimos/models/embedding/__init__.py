from dimos.models.embedding.base import Embedding, EmbeddingModel

__all__ = [
    "Embedding",
    "EmbeddingModel",
]

# Optional: CLIP support
try:
    from dimos.models.embedding.clip import CLIPModel  # noqa: F401

    __all__.append("CLIPModel")
except ImportError:
    pass

# Optional: MobileCLIP support
try:
    from dimos.models.embedding.mobileclip import MobileCLIPModel  # noqa: F401

    __all__.append("MobileCLIPModel")
except ImportError:
    pass

# Optional: TorchReID support
try:
    from dimos.models.embedding.treid import TorchReIDModel  # noqa: F401

    __all__.append("TorchReIDModel")
except ImportError:
    pass
