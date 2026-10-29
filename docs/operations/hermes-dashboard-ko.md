# authentik 뒤의 Hermes 대시보드

[English](hermes-dashboard.md)

이 클러스터에서 Hermes 에이전트가 관리 대시보드를 노출하는 방법과 사용자가 로그인하는 방법입니다. 대시보드는 기본적으로 꺼져 있습니다. `hermes gateway run`은 밖으로 나가기만 하는 메신저라서 웹 UI가 없습니다. 에이전트 자체는 [hermes-agents.md](hermes-agents.md)를 보세요.

| 파일 | 내용 |
| --- | --- |
| [`examples/hermes-dashboard-application.yaml`](examples/hermes-dashboard-application.yaml) | 대시보드를 켠 Argo CD Application 전체 예시입니다. 복사해서 "example"을 바꿔 쓰세요. |
| [`examples/hermes-dashboard-blueprint.yaml`](examples/hermes-dashboard-blueprint.yaml) | 짝이 되는 authentik 블루프린트(provider, application, 그룹 바인딩)입니다. |

실제로 운영 중인 인스턴스는 `hermes-agent-henry`
([`clusters/r4spi/apps/hermes-agent-henry.yaml`](../../clusters/r4spi/apps/hermes-agent-henry.yaml))이고, 블루프린트는 [`authentik.yaml`](../../clusters/r4spi/apps/authentik.yaml)의 `authentik-hermes-dashboard`입니다.

## 로그인은 셸 접근과 같습니다

대시보드는 API 키를 보여주고, 로그인한 사용자는 셸 훅을 만들거나 Chat 탭을 쓸 수 있습니다. 로그인할 수 있는 사람은 사실상 파드에서 명령을 실행할 수 있다고 보세요. 업스트림에는 자체 사용자 허용 목록이 없으므로 **접근 제어는 authentik 애플리케이션의 그룹 바인딩이 전부입니다.** 넓힐 이유가 없다면 `AuthentikAdmin`(그룹 계층 덕분에 `ClusterAdmin`도 들어옵니다)으로만 두세요.

업스트림은 실패 시 닫히는 방식입니다. loopback이 아닌 곳에 바인딩하면 인증 provider 없이는 대시보드가 시작되지 않습니다. `--insecure`와 `HERMES_DASHBOARD_INSECURE`는 폐기된 no-op이라 인증 게이트를 끄지 못합니다.

## 구성

```
브라우저 ──https──> ingress-nginx ──> Service :9119 ──> hermes 대시보드 (s6 서비스)
   │                                                    `gateway run`과 같은 파드
   └── 로그인 리다이렉트 ──> authentik (공개 PKCE 클라이언트, 비밀값 없음)
```

- 대시보드는 이미지 안의 s6 서비스이고 `dashboard.enabled`로 켭니다. 이 값이 `HERMES_DASHBOARD=1`을 렌더링합니다. `env`에 `HERMES_DASHBOARD`를 직접 넣는 것보다 차트 값을 쓰세요. 차트 값을 써야 readiness probe, 자동으로 만들어지는 `public_url`과 `trusted_proxies`, 인증 provider 검사가 함께 적용됩니다.
- Hermes는 authentik에 PKCE를 쓰는 **공개** 클라이언트로 등록됩니다. 클라이언트 시크릿이 없으므로 블루프린트는 평범한 ConfigMap이고 봉인할 것이 없습니다. issuer와 client id도 비밀이 아닙니다.
- 차트는 모두 `values`로 렌더링하므로 차트를 바꿀 필요가 없습니다. 차트 1.21.0에서 쓸 수 있고, 예시도 이 버전을 씁니다.

## 중요한 값

| 값 | 이유 |
| --- | --- |
| `dashboard.enabled: true` | 대시보드를 시작하고 TCP readiness probe를 붙여서, 시작하는 동안 Ingress가 502를 내지 않게 합니다. |
| `dashboard.auth.provider: oidc` | issuer나 client id가 없으면 503을 내는 Ingress를 남기는 대신 차트 렌더링이 실패합니다. |
| `config.dashboard.oauth.self_hosted.issuer` | `https://authentik.app.jyje.online/application/o/<slug>/`입니다. slug는 authentik 애플리케이션의 slug입니다. |
| `config.dashboard.oauth.self_hosted.client_id` | 블루프린트 provider의 `client_id`와 같아야 합니다. |
| `dashboard.trustedProxies` | `X-Forwarded-*`를 보내도 되는 네트워크입니다. ingress-nginx가 여러 노드의 호스트 네트워크에서 돌기 때문에 노드 네트워크 **와** 파드 네트워크를 모두 넣으세요(여기서는 `10.0.4.0/24`와 `10.1.0.0/16`). 하나만 넣으면 요청이 들어온 노드에 따라 세션 쿠키에서 `Secure`가 빠지는데, 경고도 없습니다. |
| `service.enabled: true`와 `ingress` | 차트는 리스너를 스스로 노출하지 않습니다. |
| `ingress.hosts[0].host`와 `tls` | `public_url`은 첫 host에서 만들어집니다(`tls`가 있으면 https). `/auth/callback`만 뺀 값이 authentik에 등록한 redirect URI와 같아야 합니다. |

Homer는 Ingress 어노테이션으로 카드를 찾습니다. 차트가 모든 인스턴스에 `app.kubernetes.io/name: hermes-agent` 라벨을 붙이므로, Homer `ingressSelector`에 한 줄이면 전부 포함됩니다. Ping `type`은 넣지 마세요. 페이지가 로그인 뒤에 있습니다.

## 적용 순서

1. **DNS**: 다른 `*.app.jyje.online` 레코드가 쓰는 대상으로 `<host>`의 CNAME을 만듭니다. 인증서는 HTTP-01로 발급되므로 이름이 먼저 풀려야 합니다. 와일드카드 레코드는 없습니다.
2. **병합**합니다. Argo CD가 에이전트를 동기화하고 authentik worker가 블루프린트를 적용합니다.
3. **authentik 확인**: 블루프린트 인스턴스가 성공으로 보고되어야 하고, 애플리케이션과 provider가 있어야 합니다. flow slug나 서명 키가 없으면 이 블루프린트만 실패하고 authentik은 계속 동작합니다.
4. **에이전트 확인**: 9119 포트가 열리면 파드가 Ready가 됩니다. 첫 시작에는 번들 skill이 볼륨에 동기화되는 동안 몇 분이 걸릴 수 있고, 네트워크 스토리지에서는 더 걸립니다.
5. **로그인 확인**(아래).
6. **후속 변경**: `bootstrap.overwrite`를 `false`로 되돌립니다.

### `bootstrap.overwrite`가 일회성인 이유

`public_url`, `trusted_proxies`, OIDC issuer는 볼륨이 처음 시드될 때만 `config.yaml`에 기록되고, `bootstrap.overwrite`의 기본값은 `false`입니다. 그래서 이후 동기화에서 host나 `dashboard.*` 값을 바꿔도 파드에 반영되지 않고, 오래된 `public_url`은 로그인 콜백을 깨뜨립니다. 값을 바꾸는 동기화에서만 `bootstrap.overwrite: true`로 두세요. 이 값은 `config.yaml`(과 설정된 `SOUL.md`)을 렌더링된 내용으로 덮어쓰므로, 에이전트가 런타임에 바꾼 설정은 사라집니다. 중요하다면 먼저 복사해 두고, 다음 변경에서 `false`로 되돌리세요. 켜 둔 채로 두면 동기화할 때마다 파일이 다시 덮어써집니다.

## 확인

세션이 없으면 `GET /`는 로그인 페이지로 리다이렉트하고 `/api/env`, `/api/config`는 401을 줍니다. 바인딩된 그룹의 구성원으로 로그인한 뒤 `GET /api/auth/me`가 provider를 알려 주고, 세션 쿠키는 `__Host-`, `Secure`, `HttpOnly`입니다. 브라우저에서도 확인하세요.

- 세션 쿠키에 `Secure`가 붙어 있는지 확인합니다(없으면 `trustedProxies`가 대시보드가 보는 주소와 맞지 않는 것입니다).
- 바인딩된 그룹 밖의 사용자는 authentik에서 막히고 대시보드에 도달하지 못해야 합니다.

## 문제 해결

| 증상 | 가능한 원인 |
| --- | --- |
| `GET /auth/login`이 503 | issuer가 틀렸습니다. 대시보드 응답 본문에 이유가 나오지만(예: "OIDC discovery returned 404") 커스텀 오류 페이지가 있는 프록시는 일반 503으로 바꿀 수 있으니 Service에 직접 요청해서 보세요. 끝의 슬래시 차이는 허용됩니다. |
| 로그인이 `/auth/callback?error=invalid_request`("The request is otherwise malformed")로 돌아옴 | provider가 허용하는 grant type이 없습니다. 블루프린트로 만든 provider는 `grant_types`를 지정하지 않으면 비어 있습니다. authentik 서버 로그에 `Invalid grant_type for provider`가 남습니다. provider에 `grant_types: [authorization_code, refresh_token]`을 추가하세요. |
| authentik이 "Unregistered redirect_uri"를 표시 | 블루프린트의 redirect URI가 `public_url` + `/auth/callback`과 다릅니다. host를 바꾼 뒤에 흔합니다. |
| host를 바꾼 뒤 콜백 실패 | `config.yaml`의 `public_url`이 오래되었습니다. `bootstrap.overwrite: true`로 한 번 동기화하세요. |
| 롤아웃 직후 Ingress가 502 | 파드가 아직 시작 중입니다(skill 동기화). Ready가 될 때까지 기다리세요. readiness probe가 그때까지 Ingress를 붙이지 않습니다. |
| 파드가 Ready가 되지 않음 | 인증 provider가 없어 대시보드가 닫힌 채로 실패했습니다. issuer, client id, `dashboard.auth.provider`를 확인하세요. |
| 쿠키에 `Secure`가 없음 | `trustedProxies`에 노드 네트워크나 파드 네트워크가 빠졌습니다. 둘 다 넣으세요. |
| `networkPolicy`를 켠 뒤 Ingress 타임아웃 | 정책이 모든 인바운드를 막고, 호스트 네트워크 컨트롤러는 파드/네임스페이스 셀렉터에 걸리지 않습니다. `networkPolicy.extraIngress`에서 노드 네트워크와 파드 네트워크 모두에 9119 포트를 허용하세요. 차트에 측정된 예시 [`values-networkpolicy-dashboard.yaml`](../../helm/hermes-agent/hermes-agent-1.21.0/values-networkpolicy-dashboard.yaml)이 있습니다. henry는 지금 켜져 있지 않습니다. |
| Homer 카드가 없음 | Homer `ingressSelector`에 `hermes-agent`가 없거나, Ingress에 Homer 어노테이션이 없습니다. |
| 블루프린트가 적용되지 않음 | 이 클러스터에서 기본 flow slug나 자체 서명 키 쌍의 이름이 다릅니다. 블루프린트의 이름을 고치세요. 다른 블루프린트는 영향이 없습니다. |

## 다른 에이전트에 대시보드 추가하기

1. 예시 파일 두 개를 복사하고 "example"을 모두 바꿉니다. host, issuer slug, client id, redirect URI가 서로 일치해야 합니다.
2. `authentik.yaml`의 `additionalObjects`에 블루프린트 ConfigMap을 추가하고 `blueprints.configMaps`에도 올립니다.
3. DNS 레코드를 만듭니다(적용 순서 1단계).
4. Homer `ingressSelector`에는 이미 `hermes-agent`가 들어 있습니다.
5. 위 적용 순서를 따릅니다. 새 인스턴스는 첫 시작에 이 값들로 볼륨이 시드되므로 `bootstrap.overwrite`가 필요 없어서 예시에서도 주석 처리해 두었습니다. 이미 볼륨이 있는 에이전트만 이 값이 필요하고, 그 경우 되돌리는 후속 변경까지 함께 합니다.
