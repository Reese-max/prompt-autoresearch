import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_JS = PROJECT_ROOT / "app.js"

# Model IDs Google has already shut down (Gemini API deprecations page /
# changelog). The Gemini selector must never offer or emit these again.
RETIRED_GEMINI_IDS = {
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-1.5-flash-001",
    "gemini-1.5-flash-002",
    "gemini-1.5-pro-001",
    "gemini-1.5-pro-002",
    "gemini-1.0-pro",
    "gemini-pro",
    "gemini-pro-vision",
    "gemini-2.0-flash",
    "gemini-2.0-flash-001",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash-lite-001",
}


def _read_app_js() -> str:
    return APP_JS.read_text(encoding="utf-8")


def _gemini_option_ids(source: str) -> list[str]:
    """Extract the id strings from the ProviderModels.gemini array."""
    match = re.search(
        r"gemini\s*:\s*\[(?P<body>.*?)\]", source, flags=re.DOTALL
    )
    assert match is not None, "ProviderModels.gemini block not found"
    return re.findall(r"id:\s*'([^']+)'", match.group("body"))


class GeminiProviderModelTests(unittest.TestCase):
    """Regression for issue #7: retired Gemini 1.5 model IDs must not be
    selectable, and the selector must be the single source of truth for the
    model ID that reaches the generateContent URL."""

    def test_selectable_gemini_models_exclude_retired_ids(self):
        ids = _gemini_option_ids(_read_app_js())
        self.assertTrue(ids, "ProviderModels.gemini must not be empty")
        for model_id in ids:
            self.assertNotIn(
                model_id,
                RETIRED_GEMINI_IDS,
                f"{model_id} is a shut-down Gemini model and must not be selectable",
            )
            self.assertNotRegex(
                model_id,
                r"^gemini-1\.",
                f"{model_id} belongs to the retired Gemini 1.x family",
            )
            self.assertNotIn(
                "preview",
                model_id,
                f"{model_id} is a preview-only model; selector must use stable GA IDs",
            )

    def test_no_retired_gemini_id_anywhere_in_app_js(self):
        source = _read_app_js()
        for retired in RETIRED_GEMINI_IDS:
            self.assertNotIn(
                retired,
                source,
                f"retired model id {retired} still referenced in app.js",
            )

    def test_generate_content_url_uses_selected_model_verbatim(self):
        source = _read_app_js()
        match = re.search(
            r"async function callGeminiAPI\(key, model, .*?\n\}",
            source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(match, "callGeminiAPI not found")
        body = match.group(0)
        self.assertIn(
            "v1beta/models/${model}:generateContent",
            body,
            "callGeminiAPI must build the request URL from the selected model id",
        )
        self.assertNotRegex(
            body,
            r"gemini-\d",
            "callGeminiAPI must not hardcode a fallback model id",
        )

    def test_persisted_stale_model_is_reset_to_selectable_option(self):
        """A localStorage-saved retired id must not bypass the dropdown:
        populateModelDropdown must coerce AppState.settings.model back into
        the selectable list before it can reach callGeminiAPI."""
        source = _read_app_js()
        match = re.search(
            r"function populateModelDropdown\(\).*?(?=\nfunction |\n// )",
            source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(match, "populateModelDropdown not found")
        body = match.group(0)
        self.assertRegex(
            body,
            r"some\s*\(\s*\(?\s*m\s*\)?\s*=>\s*m\.id\s*===\s*AppState\.settings\.model",
            "populateModelDropdown must validate AppState.settings.model "
            "against the provider's selectable ids",
        )
        self.assertRegex(
            body,
            r"AppState\.settings\.model\s*=\s*models\[0\]\.id",
            "populateModelDropdown must reset an unlisted persisted model "
            "to the first selectable option",
        )


if __name__ == "__main__":
    unittest.main()
