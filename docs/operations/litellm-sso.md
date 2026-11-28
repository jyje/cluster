# LiteLLM sign-in through authentik

[한국어](litellm-sso-ko.md)

The LiteLLM admin UI at `https://litellm.app.jyje.online/ui` signs people in through authentik. The API keys and the master key work as before. The rules behind this are in [authentik-access.md](authentik-access.md).

## How it works

| Part | Where |
| --- | --- |
| authentik provider and application `litellm` | sealed blueprint `authentik-litellm-oidc` in `authentik.yaml`, bound to `AuthentikAdmin` |
| Client secret in LiteLLM | SealedSecret `litellm-oidc` in `litellm.yaml`, same value as in the blueprint |
| LiteLLM settings | `GENERIC_*` and `PROXY_BASE_URL` variables in `extraEnvVars` of `litellm.yaml` |
| Redirect URI | `https://litellm.app.jyje.online/sso/callback` |

Roles come from the `groups` claim of the authentik access token:

| authentik group | LiteLLM role |
| --- | --- |
| `AuthentikAdmin` | `proxy_admin` |
| `ClusterAdmin` | `proxy_admin` |
| anyone else | `internal_user_viewer` (the application binding already keeps them out) |

To make someone a LiteLLM admin, add their authentik account to `AuthentikAdmin`. Nobody is named in git.

## Limits

LiteLLM allows single sign-on for up to 5 users without an Enterprise license. Users who already exist can still sign in after the limit. Check the user count before adding people.

## Fallback sign-in

The local UI account stays. Its name and password are in the Secret `litellm-creds`:

```bash
kubectl -n ollama-system get secret litellm-creds -o jsonpath='{.data.litellm\.ui-username}' | base64 -d
kubectl -n ollama-system get secret litellm-creds -o jsonpath='{.data.litellm\.ui-password}' | base64 -d
```

With SSO on, the sign-in page goes to authentik. Open `https://litellm.app.jyje.online/fallback/login` to use the local account.

## Rotating the client secret

Seal the same new value into both `authentik-litellm-oidc` and `litellm-oidc`, and replace both in one change.

## Checks after a change

1. Argo CD shows `authentik` and `litellm` as Synced and Healthy, and both LiteLLM Pods are Ready.
2. Open the UI, sign in with the owner account, and check that the account is shown as an admin.
3. An API call with an existing key still works.
