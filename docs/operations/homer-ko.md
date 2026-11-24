# Homer 대시보드

`https://app.jyje.online`의 시작 페이지는 Homer 대시보드입니다. homer-operator가 `Dashboard` 리소스 하나로 만들며, 카드는 모두 그 리소스에 직접 적습니다. 자동 발견은 꺼져 있습니다.

## 위치

| 항목 | 위치 |
| :-- | :-- |
| 오퍼레이터 | Application `homer-operator` |
| Dashboard 리소스와 카드 | `clusters/r4spi/apps/homer-instance.yaml`의 `Dashboard`(이름 `homer`), `homerConfig.services` |
| 네임스페이스 | `homer-instance` |

## 카드 추가와 수정

`homer-instance.yaml`의 `homerConfig.services`를 고칩니다. 카드는 그룹 안의 항목 하나입니다.

```yaml
- parameters:
    name: "Airflow"
    logo: "https://example.com/logo.svg"
    subtitle: "Workflow scheduler"
    tag: "airflow #workflow #dag"
    url: "https://airflow.app.jyje.online"
    type: "Ping"
```

- `type: "Ping"`은 상태 표시를 보여 줍니다. `endpoint`가 없으면 `url`로 요청합니다. 루트 페이지가 404를 돌려주거나 로그인이 필요해서 상태 신호로 부적절하면 `endpoint`(필요하면 `method: "GET"`도)를 지정합니다. 이 점검은 브라우저에서 실행되므로 엔드포인트가 대시보드 출처를 허용해야 합니다.
- 태그는 하나의 규칙을 따릅니다. 앱 이름이 먼저 오고, 뒤에 성격을 설명하는 단어 2~4개가 옵니다. 예: `n8n #workflow #automation #cicd`.
- 한 그룹 안에서는 이름순으로 정렬됩니다. `order: "-1"`은 카드를 맨 아래로 보내며, homer-operator 1.2.4가 필요합니다.
- 그룹 이름에는 번호가 붙습니다(`1. Applications`, `2. Dashboards`, `3. Management`, `4. External Links`). 오퍼레이터가 그룹을 이름순으로 정렬하므로 번호가 순서를 정하는 유일한 방법입니다. 카드를 어느 그룹에 넣으려면 정확히 그 이름을 씁니다.

Helm 값은 Application 안에 있으므로, 변경을 병합한 뒤 `apps`를 먼저 동기화하고 그다음에 `homer-instance`를 동기화합니다.

## 자동 발견은 꺼져 있습니다

오퍼레이터는 Ingress 어노테이션(`item.homer.rajsingh.info/*`)으로 카드를 만들 수 있습니다. 이 클러스터는 더 이상 그 방식을 쓰지 않습니다.

끈 이유:

- 읽을 Ingress를 `ingressSelector`의 `app.kubernetes.io/name` 허용 목록으로 골랐습니다. 새 앱마다 두 곳을 고쳐야 했고, 목록에 없는 앱은 아예 나타나지 않았습니다. Airflow가 그렇게 빠졌습니다.
- 이름 목록은 대시보드를 정확하게 유지하는 데 도움이 되지 않았고, 거의 모든 카드가 어차피 직접 관리되고 있었습니다.

끄는 방법:

- 오퍼레이터에는 발견을 끄는 스위치가 없고, 선택자를 비우면 "전부 매칭"입니다. 그래서 `ingressSelector`와 `httpRouteSelector`가 모두 라벨 `homer.jyje.online/discovery: enabled`를 매칭하게 했습니다. 그 라벨을 가진 것이 없으므로 아무것도 발견되지 않습니다.
- Service는 `serviceSelector`가 있어야만 발견되는데, 설정하지 않았습니다.

앱들의 Ingress에 남아 있는 Homer 어노테이션은 무시됩니다. 해롭지 않고 카드 문구의 기록으로 남겨 두었습니다.

Ingress를 다시 발견시키려면 그 Ingress에 라벨 `homer.jyje.online/discovery: enabled`와 `item.homer.rajsingh.info/*`, `service.homer.rajsingh.info/name` 어노테이션을 붙입니다. 같은 그룹 이름의 발견된 카드는 수동 그룹에 합쳐집니다. 같은 카드를 수동으로도 적어 두면 두 번 보이니 하나만 둡니다.

## 변경 후 확인

- Argo CD에서 `homer-instance`가 Synced, Healthy입니다.
- 렌더링된 설정에 기대한 카드가 들어 있습니다.

  ```bash
  kubectl -n homer-instance get cm homer-homer -o jsonpath='{.data.config\.yml}'
  ```

- 대시보드를 열어 새 카드와 링크, 상태 표시를 확인합니다.
