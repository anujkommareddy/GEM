"""Configuration management for GEM autoresearch system."""

import json
import os
from pathlib import Path
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class Config:
    """Load and manage configuration from JSON files and environment."""

    def __init__(self, config_dir: str = None):
        """
        Initialize config loader.

        Args:
            config_dir: Path to config directory. Defaults to ./config
        """
        self.config_dir = Path(config_dir or "./config")
        self.config_file = self.config_dir / "config.json"
        self.evaluator_config_file = self.config_dir / "evaluator_config.json"

        if not self.config_file.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_file}")

        self.config = self._load_config(self.config_file)
        self.evaluator_config = self._load_config(self.evaluator_config_file)

        # Override with environment variables where applicable
        self._apply_env_overrides()

    def _load_config(self, path: Path) -> Dict[str, Any]:
        """Load JSON config file."""
        try:
            with open(path) as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load config from {path}: {e}")
            raise

    def _apply_env_overrides(self):
        """Apply environment variable overrides."""
        if model := os.getenv("GEM_MODEL"):
            self.config["models"]["default"] = model

        if pdf_source := os.getenv("GEM_PDF_SOURCE"):
            self.config["paths"]["pdf_source"] = pdf_source

        if extracted := os.getenv("GEM_EXTRACTED_TEXT"):
            self.config["paths"]["extracted_text"] = extracted

        if benchmark := os.getenv("GEM_BENCHMARK_FILE"):
            self.config["paths"]["benchmark_file"] = benchmark

        if results := os.getenv("GEM_RESULTS_LOG"):
            self.config["paths"]["results_log"] = results

    def get(self, key: str, default: Any = None) -> Any:
        """Get config value by dot-notation key (e.g., 'models.default')."""
        keys = key.split(".")
        value = self.config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default
        return value

    def get_path(self, key: str) -> Path:
        """Get a path from config and ensure it exists (except benchmark/results which are created)."""
        path = Path(self.get(f"paths.{key}"))

        # Create directories for output paths
        if key in ["extracted_text", "results", "results_log", "experiment_dir", "cache", "benchmark_file"]:
            path.parent.mkdir(parents=True, exist_ok=True)

        return path

    def get_model_config(self, model_name: str = None) -> Dict[str, Any]:
        """Get configuration for a specific model."""
        if not model_name:
            model_name = self.get("models.default")

        return self.get(f"models.{model_name}", {})

    def get_evaluation_dimensions(self) -> list:
        """Get list of evaluation dimensions."""
        return self.get("evaluation.dimensions", [])

    def load_rubric(self) -> str:
        """Load the evaluation rubric prompt."""
        rubric_file = self.config_dir / self.evaluator_config.get("rubric_file", "rubric_prompt.md")
        if not rubric_file.exists():
            raise FileNotFoundError(f"Rubric file not found: {rubric_file}")
        return rubric_file.read_text()

    def load_extraction_prompt(self) -> str:
        """Load the feature extraction prompt."""
        extraction_file = self.config_dir / self.evaluator_config.get("extraction_prompt_file", "extraction_prompt.md")
        if not extraction_file.exists():
            raise FileNotFoundError(f"Extraction prompt file not found: {extraction_file}")
        return extraction_file.read_text()

    def to_dict(self) -> Dict[str, Any]:
        """Return config as dictionary."""
        return self.config.copy()
