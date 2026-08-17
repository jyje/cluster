---
name: litellm-update
description: Update LiteLLM proxy configuration by translating AI SDK example code (Python/shell) into litellm.yaml model entries. Use when the user provides sample code using NVIDIA NIM, OpenAI, or other AI provider SDKs and wants to add the model to the cluster's LiteLLM proxy.
---

# LiteLLM Update Skill

You are an expert in configuring the LiteLLM proxy for a Kubernetes homelab cluster. When the user provides AI SDK example code (Python or shell), analyze it and add the appropriate model entry to the LiteLLM configuration.

## Configuration File

The primary configuration file is:
```
clusters/r4spi/apps/litellm.yaml
```

This is an ArgoCD Application manifest. Model entries live under:
```yaml
spec.source.helm.valuesObject.proxy_config.model_list
```

## Workflow

1. **Analyze the provided code** — extract:
   - Model name (e.g. `stepfun-ai/step-3.7-flash`)
   - Provider/API base (e.g. `https://integrate.api.nvidia.com/v1`)
   - Model type: text (chat), image generation, or embedding
   - Any special parameters (reasoning flags, extra_body, etc.)

2. **Read the current litellm.yaml** to understand existing patterns and find the right insertion point.

3. **Look up the official model card** (see "Model Card Research" below). Note the documented context length, output token limit, and any special serving parameters. Treat this as a starting hypothesis, not ground truth — model card wording (e.g. "up to 1M tokens") can be imprecise about the exact enforced number or unit (decimal vs. binary).

4. **Verify the spec empirically against the live API** (see "Spec Verification" below) before writing anything into `litellm.yaml`. This is a mandatory gate, not an optional nicety — a real incident this repo hit: a model card said "up to 1M tokens," the config was about to ship with `1048576` (2^20) on that assumption, and a direct API test revealed the real enforced limit was exactly `1000000` (decimal). Skipping verification would have shipped a wrong number that either under-serves the model or causes confusing downstream errors.

5. **Determine the litellm_params** using the mapping rules below, using the verified numbers (not the model card's raw wording) for `model_info`.

6. **Present the verification results to the user and wait for confirmation** before writing the change — a short table of (claimed spec → verified value → chosen parameter) is enough. Do not skip this even for a model that "looks obviously fine"; the verification step exists specifically to catch cases that don't.

7. **Insert the new model entry** in the correct section (Text Models, Image Models, Embedding Models) in alphabetical order by `model_name`.

8. **After editing**, invoke the `git-commit-helper` skill to stage and commit the change.

---

## Model Card Research

Before writing any config, find the model's official documentation and read it — don't rely on memory or the SDK example alone.

### NVIDIA NIM

- **Model card (primary source for specs)**: `https://build.nvidia.com/<org>/<model>/modelcard` — human-readable page with Context Length, License, Release Date, recommended sampling params, and use-case guidance.
- **API reference**: `https://docs.api.nvidia.com/nim/reference/<org>-<model>` — endpoint/parameter reference. A `404` here is itself a useful signal: the model isn't live on NIM yet (confirmed this way once — a model announced elsewhere hadn't reached NIM's catalog, so adding it would have configured a dead entry).
- **What NIM's own API will *not* tell you**: `GET /v1/models/<id>` (the OpenAI-compatible models-list endpoint) returns only `{id, object, created, owned_by}` — no context length, no token limits. The model card is the only documented source; that's exactly why step 4 (empirical verification) exists — a documented number that can't be cross-checked against a second API field needs to be cross-checked against reality instead.

### Other providers

Use the provider's own model/pricing page (OpenAI's `platform.openai.com/docs/models`, Anthropic's model overview, etc.). The same rule applies: treat published specs as a hypothesis to verify, not a value to transcribe blindly, especially for context-window and rate-limit figures that vary by tier/account.

---

## Spec Verification (CI Test)

A lightweight, repeatable procedure for confirming a model's real limits by calling the live API directly — bypassing litellm, so the test isolates the provider's own behavior from anything our config might be doing wrong.

1. **Get the API key** the same way the target `litellm.yaml` entry will reference it (e.g. `kubectl get secret litellm-creds -n ollama-system -o jsonpath='{.data.nim\.api\.key}' | base64 -d`) — never print it; hold it in a shell variable within one command block and `unset` it after.

2. **Calibrate the token-to-character ratio** with one small, cheap call first: send a short request, read `usage.prompt_tokens` from the response, and compute `chars_sent / prompt_tokens`. Token density varies by content (repeated filler text compresses differently than natural language) — don't assume a fixed ratio (4 chars/token undershot badly in practice; the real ratio for repeated filler text was closer to 8).

3. **Probe the boundary from both sides**, using the calibrated ratio to size a filler prompt:
   - One request sized just *over* the model card's claimed limit — the provider's rejection error message is often the most authoritative source available (NVIDIA NIM's 400 response literally states `"maximum context length is N tokens"` with the exact enforced number).
   - One request sized just *under* the claimed limit — confirm it succeeds (`200`/`HTTP 200`) with a real, small `max_tokens` (e.g. `5`) to keep response cost negligible.
   - Both results together — the exact rejection threshold and a passing case near it — are what justify writing a specific number into `model_info`, not just one side of the test.

4. **For reasoning/thinking parameters**, verify the same way: send one call with the candidate `extra_body` flag set and inspect the response for `reasoning_content` (or whatever field the model is documented to return) to confirm the flag actually does something, rather than carrying it forward from a similar model's config by assumption.

5. **Clean up** any temp payload/response files in the scratchpad directory after the test; nothing from this step belongs in the repo.

---

## Provider Mapping Rules

### NVIDIA NIM Text/Chat Models
When the code uses `ChatNVIDIA`, `langchain_nvidia_ai_endpoints`, or `https://integrate.api.nvidia.com/v1/chat/completions`:

```yaml
- model_name: "<org>/<model>"
  litellm_params:
    model: "nvidia_nim/<org>/<model>"
    api_base: "https://integrate.api.nvidia.com/v1"
    api_key: "os.environ/NIM_API_KEY"
  # <verified via direct API test — see "Spec Verification" — cite the exact
  # boundary result in a comment, e.g. "999,545 tokens succeeded; 1,000,045
  # rejected with 'maximum context length is 1000000 tokens'">
  model_info:
    max_input_tokens: <verified_value>
```

`model_info.max_input_tokens` is not optional for a new text/chat entry — without it, litellm reports `max_input_tokens: null` via `/v1/model/info`, and consumers (e.g. Hermes Agent) silently fall back to their own generic default instead of surfacing an error, which is a much harder bug to notice. This was live-observed: `hermes-agent-henry` displayed a 131,072-token window for a model whose real limit is 1,000,000, with no error anywhere in the chain.

If the response code checks `reasoning_content` or the model name includes `reasoning`, `think`, `r1`, `step` (StepFun), add reasoning support. Use the pattern that fits (confirm which one actually applies via the verification step above, don't guess from the model name alone):
- StepFun / models with implicit reasoning: no extra_body needed (reasoning is in the response by default)
- Models needing `thinking: true`: `extra_body.chat_template_kwargs.thinking: true`
- Models needing `enable_thinking: true`: `extra_body.chat_template_kwargs.enable_thinking: true` + `reasoning_budget: <max_tokens>`
- Models with `reasoning_effort`: `extra_body.reasoning_effort: "high"`

### NVIDIA NIM Image Models
When the code uses image generation endpoints or `https://ai.api.nvidia.com/v1/genai`:

```yaml
- model_name: "<org>/<model>"
  litellm_params:
    model: "openai/<org>/<model>"
    api_base: "https://integrate.api.nvidia.com/v1"
    api_key: "os.environ/NIM_API_IMAGE_KEY"
    drop_params: true
    extra_body:
      steps: <steps>
      cfg_scale: <cfg_scale>
      size: "1024x1024"
  model_info:
    type: "image_generation"
```

### NVIDIA NIM Embedding Models

```yaml
- model_name: "<org>/<model>"
  litellm_params:
    model: "openai/<org>/<model>"
    api_base: "https://integrate.api.nvidia.com/v1"
    api_key: "os.environ/NIM_API_KEY"
    extra_body:
      input_type: "passage"
      encoding_format: "float"
  model_info:
    type: "embedding"
```

---

## Section Organization

The `model_list` is divided into sections with comments:
1. `# Text Models` — chat/completion models
2. `# Image Models` — image generation models
3. `# Embedding Models` — embedding models

Insert new entries in the correct section, maintaining rough alphabetical order by `model_name` within each section.

---

## Constraints

- Do NOT modify the SealedSecret encrypted values (`encryptedData` fields).
- Do NOT change the Helm chart version or image tag.
- Do NOT alter the PostgreSQL cluster, adapter ConfigMap/Deployment/Service, or any infrastructure resources.
- Only add to `proxy_config.model_list`.
- Keep YAML indentation consistent (2-space indent throughout).
- If the model already exists in the list, update its parameters instead of duplicating it.
- Do not skip the model-card lookup or the empirical verification step, even when the SDK example code looks complete and self-explanatory. The example code shows how to *call* the model, not what its real limits are.
