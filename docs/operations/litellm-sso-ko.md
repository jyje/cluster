# authentik으로 LiteLLM 로그인

[English](litellm-sso.md)

`https://litellm.app.jyje.online/ui`의 LiteLLM 관리 화면은 authentik으로 로그인합니다. API 키와 마스터 키는 그대로 동작합니다. 바탕이 되는 규칙은 [authentik-access-ko.md](authentik-access-ko.md)에 있습니다.

## 동작 방식

| 항목 | 위치 |
| --- | --- |
| authentik 제공자와 애플리케이션 `litellm` | `authentik.yaml`의 봉인된 블루프린트 `authentik-litellm-oidc`, `AuthentikAdmin`에 바인딩 |
| LiteLLM의 클라이언트 시크릿 | `litellm.yaml`의 SealedSecret `litellm-oidc`, 블루프린트와 같은 값 |
| LiteLLM 설정 | `litellm.yaml`의 `extraEnvVars`에 있는 `GENERIC_*`와 `PROXY_BASE_URL` 변수 |
| 리디렉션 URI | `https://litellm.app.jyje.online/sso/callback` |

역할은 authentik 액세스 토큰의 `groups` 클레임에서 옵니다.

| authentik 그룹 | LiteLLM 역할 |
| --- | --- |
| `AuthentikAdmin` | `proxy_admin` |
| `ClusterAdmin` | `proxy_admin` |
| 그 밖의 사람 | `internal_user_viewer`(애플리케이션 바인딩이 이미 들어오지 못하게 막음) |

누군가를 LiteLLM 관리자로 만들려면 그 사람의 authentik 계정을 `AuthentikAdmin`에 넣습니다. git에는 이름이 없습니다.

## 제한

LiteLLM은 Enterprise 라이선스 없이는 SSO 사용자를 5명까지만 허용합니다. 한도를 넘어도 이미 있는 사용자는 계속 로그인할 수 있습니다. 사람을 추가하기 전에 사용자 수를 확인하세요.

## 예비 로그인

로컬 UI 계정은 남아 있습니다. 이름과 비밀번호는 Secret `litellm-creds`에 있습니다.

```bash
kubectl -n ollama-system get secret litellm-creds -o jsonpath='{.data.litellm\.ui-username}' | base64 -d
kubectl -n ollama-system get secret litellm-creds -o jsonpath='{.data.litellm\.ui-password}' | base64 -d
```

SSO를 켜면 로그인 화면이 authentik으로 이동합니다. 로컬 계정을 쓰려면 `https://litellm.app.jyje.online/fallback/login`을 엽니다.

## 클라이언트 시크릿 교체

같은 새 값을 `authentik-litellm-oidc`와 `litellm-oidc` 양쪽에 봉인하고, 한 번의 변경으로 둘 다 바꿉니다.

## 변경 후 확인

1. Argo CD에서 `authentik`과 `litellm`이 Synced, Healthy이고 LiteLLM 파드 2개가 Ready입니다.
2. 화면을 열어 소유자 계정으로 로그인하고, 계정이 관리자로 표시되는지 확인합니다.
3. 기존 키로 API 호출이 여전히 됩니다.
