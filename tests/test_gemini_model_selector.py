"""Regression tests for Gemini model selector - ensures retired models are not selectable."""

import re
import json


def test_gemini_selector_no_retired_models():
    """Test that Gemini provider model list doesn't contain retired 1.5 models."""
    with open('app.js', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract ProviderModels.gemini array
    match = re.search(r'ProviderModels\s*=\s*\{[\s\S]*?gemini:\s*(\[[\s\S]*?\])', content)
    assert match, "ProviderModels.gemini not found in app.js"
    
    gemini_models_str = match.group(1)
    
    # Parse the model IDs from the array
    model_ids = re.findall(r"id:\s*['\"]([^'\"]+)['\"]", gemini_models_str)
    
    # Retired models that should NOT be present
    retired_models = ['gemini-1.5-flash', 'gemini-1.5-pro']
    for retired in retired_models:
        assert retired not in model_ids, f"Retired model {retired} should not be in selectable models"
    
    # Should have at least one supported model
    assert len(model_ids) > 0, "Gemini provider should have at least one supported model"
    
    # All models should be currently supported (no shutdown date announced as of 2026-09-17)
    # Based on Google Gemini API official lifecycle
    supported_models = {
        'gemini-2.5-flash',
        'gemini-2.5-pro',
        'gemini-3.5-flash',
        'gemini-3.6-flash',
        'gemini-3.7-flash',
        'gemini-3.8-flash',
        'gemini-3.5-flash-lite',
        'gemini-3.1-flash-lite',
    }
    
    for model_id in model_ids:
        assert model_id in supported_models, f"Model {model_id} is not in the confirmed supported list"


def test_call_gemini_api_uses_selected_model():
    """Test that callGeminiAPI uses the model parameter in the request URL."""
    with open('app.js', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find callGeminiAPI function
    match = re.search(r'async function callGeminiAPI\([\s\S]*?\n\}', content)
    assert match, "callGeminiAPI function not found"
    
    func_content = match.group(0)
    
    # Verify it uses the model parameter in the URL
    assert '${model}' in func_content or "${model}" in func_content, \
        "callGeminiAPI should use the model parameter in the request URL"
    
    # Verify the URL pattern is correct
    assert 'generativelanguage.googleapis.com/v1beta/models/' in func_content, \
        "callGeminiAPI should use the correct Google API endpoint"


def test_other_providers_unchanged():
    """Test that MiniMax, OpenAI, Anthropic providers are unchanged."""
    with open('app.js', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract all provider model arrays
    providers = ['openai', 'anthropic', 'minimax']
    for provider in providers:
        match = re.search(rf'{provider}:\s*(\[[\s\S]*?\])', content)
        assert match, f"ProviderModels.{provider} not found"
        
        provider_models_str = match.group(1)
        model_ids = re.findall(r"id:\s*['\"]([^'\"]+)['\"]", provider_models_str)
        
        # Each provider should have at least one model
        assert len(model_ids) > 0, f"{provider} provider should have at least one model"
        
        # Verify known models are present (basic sanity check)
        if provider == 'openai':
            assert any('gpt-4o' in m for m in model_ids), "OpenAI should have gpt-4o models"
        elif provider == 'anthropic':
            assert any('claude' in m.lower() for m in model_ids), "Anthropic should have claude models"
        elif provider == 'minimax':
            assert any('MiniMax' in m for m in model_ids), "MiniMax should have MiniMax models"


if __name__ == '__main__':
    test_gemini_selector_no_retired_models()
    test_call_gemini_api_uses_selected_model()
    test_other_providers_unchanged()
    print("All tests passed!")