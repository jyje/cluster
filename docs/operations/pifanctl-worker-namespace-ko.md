# pifanctl: 작업자를 전용 네임스페이스로 옮기기

English version: [pifanctl-worker-namespace.md](pifanctl-worker-namespace.md)

## 이유

하드웨어 작업자와 온도 에이전트는 hostPath 볼륨이 필요한데, 이는 Pod Security
수준 `privileged`만 허용합니다. 지금은 오퍼레이터와 같은 네임스페이스에서 돌기
때문에 그 네임스페이스를 제한(restricted)할 수 없습니다. 이 변경은 작업자와
에이전트에게 전용 네임스페이스를 주고, 오퍼레이터는 자기 네임스페이스에 Lease와
Event 권한만 남깁니다.

pifanctl 이슈 #91의 2단계입니다. 1단계(같은 네임스페이스에서 1.2.2에서 1.5.1로)는
끝났고 검증되었습니다. **유지보수 창 밖에서 병합하지 마세요.** 최신 하트비트를 가진
작업자가 없는 동안 팬은 안전 듀티로 동작합니다.

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
2. 옛 작업자가 호스트 잠금을 잡고 있는 동안 새 작업자는 팬을 제어하지 못합니다. 새 에이전트가 보고할 때까지 멤버가 `Unavailable`로 보입니다. 이는 안전 동작을 바꾸지 않습니다.
3. 잠금이 풀리도록 옛 하드웨어 작업자를 먼저 삭제합니다.

```sh
kubectl -n pifanctl get deploy
kubectl -n pifanctl delete deploy <옛-작업자-deployment>
```

4. 새 작업자가 최신 하트비트를 가질 때까지 팬은 안전 듀티(100%)로 동작합니다. 1.2.2에서 1.5.1로 작업자를 교체할 때는 10초 간격 폴링 기준 약 30초였습니다. 보장이 아니라 규모 감각으로 보세요.
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

시험하지 않은 것: 실제 CNI(Calico가 정책을 강제함)에서의 작업자 NetworkPolicy 인그레스,
GPIO가 동작하는 노드에서 네임스페이스를 가로지르는 작업자 확인 응답, 두 네임스페이스
객체의 Argo CD 적용 순서, 안전 듀티 공백의 실제 길이. 작업 PC 디스크가 거의 가득 차서
일회용 클러스터 시험은 하지 못했습니다.
