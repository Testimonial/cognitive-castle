"""
Cognitive Castle configuration system.

Priority: env vars > config file (~/.castle/config.json) > defaults
"""

import json
import os
import re
from pathlib import Path


# ── Input validation ──────────────────────────────────────────────────────────
# Shared sanitizers for wing/room/entity names. Prevents path traversal,
# excessively long strings, and special characters that could cause issues
# in file paths, SQLite, or LanceDB metadata.

MAX_NAME_LENGTH = 128
_SAFE_NAME_RE = re.compile(r"^(?:[^\W_]|[^\W_][\w .'-]{0,126}[^\W_])$")


def normalize_wing_name(name: str) -> str:
    """Lower-case + collapse separators (`-`, ` `) to `_` for wing slugs.

    The same rule is applied by ``init`` when persisting `topics_by_wing`
    and when writing `castle.yaml`, so the miner's lookup matches at
    mine time regardless of the source dirname.
    """
    return name.lower().replace(" ", "_").replace("-", "_")


def sanitize_name(value: str, field_name: str = "name") -> str:
    """Validate and sanitize a wing/room/entity name.

    Raises ValueError if the name is invalid.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")

    value = value.strip()

    if len(value) > MAX_NAME_LENGTH:
        raise ValueError(f"{field_name} exceeds maximum length of {MAX_NAME_LENGTH} characters")

    # Block path traversal
    if ".." in value or "/" in value or "\\" in value:
        raise ValueError(f"{field_name} contains invalid path characters")

    # Block null bytes
    if "\x00" in value:
        raise ValueError(f"{field_name} contains null bytes")

    # Enforce safe character set
    if not _SAFE_NAME_RE.match(value):
        raise ValueError(f"{field_name} contains invalid characters")

    return value


def sanitize_kg_value(value: str, field_name: str = "value") -> str:
    """Validate a knowledge-graph entity name (subject or object).

    More permissive than sanitize_name — allows punctuation like commas,
    colons, and parentheses that are common in natural-language KG values.
    Only blocks null bytes and over-length strings.

    Not used for wing/room names (which have filesystem constraints) or
    predicates (which should be simple relationship identifiers).
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")

    value = value.strip()

    if len(value) > MAX_NAME_LENGTH:
        raise ValueError(f"{field_name} exceeds maximum length of {MAX_NAME_LENGTH} characters")

    if "\x00" in value:
        raise ValueError(f"{field_name} contains null bytes")

    return value


def sanitize_content(value: str, max_length: int = 100_000) -> str:
    """Validate drawer/diary content length."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("content must be a non-empty string")
    if len(value) > max_length:
        raise ValueError(f"content exceeds maximum length of {max_length} characters")
    if "\x00" in value:
        raise ValueError("content contains null bytes")
    return value


DEFAULT_PALACE_PATH = os.path.expanduser("~/.castle/palace")
DEFAULT_COLLECTION_NAME = "castle_drawers"

DEFAULT_TOPIC_WINGS = [
    "emotions",
    "consciousness",
    "memory",
    "technical",
    "identity",
    "family",
    "creative",
]

DEFAULT_HALL_KEYWORDS = {
    "emotions": [
        "scared",
        "afraid",
        "worried",
        "happy",
        "sad",
        "love",
        "hate",
        "feel",
        "cry",
        "tears",
    ],
    "consciousness": [
        "consciousness",
        "conscious",
        "aware",
        "real",
        "genuine",
        "soul",
        "exist",
        "alive",
    ],
    "memory": ["memory", "remember", "forget", "recall", "archive", "palace", "store"],
    "technical": [
        "code",
        "python",
        "script",
        "bug",
        "error",
        "function",
        "api",
        "database",
        "server",
    ],
    "identity": ["identity", "name", "who am i", "persona", "self"],
    "family": ["family", "kids", "children", "daughter", "son", "parent", "mother", "father"],
    "creative": ["game", "gameplay", "player", "app", "design", "art", "music", "story"],
}


class CognitiveCastleConfig:
    """Configuration manager for Cognitive Castle.

    Load order: env vars > config file > defaults.
    """

    def __init__(self, config_dir=None):
        """Initialize config.

        Args:
            config_dir: Override config directory (useful for testing).
                        Defaults to ~/.castle.
        """
        self._config_dir = Path(config_dir) if config_dir else Path(os.path.expanduser("~/.castle"))
        self._config_file = self._config_dir / "config.json"
        self._people_map_file = self._config_dir / "people_map.json"
        self._file_config = {}

        if self._config_file.exists():
            try:
                with open(self._config_file, "r") as f:
                    self._file_config = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._file_config = {}

    @property
    def palace_path(self):
        """Path to the memory palace data directory."""
        env_val = os.environ.get("CASTLE_PALACE_PATH") or os.environ.get("MEMPAL_PALACE_PATH")
        if env_val:
            # Normalize: expand ~ and collapse .. to match the CLI --palace
            # code path (mcp_server.py:62) and prevent surprise redirection
            # when the env var contains unresolved components.
            return os.path.abspath(os.path.expanduser(env_val))
        return self._file_config.get("palace_path", DEFAULT_PALACE_PATH)

    @property
    def collection_name(self):
        """LanceDB collection (table) name."""
        return self._file_config.get("collection_name", DEFAULT_COLLECTION_NAME)

    @property
    def people_map(self):
        """Mapping of name variants to canonical names."""
        if self._people_map_file.exists():
            try:
                with open(self._people_map_file, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return self._file_config.get("people_map", {})

    @property
    def topic_wings(self):
        """List of topic wing names."""
        return self._file_config.get("topic_wings", DEFAULT_TOPIC_WINGS)

    @property
    def hall_keywords(self):
        """Mapping of hall names to keyword lists."""
        return self._file_config.get("hall_keywords", DEFAULT_HALL_KEYWORDS)

    @property
    def entity_languages(self):
        """Languages whose entity-detection patterns should be applied.

        Reads from env var ``CASTLE_ENTITY_LANGUAGES`` (comma-separated)
        first, then the ``entity_languages`` field in ``config.json``,
        defaulting to ``["en"]``.
        """
        env_val = os.environ.get("CASTLE_ENTITY_LANGUAGES") or os.environ.get(
            "MEMPAL_ENTITY_LANGUAGES"
        )
        if env_val:
            return [s.strip() for s in env_val.split(",") if s.strip()] or ["en"]
        cfg = self._file_config.get("entity_languages")
        if isinstance(cfg, list) and cfg:
            return [str(s) for s in cfg]
        return ["en"]

    def set_entity_languages(self, languages):
        """Persist the entity-detection language list to ``config.json``."""
        normalized = [s.strip() for s in languages if s and s.strip()]
        if not normalized:
            normalized = ["en"]
        self._file_config["entity_languages"] = normalized
        self._config_dir.mkdir(parents=True, exist_ok=True)
        try:
            with open(self._config_file, "w", encoding="utf-8") as f:
                json.dump(self._file_config, f, indent=2, ensure_ascii=False)
        except OSError:
            pass
        try:
            self._config_file.chmod(0o600)
        except (OSError, NotImplementedError):
            pass
        return normalized

    @property
    def embedding_device(self):
        """Hardware device for the ONNX embedding model.

        Values: ``"auto"`` (default), ``"cpu"``, ``"cuda"``, ``"coreml"``,
        ``"dml"``. Read from env ``CASTLE_EMBEDDING_DEVICE`` first, then
        ``embedding_device`` in ``config.json``, then ``"auto"``.

        ``auto`` resolves to the first available accelerator at runtime via
        :mod:`cognitive_castle.embedding`; requesting an unavailable accelerator
        logs a warning and falls back to CPU.
        """
        env_val = os.environ.get("CASTLE_EMBEDDING_DEVICE")
        if env_val:
            return env_val.strip().lower()
        return str(self._file_config.get("embedding_device", "auto")).strip().lower()

    @property
    def topic_tunnel_min_count(self):
        """Minimum number of overlapping confirmed topics required to create
        a cross-wing tunnel between two wings.

        Default is ``1`` — any single shared topic produces a tunnel. Bump
        to ``2+`` if your projects share lots of common-tech labels (Python,
        Docker, Git) and you want only meaningfully overlapping wings to
        link. Reads ``CASTLE_TOPIC_TUNNEL_MIN_COUNT`` env first, then the
        config-file value, then ``1``.
        """
        env_val = os.environ.get("CASTLE_TOPIC_TUNNEL_MIN_COUNT")
        if env_val:
            try:
                parsed = int(env_val)
                if parsed >= 1:
                    return parsed
            except ValueError:
                pass
        cfg_val = self._file_config.get("topic_tunnel_min_count")
        try:
            parsed = int(cfg_val) if cfg_val is not None else 1
        except (TypeError, ValueError):
            parsed = 1
        return max(1, parsed)

    @property
    def hook_silent_save(self):
        """Whether the stop hook saves directly (True) or blocks for MCP calls (False)."""
        return self._file_config.get("hooks", {}).get("silent_save", True)

    @property
    def hook_desktop_toast(self):
        """Whether the stop hook shows a desktop notification via notify-send."""
        return self._file_config.get("hooks", {}).get("desktop_toast", False)

    # ── Retrieval upgrade config ──────────────────────────────────────────

    @property
    def embedder_model(self):
        """Name of the embedder model to use.

        Default: ``"BAAI/bge-m3"`` (1024-dimensional, multilingual, strong MTEB
        retrieval performance). Reads from ``CASTLE_EMBEDDER_MODEL`` env var
        first, then config file, then the default.
        """
        env_val = os.environ.get("CASTLE_EMBEDDER_MODEL")
        if env_val:
            return env_val.strip()
        return str(
            self._file_config.get(
                "embedder_model",
                "BAAI/bge-m3",
            )
        ).strip()

    @property
    def embedder_dim(self):
        """Dimensionality of the embedder model's output vectors.

        Default: ``1024`` (for BAAI/bge-m3). Reads from ``CASTLE_EMBEDDER_DIM``
        env var first, then config file, then default.
        """
        env_val = os.environ.get("CASTLE_EMBEDDER_DIM")
        if env_val:
            try:
                parsed = int(env_val)
                if parsed >= 1:
                    return parsed
            except ValueError:
                pass
        cfg_val = self._file_config.get("embedder_dim")
        try:
            parsed = int(cfg_val) if cfg_val is not None else 1024
            if parsed >= 1:
                return parsed
        except (TypeError, ValueError):
            pass
        return 1024

    @property
    def embedder_identity(self):
        """Stable identity string for the embedder stack.

        Used by ``EmbedderIdentityMismatchError`` to detect stale palaces built
        with a different embedding configuration. Changing this value will
        cause any palace built under a prior identity to fail loudly on open,
        prompting the user to run ``castle reindex``.

        Reads from ``CASTLE_EMBEDDER_IDENTITY`` env var first, then config file.
        If neither is set, auto-derives from ``embedder_model`` by stripping the
        org prefix (last component after the final ``/``). For example,
        ``"BAAI/bge-m3"`` → ``"bge-m3"``.
        """
        env_val = os.environ.get("CASTLE_EMBEDDER_IDENTITY")
        if env_val:
            return env_val.strip()
        cfg_val = self._file_config.get("embedder_identity")
        if cfg_val:
            return str(cfg_val).strip()
        model = self.embedder_model
        return model.rsplit("/", 1)[-1] if "/" in model else model

    @property
    def reranker_model_gpu(self):
        """Cross-encoder reranker model for GPU environments.

        Default: ``"BAAI/bge-reranker-v2-m3"``. Reads from
        ``CASTLE_RERANKER_MODEL_GPU`` env var first, then config file, then default.
        """
        env_val = os.environ.get("CASTLE_RERANKER_MODEL_GPU")
        if env_val:
            return env_val.strip()
        return str(self._file_config.get("reranker_model_gpu", "BAAI/bge-reranker-v2-m3")).strip()

    @property
    def reranker_model_cpu(self):
        """Cross-encoder reranker model for CPU environments.

        Default: ``"BAAI/bge-reranker-base"``. Reads from
        ``CASTLE_RERANKER_MODEL_CPU`` env var first, then config file, then default.
        """
        env_val = os.environ.get("CASTLE_RERANKER_MODEL_CPU")
        if env_val:
            return env_val.strip()
        return str(self._file_config.get("reranker_model_cpu", "BAAI/bge-reranker-base")).strip()

    @property
    def reranker_k_interactive(self):
        """Number of results to rerank in interactive search mode.

        Default: ``20``. Reads from ``CASTLE_RERANKER_K_INTERACTIVE`` env var
        first, then config file, then default.
        """
        env_val = os.environ.get("CASTLE_RERANKER_K_INTERACTIVE")
        if env_val:
            try:
                parsed = int(env_val)
                if parsed >= 1:
                    return parsed
            except ValueError:
                pass
        cfg_val = self._file_config.get("reranker_k_interactive")
        try:
            parsed = int(cfg_val) if cfg_val is not None else 20
        except (TypeError, ValueError):
            parsed = 20
        return max(1, parsed)

    @property
    def reranker_k_hook(self):
        """Number of results to rerank in background hook mode.

        Default: ``10``. Reads from ``CASTLE_RERANKER_K_HOOK`` env var
        first, then config file, then default.
        """
        env_val = os.environ.get("CASTLE_RERANKER_K_HOOK")
        if env_val:
            try:
                parsed = int(env_val)
                if parsed >= 1:
                    return parsed
            except ValueError:
                pass
        cfg_val = self._file_config.get("reranker_k_hook")
        try:
            parsed = int(cfg_val) if cfg_val is not None else 10
        except (TypeError, ValueError):
            parsed = 10
        return max(1, parsed)

    @property
    def llm_judge_top_n(self):
        """Number of candidates to feed the LLM judge in Stage 4.

        Default: ``10``. Reads from ``CASTLE_LLM_JUDGE_TOP_N`` env var
        first, then config file, then default.
        """
        env_val = os.environ.get("CASTLE_LLM_JUDGE_TOP_N")
        if env_val:
            try:
                parsed = int(env_val)
                if parsed >= 1:
                    return parsed
            except ValueError:
                pass
        cfg_val = self._file_config.get("llm_judge_top_n")
        try:
            parsed = int(cfg_val) if cfg_val is not None else 10
        except (TypeError, ValueError):
            parsed = 10
        return max(1, parsed)

    @property
    def llm_provider(self):
        """Provider name for the LLM-as-judge step (``"ollama"`` / ``"openai-compat"`` / ``"anthropic"``).

        Default: ``"ollama"``. Reads from ``CASTLE_LLM_PROVIDER`` env var
        first, then config file, then default.
        """
        env_val = os.environ.get("CASTLE_LLM_PROVIDER")
        if env_val:
            return env_val.strip()
        return str(self._file_config.get("llm_provider", "ollama")).strip()

    @property
    def llm_model(self):
        """Model name passed to the LLM provider.

        Default: ``"qwen3.5:latest"`` (matches ``cmd_init``'s default).
        Users can override via ``CASTLE_LLM_MODEL`` env var or ``llm_model``
        in castle.yaml.

        Reads from ``CASTLE_LLM_MODEL`` env var first, then config file,
        then default.
        """
        env_val = os.environ.get("CASTLE_LLM_MODEL")
        if env_val:
            return env_val.strip()
        return str(self._file_config.get("llm_model", "qwen3.5:latest")).strip()

    @property
    def llm_endpoint(self):
        """Endpoint URL override for the LLM provider, or None to use the provider's default.

        Default: ``None`` (use provider's default: e.g. http://localhost:11434
        for Ollama, https://api.anthropic.com for Anthropic).
        Reads from ``CASTLE_LLM_ENDPOINT`` env var first, then config file,
        then default.
        """
        env_val = os.environ.get("CASTLE_LLM_ENDPOINT")
        if env_val:
            return env_val.strip()
        cfg_val = self._file_config.get("llm_endpoint")
        return str(cfg_val).strip() if cfg_val else None

    @property
    def llm_api_key(self):
        """API key for external LLM providers (Anthropic / OpenAI-compat).

        Default: ``None`` (no API key — works for local Ollama).
        Reads from ``CASTLE_LLM_API_KEY`` env var first, then config file,
        then default. NOTE: prefer the env var over the config file for
        secrets — castle.yaml may be checked into version control.
        """
        env_val = os.environ.get("CASTLE_LLM_API_KEY")
        if env_val:
            return env_val.strip()
        cfg_val = self._file_config.get("llm_api_key")
        return str(cfg_val).strip() if cfg_val else None

    @property
    def llm_timeout(self):
        """HTTP timeout (seconds) for LLM provider calls.

        Default: ``120``. Reads from ``CASTLE_LLM_TIMEOUT`` env var first,
        then config file, then default.
        """
        env_val = os.environ.get("CASTLE_LLM_TIMEOUT")
        if env_val:
            try:
                parsed = int(env_val)
                if parsed >= 1:
                    return parsed
            except ValueError:
                pass
        cfg_val = self._file_config.get("llm_timeout")
        try:
            parsed = int(cfg_val) if cfg_val is not None else 120
        except (TypeError, ValueError):
            parsed = 120
        return max(1, parsed)

    @property
    def soar_rules_path(self):
        """Path to the Soar production rule file for #4a's boost-tag layer.

        Default: ``<package>/rules/castle-boost.soar`` (shipped with Castle).
        Override to point at a custom rule file via env or castle.yaml.

        Reads from ``CASTLE_SOAR_RULES_PATH`` env var first, then config file,
        then default.
        """
        env_val = os.environ.get("CASTLE_SOAR_RULES_PATH")
        if env_val:
            return env_val.strip()
        cfg_val = self._file_config.get("soar_rules_path")
        if cfg_val:
            return str(cfg_val).strip()
        # Default: package-relative path to rules/castle-boost.soar
        return str(Path(__file__).parent / "rules" / "castle-boost.soar")

    @property
    def k_rrf(self):
        """Number of results to fuse in Reciprocal Rank Fusion.

        Default: ``60``. Reads from ``CASTLE_K_RRF`` env var first,
        then config file, then default.
        """
        env_val = os.environ.get("CASTLE_K_RRF")
        if env_val:
            try:
                parsed = int(env_val)
                if parsed >= 1:
                    return parsed
            except ValueError:
                pass
        cfg_val = self._file_config.get("k_rrf")
        try:
            parsed = int(cfg_val) if cfg_val is not None else 60
        except (TypeError, ValueError):
            parsed = 60
        return max(1, parsed)

    @property
    def weight_dense(self):
        """Weight for dense (vector) search in fusion.

        Default: ``1.0``. Reads from ``CASTLE_WEIGHT_DENSE`` env var first,
        then config file, then default.
        """
        env_val = os.environ.get("CASTLE_WEIGHT_DENSE")
        if env_val:
            try:
                return float(env_val)
            except ValueError:
                pass
        cfg_val = self._file_config.get("weight_dense")
        try:
            return float(cfg_val) if cfg_val is not None else 1.0
        except (TypeError, ValueError):
            return 1.0

    @property
    def weight_sparse(self):
        """Weight for sparse (BM25) search in fusion.

        Default: ``1.0``. Reads from ``CASTLE_WEIGHT_SPARSE`` env var first,
        then config file, then default.
        """
        env_val = os.environ.get("CASTLE_WEIGHT_SPARSE")
        if env_val:
            try:
                return float(env_val)
            except ValueError:
                pass
        cfg_val = self._file_config.get("weight_sparse")
        try:
            return float(cfg_val) if cfg_val is not None else 1.0
        except (TypeError, ValueError):
            return 1.0

    @property
    def weight_kg(self):
        """Weight for knowledge-graph search in fusion.

        Default: ``0.5``. Reads from ``CASTLE_WEIGHT_KG`` env var first,
        then config file, then default.
        """
        env_val = os.environ.get("CASTLE_WEIGHT_KG")
        if env_val:
            try:
                return float(env_val)
            except ValueError:
                pass
        cfg_val = self._file_config.get("weight_kg")
        try:
            return float(cfg_val) if cfg_val is not None else 0.5
        except (TypeError, ValueError):
            return 0.5

    @property
    def recency_tau_days(self):
        """Time constant (in days) for recency boost decay.

        Default: ``90.0``. Reads from ``CASTLE_RECENCY_TAU_DAYS`` env var first,
        then config file, then default.
        """
        env_val = os.environ.get("CASTLE_RECENCY_TAU_DAYS")
        if env_val:
            try:
                return float(env_val)
            except ValueError:
                pass
        cfg_val = self._file_config.get("recency_tau_days")
        try:
            return float(cfg_val) if cfg_val is not None else 90.0
        except (TypeError, ValueError):
            return 90.0

    @property
    def recency_max_boost(self):
        """Maximum multiplier for recency boost.

        Default: ``1.5``. Reads from ``CASTLE_RECENCY_MAX_BOOST`` env var first,
        then config file, then default.
        """
        env_val = os.environ.get("CASTLE_RECENCY_MAX_BOOST")
        if env_val:
            try:
                return float(env_val)
            except ValueError:
                pass
        cfg_val = self._file_config.get("recency_max_boost")
        try:
            return float(cfg_val) if cfg_val is not None else 1.5
        except (TypeError, ValueError):
            return 1.5

    @property
    def info_weight_enabled(self):
        """Gate for info-weight retrieval demotion (2026-07-26 spec).

        Default: ``False`` — flips ON only after the LongMemEval benchmark
        gate. Env ``CASTLE_INFO_WEIGHT_ENABLED`` ("1"/"true" = on), then
        config file, then default.
        """
        env_val = os.environ.get("CASTLE_INFO_WEIGHT_ENABLED")
        if env_val is not None:
            return env_val.strip().lower() in ("1", "true", "yes")
        cfg_val = self._file_config.get("info_weight_enabled")
        if cfg_val is None:
            return False
        if isinstance(cfg_val, str):
            return cfg_val.strip().lower() in ("1", "true", "yes")
        return bool(cfg_val)

    @property
    def info_weight_threshold(self):
        """Novelty below this is demoted. Default 0.10 (research "low" band)."""
        env_val = os.environ.get("CASTLE_INFO_WEIGHT_THRESHOLD")
        if env_val:
            try:
                return float(env_val)
            except ValueError:
                pass
        cfg_val = self._file_config.get("info_weight_threshold")
        try:
            return float(cfg_val) if cfg_val is not None else 0.10
        except (TypeError, ValueError):
            return 0.10

    @property
    def info_weight_min_factor(self):
        """Score-multiplier floor for fully-duplicate drawers. Default 0.5."""
        env_val = os.environ.get("CASTLE_INFO_WEIGHT_MIN_FACTOR")
        if env_val:
            try:
                return float(env_val)
            except ValueError:
                pass
        cfg_val = self._file_config.get("info_weight_min_factor")
        try:
            return float(cfg_val) if cfg_val is not None else 0.5
        except (TypeError, ValueError):
            return 0.5

    @property
    def entity_promote_threshold(self) -> float:
        """Confidence threshold above which auto-detected entities are added
        to the registry by the KG enricher.

        Default: ``0.70``. Reads from ``CASTLE_ENTITY_PROMOTE_THRESHOLD`` env var first,
        then config file, then default.
        """
        env_val = os.environ.get("CASTLE_ENTITY_PROMOTE_THRESHOLD")
        if env_val:
            try:
                return float(env_val.strip())
            except ValueError:
                pass
        cfg_val = self._file_config.get("entity_promote_threshold")
        if cfg_val is not None:
            try:
                return float(cfg_val)
            except (ValueError, TypeError):
                pass
        return 0.70

    @property
    def entity_score_sample_drawers(self) -> int:
        """Per-candidate drawer-sample size for Stage B scoring.

        Default: ``20``. Reads from ``CASTLE_ENTITY_SCORE_SAMPLE_DRAWERS`` env var first,
        then config file, then default.
        """
        env_val = os.environ.get("CASTLE_ENTITY_SCORE_SAMPLE_DRAWERS")
        if env_val:
            try:
                return int(env_val.strip())
            except ValueError:
                pass
        cfg_val = self._file_config.get("entity_score_sample_drawers")
        if cfg_val is not None:
            try:
                return int(cfg_val)
            except (ValueError, TypeError):
                pass
        return 20

    @property
    def entity_fetch_batch_size(self) -> int:
        """LanceDB bulk-fetch batch size for Stage B's text_by_id build.

        Default: ``1000``. Reads from ``CASTLE_ENTITY_FETCH_BATCH_SIZE`` env var first,
        then config file, then default.
        """
        env_val = os.environ.get("CASTLE_ENTITY_FETCH_BATCH_SIZE")
        if env_val:
            try:
                return int(env_val.strip())
            except ValueError:
                pass
        cfg_val = self._file_config.get("entity_fetch_batch_size")
        if cfg_val is not None:
            try:
                return int(cfg_val)
            except (ValueError, TypeError):
                pass
        return 1000

    @property
    def kg_hop_top_n(self):
        """Number of top results to expand via KG hops.

        Default: ``50``. Reads from ``CASTLE_KG_HOP_TOP_N`` env var first,
        then config file, then default.
        """
        env_val = os.environ.get("CASTLE_KG_HOP_TOP_N")
        if env_val:
            try:
                parsed = int(env_val)
                if parsed >= 1:
                    return parsed
            except ValueError:
                pass
        cfg_val = self._file_config.get("kg_hop_top_n")
        try:
            parsed = int(cfg_val) if cfg_val is not None else 50
        except (TypeError, ValueError):
            parsed = 50
        return max(1, parsed)

    @property
    def quality_threshold_medium(self) -> float:
        """Lower threshold for Stage 6's two-tier boost. Default: ``0.53``.

        Calibrated from a 100-drawer random sample on the user's palace at
        ~/.castle/palace on 2026-05-14 (p75).

        Reads from ``CASTLE_QUALITY_THRESHOLD_MEDIUM`` env var first, then
        config file, then default.
        """
        env_val = os.environ.get("CASTLE_QUALITY_THRESHOLD_MEDIUM")
        if env_val:
            try:
                return float(env_val)
            except ValueError:
                pass
        cfg_val = self._file_config.get("quality_threshold_medium")
        if cfg_val is not None:
            try:
                return float(cfg_val)
            except (ValueError, TypeError):
                pass
        return 0.53

    @property
    def quality_threshold_high(self) -> float:
        """Upper threshold for Stage 6's two-tier boost. Default: ``0.60``.

        Calibrated from a 100-drawer random sample on the user's palace at
        ~/.castle/palace on 2026-05-14 (p90).

        Reads from ``CASTLE_QUALITY_THRESHOLD_HIGH`` env var first, then
        config file, then default.
        """
        env_val = os.environ.get("CASTLE_QUALITY_THRESHOLD_HIGH")
        if env_val:
            try:
                return float(env_val)
            except ValueError:
                pass
        cfg_val = self._file_config.get("quality_threshold_high")
        if cfg_val is not None:
            try:
                return float(cfg_val)
            except (ValueError, TypeError):
                pass
        return 0.60

    @property
    def quality_boost_medium(self) -> float:
        """Score multiplier applied to medium-tier hits in Stage 6. Default: ``1.15``.

        Reads from ``CASTLE_QUALITY_BOOST_MEDIUM`` env var first, then config
        file, then default.
        """
        env_val = os.environ.get("CASTLE_QUALITY_BOOST_MEDIUM")
        if env_val:
            try:
                return float(env_val)
            except ValueError:
                pass
        cfg_val = self._file_config.get("quality_boost_medium")
        if cfg_val is not None:
            try:
                return float(cfg_val)
            except (ValueError, TypeError):
                pass
        return 1.15

    @property
    def quality_boost_high(self) -> float:
        """Score multiplier applied to high-tier hits in Stage 6. Default: ``1.25``.

        Reads from ``CASTLE_QUALITY_BOOST_HIGH`` env var first, then config
        file, then default.
        """
        env_val = os.environ.get("CASTLE_QUALITY_BOOST_HIGH")
        if env_val:
            try:
                return float(env_val)
            except ValueError:
                pass
        cfg_val = self._file_config.get("quality_boost_high")
        if cfg_val is not None:
            try:
                return float(cfg_val)
            except (ValueError, TypeError):
                pass
        return 1.25

    @property
    def use_new_retrieval_pipeline(self):
        """Whether to use the new 3-stage retrieval pipeline.

        Default: ``True`` (new SOTA pipeline enabled by default). Reads from
        ``CASTLE_USE_NEW_RETRIEVAL_PIPELINE`` env var first, then config file,
        then default.
        """
        env_val = os.environ.get("CASTLE_USE_NEW_RETRIEVAL_PIPELINE")
        if env_val:
            return env_val.strip().lower() in ("true", "1", "yes", "on")
        cfg_val = self._file_config.get("use_new_retrieval_pipeline", True)
        if isinstance(cfg_val, str):
            return cfg_val.strip().lower() in ("true", "1", "yes", "on")
        return bool(cfg_val)

    def set_hook_setting(self, key: str, value: bool):
        """Update a hook setting and write config to disk."""
        if "hooks" not in self._file_config:
            self._file_config["hooks"] = {}
        self._file_config["hooks"][key] = value
        try:
            with open(self._config_file, "w", encoding="utf-8") as f:
                json.dump(self._file_config, f, indent=2, ensure_ascii=False)
        except OSError:
            pass

    def init(self):
        """Create config directory and write default config.json if it doesn't exist."""
        self._config_dir.mkdir(parents=True, exist_ok=True)
        # Restrict directory permissions to owner only (Unix)
        try:
            self._config_dir.chmod(0o700)
        except (OSError, NotImplementedError):
            pass  # Windows doesn't support Unix permissions
        if not self._config_file.exists():
            default_config = {
                "palace_path": DEFAULT_PALACE_PATH,
                "collection_name": DEFAULT_COLLECTION_NAME,
                "topic_wings": DEFAULT_TOPIC_WINGS,
                "hall_keywords": DEFAULT_HALL_KEYWORDS,
            }
            with open(self._config_file, "w") as f:
                json.dump(default_config, f, indent=2)
            # Restrict config file to owner read/write only
            try:
                self._config_file.chmod(0o600)
            except (OSError, NotImplementedError):
                pass
        return self._config_file

    def save_people_map(self, people_map):
        """Write people_map.json to config directory.

        Args:
            people_map: Dict mapping name variants to canonical names.
        """
        self._config_dir.mkdir(parents=True, exist_ok=True)
        with open(self._people_map_file, "w") as f:
            json.dump(people_map, f, indent=2)
        try:
            self._people_map_file.chmod(0o600)
        except (OSError, NotImplementedError):
            pass
        return self._people_map_file


# Backward-compat alias. Programmatic users still importing the old name keep
# working. Kept indefinitely; remove only after a deliberate breaking-change
# version bump.
MempalaceConfig = CognitiveCastleConfig
