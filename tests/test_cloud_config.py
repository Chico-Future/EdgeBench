from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cloud.config import model_keys, resolve_model


YAML_TEXT = """\
version: 1
provider:
  name: bailian
  base_url_env: TEST_BAILIAN_URL
  api_key_env: TEST_BAILIAN_KEY
defaults:
  enabled: false
  temperature: 0.0
  request_timeout: 30
  max_tokens_field: max_tokens
  max_context_len: 8192
  max_new_tokens: {State-Given: 100, State-Seeking: 50}
  supported_profiles: [P0_prompt_only]
  extra_body: {}
models:
  qwen:
    model: qwen-test
    enabled: true
    extra_body: {enable_thinking: false}
  placeholder:
    model: REPLACE_WITH_EXACT_MODEL_ID
    enabled: false
  fixed_temperature:
    model: fixed-temperature-model
    temperature: null
  openrouter_model:
    model: google/test-model
    provider: openrouter
    base_url_env: TEST_OPENROUTER_URL
    api_key_env: TEST_OPENROUTER_KEY
"""


class CloudConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "models.yaml"
        self.path.write_text(YAML_TEXT, encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_enabled_model_keys(self):
        self.assertEqual(["qwen"], model_keys(self.path, enabled_only=True))

    def test_resolve_bailian_model(self):
        env = {
            "TEST_BAILIAN_URL": "https://workspace.example/compatible-mode/v1",
            "TEST_BAILIAN_KEY": "secret",
        }
        with patch.dict(os.environ, env, clear=False):
            model = resolve_model(
                self.path,
                "qwen",
                env_file=None,
                profile="P0_prompt_only",
                interface="State-Given",
            )
        self.assertEqual("qwen-test", model.model)
        self.assertEqual(100, model.max_new_tokens["State-Given"])
        self.assertEqual({"enable_thinking": False}, model.extra_body)

    def test_profile_capability_is_enforced(self):
        env = {
            "TEST_BAILIAN_URL": "https://workspace.example/compatible-mode/v1",
            "TEST_BAILIAN_KEY": "secret",
        }
        with patch.dict(os.environ, env, clear=False):
            with self.assertRaisesRegex(ValueError, "profile_not_supported"):
                resolve_model(
                    self.path,
                    "qwen",
                    env_file=None,
                    profile="P1_schema_guided",
                    interface="State-Given",
                )

    def test_null_temperature_is_preserved_for_provider_default(self):
        env = {
            "TEST_BAILIAN_URL": "https://workspace.example/compatible-mode/v1",
            "TEST_BAILIAN_KEY": "secret",
        }
        with patch.dict(os.environ, env, clear=False):
            model = resolve_model(
                self.path,
                "fixed_temperature",
                env_file=None,
                profile="P0_prompt_only",
                interface="State-Given",
            )
        self.assertIsNone(model.temperature)

    def test_model_can_override_provider_and_credentials(self):
        env = {
            "TEST_OPENROUTER_URL": "https://openrouter.ai/api/v1",
            "TEST_OPENROUTER_KEY": "openrouter-secret",
        }
        with patch.dict(os.environ, env, clear=False):
            model = resolve_model(
                self.path,
                "openrouter_model",
                env_file=None,
                profile="P0_prompt_only",
                interface="State-Seeking",
            )
        self.assertEqual("openrouter", model.provider)
        self.assertEqual("https://openrouter.ai/api/v1", model.base_url)
        self.assertEqual("TEST_OPENROUTER_KEY", model.api_key_env)
        self.assertEqual("google/test-model", model.model)


if __name__ == "__main__":
    unittest.main()
