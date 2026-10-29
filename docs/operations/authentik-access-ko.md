# authentik 접근 권한: 누가 들어가고, 새 앱은 무엇을 해야 하나

[English](authentik-access.md)

소유자 계정은 항상 authentik 슈퍼유저이고, 모든 애플리케이션 블루프린트는 이 계정을 들여보내야 합니다. 새 애플리케이션이 로그인 직후 "권한 거부됨" 화면으로 끝나지 않도록 두 가지를 설명합니다.

## 그룹

그룹은 [`authentik.yaml`](../../clusters/r4spi/apps/authentik.yaml)의 `authentik-rbac-groups` 블루프린트에 정의되어 있습니다. 그룹은 부모를 상속하므로, 아래 표에서 낮은 그룹의 구성원은 위쪽 모든 그룹의 구성원으로도 취급됩니다.

| 그룹 | 부모 | 슈퍼유저 | 의미 |
| --- | --- | --- | --- |
| `Unknown` | 없음 | 아니오 | 새로 Google 로그인한 모든 사용자가 권한 없이 들어오는 곳입니다. |
| `Viewer` | `Unknown` | 아니오 | 읽기 전용입니다. |
| `Developer` | `Viewer` | 아니오 | 일상적인 사용입니다. |
| `AuthentikAdmin` | `Developer` | **예** | authentik을 관리합니다. |
| `ClusterAdmin` | `AuthentikAdmin` | **예** | Argo CD에서도 최상위 등급입니다. |

## 소유자는 자동으로 승격됩니다

블루프린트가 `jyje`를 `AuthentikAdmin`에 넣어 두므로, 관리자 화면에서 손으로 승격할 필요가 없습니다. authentik은 블루프린트 파일이 바뀔 때 적용합니다. 로그인은 적용을 일으키지 않습니다.

- 계정 자체는 여전히 Google 가입 흐름에서 만들어집니다. 새 계정은 먼저 `Unknown`에 들어가고, 다음 적용 때 승격됩니다. 바로 승격하려면 관리자 화면(시스템, 블루프린트)에서 블루프린트 인스턴스를 다시 적용하세요.
- 블루프린트의 `groups` 목록은 사용자의 직접 멤버십을 대체합니다. 낮은 그룹은 계층 구조로 그대로 적용됩니다.
- 계정을 삭제하면 블루프린트가 빈 계정을 다시 만들고, Google 로그인은 붙을 곳이 없습니다(소스가 이메일로 계정을 연결합니다). 다른 관리자로 로그인해서 손으로 고치거나, 이메일을 블루프린트에 추가하세요.
- 다른 사람은 블루프린트가 승격하지 않습니다. 관리자 화면(디렉터리, 사용자, 해당 사용자, 그룹)에서 추가하거나, 의도해서 블루프린트에 적으세요.

## 새 애플리케이션의 규칙

애플리케이션을 그룹에 바인딩하는 것이 접근을 결정합니다. **슈퍼유저는 자동으로 허용되지 않으므로**, 좁은 그룹만 바인딩한 새 애플리케이션은 소유자를 막아 버립니다. 그래서 모든 애플리케이션 블루프린트는 다음을 지켜야 합니다.

1. **`AuthentikAdmin` 바인딩을 유지합니다.** 소유자가 들어오는 길이고, `ClusterAdmin`도 함께 들어옵니다.
2. 더 좁은 그룹은 추가 바인딩으로만 더합니다. 바인딩 중 하나라도 맞으면 애플리케이션이 열립니다.
3. provider에 필요한 값을 지정합니다. 블루프린트로 만드는 OAuth2/OpenID provider는 `grant_types`(예: `authorization_code`, `refresh_token`), redirect URI, 서명 키가 필요합니다. `grant_types`가 없으면 로그인이 `invalid_request`로 실패합니다.
4. 끝났다고 하기 전에 소유자로 확인합니다. 애플리케이션을 열어 로그인해 보세요. 로그인에 성공한 직후 "권한 거부됨"이 나오면 바인딩이 없거나 너무 좁은 것입니다.

```yaml
- model: authentik_policies.policybinding
  identifiers:
    target: !KeyOf my-app
    order: 0
  attrs:
    group: !Find [authentik_core.group, [name, AuthentikAdmin]]
```

전체 예시는 [`examples/hermes-dashboard-blueprint.yaml`](examples/hermes-dashboard-blueprint.yaml)이고, Hermes 관련 절차는 [hermes-dashboard-ko.md](hermes-dashboard-ko.md)에 있습니다.

## 문제 해결

| 증상 | 가능한 원인 |
| --- | --- |
| 로그인에 성공한 직후 "권한 거부됨" | 계정이 애플리케이션에 바인딩된 그룹에 없습니다. `AuthentikAdmin` 바인딩을 추가하거나 사용자를 그룹에 넣으세요. |
| 새로 설치했는데 소유자가 슈퍼유저가 아님 | 블루프린트가 적용될 때 계정이 아직 없었습니다. Google로 한 번 로그인한 뒤 블루프린트 인스턴스를 다시 적용하세요(시스템, 블루프린트). |
| 로그인이 `invalid_request`로 돌아옴 | OAuth2 provider에 `grant_types`가 없습니다. 3번 규칙을 보세요. |
