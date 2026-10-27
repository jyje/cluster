# pifanctl: 작업자를 전용 네임스페이스로 옮기기

English version: [pifanctl-worker-namespace.md](pifanctl-worker-namespace.md)

## 이유

하드웨어 작업자와 온도 에이전트는 hostPath 볼륨이 필요한데, 이는 Pod Security
수준 `privileged`만 허용합니다. 지금은 오퍼레이터와 같은 네임스페이스에서 돌기
때문에 그 네임스페이스를 제한(restricted)할 수 없습니다. 이 변경은 작업자와
에이전트에게 전용 네임스페이스를 주고, 오퍼레이터는 자기 네임스페이스에 Lease와
Event 권한만 남깁니다.

pifanctl 이슈 #91의 2단계입니다. 1단계(같은 네임스페이스에서 1.2.2에서 1.5.1로)는
끝났고 검증되었습니다. 2단계는 2026-10-27에 적용되어 검증되었습니다("관찰된 것"
참고). **이런 변경은 유지보수 창 밖에서 반복하지 마세요.** 최신 하트비트를 가진
작업자가 없는 동안 Fan은 `AwaitingWorker`로 보고하고 온도가 오릅니다.

## 변경 내용

| 객체 | 릴리스 네임스페이스 `pifanctl` | 새 `pifanctl-workers` |
|------|-------------------------------|-----------------------|
| 네임스페이스(`privileged` 레이블, Git에서 지워도 유지) | | 생성 |
| 오퍼레이터 Deployment | 유지, `--worker-namespace pifanctl-workers` 인자 추가 | |
| 오퍼레이터 Role | `events`와 `leases`만 남음 | |
| Deployment, Pod, ConfigMap용 Role과 RoleBinding | 제거 | 생성 |
| 에이전트 DaemonSet, 작업자 Service, 에이전트 Service | 옛 객체는 삭제할 때까지 남음 | 생성 |
| ServiceMonitor, 작업자 NetworkPolicy | 옛 객체는 삭제할 때까지 남음 | 생성 |
| 하드웨어 작업자 Deployment | 옛 것은 삭제할 때까지 남음 | 오퍼레이터가 생성 |

여기서는 Argo CD가 prune하지 않으므로(prune 없는 자동 동기화) 옛 객체는 손으로
지울 때까지 남고, 그동안 Application이 `OutOfSync`로 보입니다. 작업자 Deployment는 오퍼레이터가 만들므로 Argo CD 소유가
아닙니다.

## 창을 열기 전에

1. 유지보수 창 승인과 현재 상태를 Git 밖에 보관한 사본.
2. `Fan`이 `Regulating`, `CoolingZone`이 `Ready`, `nodeTemperatures`의 모든 멤버가 `Fresh`.
3. Prometheus가 모든 네임스페이스의 ServiceMonitor를 선택합니다. 확인했습니다: `serviceMonitorNamespaceSelector`가 비어 있고 선택자는 `release=prometheus`이며 ServiceMonitor가 그 레이블을 갖고 있습니다.
4. 독립적인 냉각 복구 수단 준비.

## 절차

1. PR을 병합합니다. Argo CD가 네임스페이스를 만들고, 오퍼레이터를 새 인자로 재시작하고, Role을 바꾸고, 새 에이전트, Service, ServiceMonitor, NetworkPolicy를 만듭니다.
2. 공백은 옛 작업자를 삭제할 때가 아니라 오퍼레이터가 새 인자로 재시작할 때 시작됩니다. 그때부터 Fan이 `AwaitingWorker`로 보고합니다. 옛 작업자가 호스트 잠금을 잡고 있는 동안 새 작업자는 팬을 제어하지 못하므로, 병합 직후 다음 명령을 바로 실행할 수 있게 준비하세요.
3. 잠금이 풀리도록 옛 하드웨어 작업자를 먼저 삭제합니다.

```sh
kubectl -n pifanctl get deploy
kubectl -n pifanctl delete deploy <옛-작업자-deployment>
```

4. 옛 작업자를 삭제하고 약 22초 뒤 새 작업자가 Ready가 되었습니다. 공백 동안 팬이 100%로 돌았다고 가정하지 마세요. 그동안 Fan은 듀티와 RPM을 보고하지 않았고 온도가 올랐습니다("관찰된 것" 참고).
5. 릴리스 네임스페이스의 나머지 옛 객체를 이름으로 삭제합니다.

```sh
kubectl -n pifanctl delete ds pifanctl-v1-staging-operator-agent
kubectl -n pifanctl delete svc pifanctl-v1-staging-operator-agent pifanctl-v1-staging-operator-worker
kubectl -n pifanctl delete servicemonitor pifanctl-v1-staging-operator-agent pifanctl-v1-staging-operator-worker
kubectl -n pifanctl delete networkpolicy pifanctl-v1-staging-operator-worker
```

6. 확인하고, 관찰하지 못한 것은 "Not measured"로 기록합니다.

```sh
kubectl get coolingzone r4spi-rack -o yaml     # 모든 멤버의 nodeTemperatures가 Fresh
kubectl get fan                                # Ready, 듀티가 곡선으로 복귀
kubectl -n pifanctl-workers get pods
```

Prometheus에 새 타깃이 보이고 옛 타깃이 사라졌는지도 확인합니다.

## 관찰된 것 (2026-10-27 적용, UTC)

| 시점 | 관찰 |
|------|------|
| PR 병합 | 11:51:31 |
| 옛 작업자를 지우기 직전 첫 샘플의 Fan 상태 | `AwaitingWorker`, 듀티와 RPM 없음 |
| 옛 작업자 삭제 | 약 11:52:58 |
| Fan이 다시 `Regulating` | 삭제 후 27초 이내(11:53:25), 듀티 95% |
| 이후 듀티 | 55%, 42.7%, 41.3%로 곡선에 복귀 |
| 제어 온도 | 전 49.6 °C, 첫 `Regulating` 샘플에서 **54.55 °C**, 약 35초 뒤 50.15 °C |

공백은 대략 30초에서 75초 사이였습니다. 온도가 약 5 °C 올랐는데 이는 팬이 100%로 돌았던 것처럼 보이지 않지만, 공백 동안의 팬 속도는 **측정하지 못했습니다**. 창을 계획할 때 이를 염두에 두고 온도를 지켜보세요.

이전 후: `nodeTemperatures` 멤버 4개가 모두 `Fresh`, `CoolingZone`이 Ready와 Regulating, 타코미터 1014 RPM, Argo CD `Synced`와 `Healthy`, 오퍼레이터 로그에 오류 없음.

## 롤백

PR을 되돌립니다. 오퍼레이터가 릴리스 네임스페이스로 돌아와 그곳에 작업자를 만듭니다.
그 뒤 `pifanctl-workers`의 객체를 삭제합니다. 같은 안전 듀티 공백이 다시 생깁니다.

## 이전 후 (별도의 나중 변경)

- 릴리스 네임스페이스에 `pod-security.kubernetes.io/enforce: restricted` 레이블을 붙입니다(예: `managedNamespaceMetadata`). 옛 작업자와 에이전트가 사라진 뒤에만 합니다. 그렇지 않으면 그곳의 새 Pod가 거부됩니다.
- `workerAdmission.enabled: true`로 켜고 실제 작업자가 승인되는지 확인합니다.
- 선택으로 한 노드에서 먼저 `networkPolicy.workerEgress.enabled: true`를 켜고 `nodeTemperatures`가 `Fresh`로 유지되는지 확인합니다.

## 시험

| 확인 | 결과 |
|------|------|
| 고정된 차트 커밋에서 현재 값과 새 값으로 `helm lint`, `helm template` | 통과 |
| 렌더링 목록 | 에이전트 DaemonSet, Service, ServiceMonitor, NetworkPolicy가 새 네임스페이스로 이동. Role, RoleBinding, Namespace 신규 |
| 오퍼레이터 인자 | `--worker-namespace pifanctl-workers` |
| 릴리스 네임스페이스의 오퍼레이터 Role | `events`와 `leases`로 축소. Deployment, Pod, ConfigMap 규칙은 작업자 Role로 이동 |
| 작업자 NetworkPolicy 인그레스 | 릴리스 네임스페이스와 `observability`에서 |
| 라이브 클러스터 대비 서버 측 비교(릴리스 네임스페이스와 클러스터 범위) | 차이는 셋뿐: 오퍼레이터 인자, 축소된 Role, 새 Namespace |

이전 후 실제 랙에서 확인한 것: 인그레스 규칙이 Calico에서 동작함(오퍼레이터가
네임스페이스를 가로질러 모든 에이전트를 읽고 멤버가 `Fresh`), Prometheus가 새
네임스페이스의 타깃 5개를 수집하고 옛 네임스페이스에는 없음, Argo CD가 오류 없이
수렴, 작업자가 네임스페이스를 가로질러 확인 응답함.

측정하지 못한 것: 공백 동안의 팬 속도와 PWM 듀티. 프로브가 붙어 있지 않습니다.
