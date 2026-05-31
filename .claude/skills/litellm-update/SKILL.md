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

3. **Determine the litellm_params** using the mapping rules below.

4. **Insert the new model entry** in the correct section (Text Models, Image Models, Embedding Models) in alphabetical order by `model_name`.

5. **After editing**, invoke the `git-commit-helper` skill to stage and commit the change.

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
```

If the response code checks `reasoning_content` or the model name includes `reasoning`, `think`, `r1`, `step` (StepFun), add reasoning support. Use the pattern that fits:
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
