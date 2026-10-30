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

소유자(jyje)는 항상 authentik 슈퍼유저입니다. [`authentik.yaml`](../../clusters/r4spi/apps/authentik.yaml)의 봉인된 블루프린트 `authentik-owner`가 계정을 `AuthentikAdmin`에 유지하므로, 관리자 화면에서 손으로 승격할 필요가 없습니다.

- **사용자 이름이 아니라 검증된 이메일로 매칭합니다.** 사용자 이름은 Google 가입 때 본인이 정하므로, 이름으로 매칭하면 빈 `jyje`를 먼저 잡은 사람에게 역할이 넘어갑니다. 이메일은 소유자의 Google 로그인만 제시할 수 있습니다. 이메일은 봉인된 블루프린트에 있어서 공개 파일에는 없습니다.
- **계정이 없으면 블루프린트가 만듭니다.** 소유자의 이메일로 만들고, 같은 이메일로 첫 Google 로그인을 하면 소스가 이메일로 계정을 연결하므로 그 계정에 붙습니다. 그러면 따로 할 일 없이 역할이 있습니다.
- **소유자가 먼저 가입했다면** 새 계정은 `Unknown`에 들어가고, 다음에 블루프린트가 적용될 때 이메일로 계정을 찾아 승격합니다. 로그인은 적용을 일으키지 않습니다. authentik은 새 블루프린트 파일과 바뀐 파일을 약 한 시간에 한 번 도는 발견 작업에서 찾습니다. `authentik-owner`를 추가한 병합 뒤에는 새 워커가 시작할 때 파일을 바로 집어내지 못했고, 이 작업이 돈 약 30분 뒤에 소유자가 승격되었습니다. 바로 승격하려면 관리자 화면(시스템, 블루프린트)에서 인스턴스를 다시 적용하세요. 아직 인스턴스가 없는 파일은 발견 작업이 한 번 돈 뒤에야 나타납니다.
- `groups` 목록은 사용자의 직접 멤버십을 대체합니다. 낮은 그룹은 계층 구조로 그대로 적용됩니다.
- Google 소스에 대한 두 가지 가정에 의존합니다. 검증된 이메일만 돌려준다는 것, 그리고 가입 흐름에서 이메일을 본인이 입력하게 하지 않는다는 것입니다. 소유자 이상의 용도로 믿기 전에 둘 다 확인하세요.
- 다른 사람은 블루프린트가 승격하지 않습니다. 관리자 화면(디렉터리, 사용자, 해당 사용자, 그룹)에서 추가하거나, 의도해서 봉인된 블루프린트에 넣으세요.
- 소유자 이메일을 바꾸려면 블루프린트를 다시 봉인([introduction.md](../introduction.md#secrets))해서 `authentik.yaml`의 `authentik-owner`를 교체하세요.

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
| 로그인했는데 소유자가 슈퍼유저가 아님 | 블루프린트가 적용되기 전에 가입했거나, 블루프린트가 새로 추가되어 매시간 도는 발견 작업이 아직 돌지 않아서 계정이 `Unknown`에 있습니다. 다음 발견 작업을 기다리거나 블루프린트 인스턴스를 다시 적용하세요(시스템, 블루프린트). "multiple users"로 실패하면 소유자 이메일을 가진 계정이 둘이라 하나를 지워야 합니다. |
| 로그인이 `invalid_request`로 돌아옴 | OAuth2 provider에 `grant_types`가 없습니다. 3번 규칙을 보세요. |
