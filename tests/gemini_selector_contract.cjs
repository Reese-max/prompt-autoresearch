const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '..', 'app.js'), 'utf8');
const nodes = new Map();
const settingsModel = {
    selected: '',
    options: [],
    get value() { return this.selected; },
    set value(value) { this.selected = this.options.includes(value) ? value : ''; },
    get innerHTML() { return this.markup; },
    set innerHTML(markup) {
        this.markup = markup;
        this.options = [...markup.matchAll(/<option value="([^"]*)"/g)].map(match => match[1]);
        this.selected = this.options[0] || '';
    }
};
const document = {
    querySelectorAll: () => [],
    addEventListener: () => {},
    getElementById(id) {
        if (id === 'settings-model') return settingsModel;
        if (!nodes.has(id)) {
            nodes.set(id, {
                value: '', style: {}, textContent: '', addEventListener: () => {},
                parentNode: { querySelector: () => ({ style: {} }) }
            });
        }
        return nodes.get(id);
    }
};
const stored = new Map();
const requests = [];
const context = vm.createContext({
    document,
    window: { location: { hostname: 'example.test' } },
    localStorage: {
        getItem: key => stored.get(key) || null,
        setItem: (key, value) => stored.set(key, value),
        removeItem: key => stored.delete(key)
    },
    fetch: async (url, options) => {
        requests.push({ url, options });
        return {
            ok: true,
            json: async () => ({
                candidates: [{ content: { parts: [{ text: 'gemini response' }] } }],
                choices: [{ message: { content: 'other response' } }],
                content: [{ text: 'other response' }]
            })
        };
    }
});
vm.runInContext(source, context);
vm.runInContext('showToast = () => {}', context);
const run = expression => vm.runInContext(expression, context);

async function main() {
    const models = run('ProviderModels.gemini');
    assert.deepEqual(Array.from(models, model => model.id), [
        'gemini-3.5-flash-lite', 'gemini-3.8-flash'
    ]);
    assert.deepEqual(Array.from(models, model => model.name.split(' (')[0]), [
        'Gemini 3.5 Flash-Lite', 'Gemini 3.8 Flash'
    ]);

    stored.set('prompt_lab_settings_v2', JSON.stringify({
        provider: 'gemini', model: 'gemini-1.5-pro', apiKey: 'test-key', temperature: 0.4
    }));
    run('loadSettings()');
    assert.equal(run('AppState.settings.model'), 'gemini-1.5-pro');
    assert.equal(settingsModel.value, '');
    assert.match(settingsModel.innerHTML, /請重新選擇 Gemini 模型並儲存/);
    await assert.rejects(run("callGeminiAPI('test-key', AppState.settings.model, 'hello', 0.4)"), /不支援的 Gemini 模型/);
    await assert.rejects(run("callGeminiAPI('test-key', 'gemini-3.8-flash/other', 'hello', 0.4)"), /不支援的 Gemini 模型/);
    assert.equal(requests.length, 0, 'stale and unknown models must not leave the browser');

    run('saveSettingsToLocal()');
    assert.equal(run('AppState.settings.model'), 'gemini-1.5-pro', 'blank placeholder cannot be saved');
    for (const model of models) {
        settingsModel.value = model.id;
        run('saveSettingsToLocal()');
        assert.equal(run('AppState.settings.model'), model.id);
        assert.equal(JSON.parse(stored.get('prompt_lab_settings_v2')).model, model.id);
        assert.equal(await run("callGeminiAPI('test-key', AppState.settings.model, 'hello', 0.4)"), 'gemini response');
        const request = requests.at(-1);
        assert.equal(request.url, `https://generativelanguage.googleapis.com/v1beta/models/${model.id}:generateContent?key=test-key`);
        assert.deepEqual(JSON.parse(request.options.body), {
            contents: [{ parts: [{ text: 'hello' }] }],
            generationConfig: { temperature: 0.4 }
        });
    }
    context.window.location.hostname = 'localhost';
    await run("callGeminiAPI('test-key', 'gemini-3.8-flash', 'hello', 0.4)");
    assert.equal(requests.at(-1).url, '/api/proxy');
    assert.equal(JSON.parse(requests.at(-1).options.body).url,
        'https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent?key=test-key');
    context.window.location.hostname = 'example.test';

    run("AppState.settings.provider = 'minimax'; AppState.settings.model = 'MiniMax-M2.7'");
    document.getElementById('settings-provider').value = 'gemini';
    run('populateModelDropdown()');
    assert.equal(run('AppState.settings.provider'), 'minimax');
    assert.equal(run('AppState.settings.model'), 'MiniMax-M2.7', 'preview must not mutate saved settings');
    run("AppState.settings.model = 'unlisted-minimax-model'");
    document.getElementById('settings-provider').value = 'minimax';
    run('populateModelDropdown()');
    assert.equal(settingsModel.value, '', 'other providers keep their original invalid-saved-model display');
    assert.equal(run('AppState.settings.model'), 'unlisted-minimax-model');

    assert.deepEqual(Array.from(run('ProviderModels.openai'), model => model.id), ['gpt-4o-mini', 'gpt-4o']);
    assert.deepEqual(Array.from(run('ProviderModels.anthropic'), model => model.id), ['claude-3-5-sonnet-20241022']);
    assert.deepEqual(Array.from(run('ProviderModels.minimax'), model => model.id), ['MiniMax-M2.7', 'MiniMax-M2.5']);
    await run("callMiniMaxAPI('test-key', 'MiniMax-M2.7', 'hello', 0.4)");
    assert.equal(requests.at(-1).url, 'https://api.minimaxi.chat/v1/text/chatcompletion_v2');
    await run("callOpenAIAPI('test-key', 'gpt-4o-mini', 'hello', 0.4)");
    assert.equal(requests.at(-1).url, 'https://api.openai.com/v1/chat/completions');
    await run("callAnthropicAPI('test-key', 'claude-3-5-sonnet-20241022', 'hello', 0.4)");
    assert.equal(requests.at(-1).url, 'https://api.anthropic.com/v1/messages');
    console.log('Gemini selector and request contract: PASS');
}

main().catch(error => { console.error(error); process.exitCode = 1; });
