# pifanctl: 노드 온도와 팬 제어

[English](pifanctl.md) | [한국어](pifanctl-ko.md)

## 개요

[pifanctl](https://github.com/jyje/pifanctl)은 클러스터의 PWM 팬을 제어하고
모든 노드의 온도를 기록합니다.

| 구성 | 위치 | 하는 일 |
| --- | --- | --- |
| `agent` | 모든 노드의 DaemonSet | `pifanctl_temperature_celsius{node,zone,type}` 발행 |
| `controller` | 팬이 달린 노드의 DaemonSet | 가장 뜨거운 노드(`max(pifanctl_temperature_celsius)`) 기준으로 팬 구동 |
| Prometheus | `observability` | 온도를 30일 보관 |
| 대시보드, 알림 | Grafana, Prometheus | `Hardware / pifanctl` 대시보드와 `Pifanctl*` 알림 |

`clusters/r4spi/apps/pifanctl.yaml`에 선언되어 있고, pifanctl 저장소가 발행한
차트를 벤더링해서(`helm/pifanctl/pifanctl-<version>`) 사용합니다.

컨트롤러는 한 가지 소스에만 의존하지 않습니다. 매 주기마다 클러스터 값과 자기
노드 값 중 높은 쪽을 쓰고, Prometheus에 닿지 못하면 자기 노드를, 아무것도 읽을
수 없으면 팬을 최대 속도로 돌립니다. 컨트롤러가 멈추면 팬은 최대 속도로 남습니다.

## 일상 운영

- **팬이 클러스터를 따르고 있나?** 대시보드의 "Where the controller got its
  temperature"가 계속 `prometheus`여야 합니다. `local`은 Prometheus를 잃었다는
  뜻이고 `failsafe`는 센서를 전혀 읽지 못한다는 뜻입니다.
- **팬이 달린 노드 추가.** `pifanctl.yaml`의 `controllers`에 자체 `nodeSelector`를
  가진 그룹을 추가합니다. 노드는 최대 한 그룹에만 일치해야 하며, 라즈베리 파이
  5는 `driver: sysfs`를 쓰세요.
- **곡선 조정.** `controllerDefaults.curve`(또는 그룹별): `tempLow` 미만은 유휴,
  `tempHigh`에서 `dutyMax`까지 선형 증가, `dutyDownStep`만큼 히스테리시스.
- **업그레이드.** 새 차트를 `helm/pifanctl/`에 벤더링하고(`helm-chart-vendor`
  스킬 참고) `pifanctl.yaml`의 경로를 바꿉니다.

## 보관(Retention)

Prometheus는 30일을 보관하며 18 GB 상한을 둡니다(`lgtm-prometheus.yaml`). TSDB는
7일에 약 4 GB였으므로 30일은 대략 17 GB입니다. 상한은 20Gi 볼륨 요청보다 살짝
작아서, TSDB가 예상보다 커져도 디스크를 채우지 않고 오래된 블록부터 지웁니다.
에이전트는 한 달에 수백 KB 정도만 더하므로 용량은 다른 워크로드가 좌우합니다.
30일을 넘는 이력은 recording rule `pifanctl:node_temperature_max_celsius:max`를
장기 저장소로 보내세요.

## 롤아웃: 손으로 적용한 Deployment 교체

git에 선언하기 전의 pifanctl은 `pifanctl` 네임스페이스에 직접 적용한
Deployment(업스트림 매니페스트를 `kubectl apply`한 뒤 수정)로 돌았습니다. 이
Deployment는 Argo CD 소유가 아니라서 Argo CD가 지우지 않습니다.

**이 단계가 수동인 이유.** Argo CD는 자기가 만들지 않은 객체를 prune하지 않습니다.
기존 Deployment와 새 컨트롤러가 같은 팬 핀을 동시에 구동하게 되므로 기존 것을
치워야 하는데, git에 기술된 적 없는 객체의 1회성 삭제는 git으로 표현할 수 없습니다.

**선행 조건**(이 순서대로):

1. pifanctl PR이 병합되어 `ghcr.io/jyje/pifanctl:v<appVersion>` 이미지와 차트가
   발행됨.
2. cluster PR이 병합되고 `pifanctl` Application이 동기화됨. 모든 노드에서 agent
   Pod가 실행 중인지 확인.

**절차.**

```sh
# 1. 롤백용으로 현재 상태를 저장
kubectl get deployment pifanctl -n pifanctl -o yaml > pifanctl-legacy-deployment.yaml

# 2. 핀을 구동하는 프로세스가 하나만 남도록 기존 컨트롤러 제거
kubectl delete deployment pifanctl -n pifanctl

# 3. 새 컨트롤러(DaemonSet pifanctl-controller-default)가 인계
kubectl get pods -n pifanctl -o wide
kubectl logs -n pifanctl -l app.kubernetes.io/component=controller --tail=20
```

**확인.** 컨트롤러 로그에 모든 노드의 온도와 따라가는 노드(`*` 표시)가 보이고,
대시보드에 모든 노드의 데이터가 있으며 `pifanctl_fan_duty_percent`가 보고됩니다.

```
Duty: 86.3%, Temperature: 70.5°C, Following: raspi-51, Source: prometheus, Nodes: raspi-51=70.5* raspi-41=52.1 raspi-50=51.8 raspi-40=49.2
```

**롤백.** git에서 `controllers.default.enabled: false`로 컨트롤러를 끄고 1단계에서
저장한 파일을 `kubectl apply -f` 합니다. 에이전트는 그대로 둬도 됩니다.

## 롤아웃 완료

2026-10-01에 롤아웃했습니다. `pifanctl` Application이 동기화된 뒤 손으로 적용했던
Deployment를 제거했고, 그 이후 컨트롤러는 클러스터 최고 온도를 기준으로 팬을
구동합니다. 실제 보드에서만 드러난 것이 두 가지 있습니다.

- **컨트롤러는 root가 필요합니다.** 이미지는 non-root 사용자로 실행되지만
  `RPi.GPIO`는 `/dev/mem`을 매핑합니다. non-root면 `No access to /dev/mem`으로
  크래시 루프에 빠집니다. 차트 0.1.2는 기본값으로 root로 실행합니다.
- **그룹의 `nodeSelector`는 적은 그대로 쓰입니다.** 차트 0.1.0은 자체 기본
  라벨과 병합해서 어떤 노드와도 일치하지 않았고, DaemonSet이 에러 없이 파드가
  0개였습니다. 0.1.1에서 수정했습니다.

## CI 러너 (ARC)

`r4spi-microk8s` 러너 스케일 셋이 pifanctl 저장소를 담당합니다. ARC 컨트롤러와
스케일 셋을 0.14.2에서 0.15.0으로 올린 뒤 `AutoscalingRunnerSet`이 사라지고
Application이 `OutOfSync`로 남았습니다. 스케일 셋 Application에는 `selfHeal`이
없기 때문입니다. Application을 한 번 sync하자 복구되고 listener가 돌아왔습니다.
ARC 업그레이드 후에는 `kubectl get autoscalingrunnersets -n arc-system`을 확인하고,
비어 있으면 스케일 셋 Application을 sync한 뒤 워크플로 하나를 돌려 러너가 잡을
집어가는지 확인하세요.

## 시험을 위해 멈추기, 그리고 복구

같은 팬을 구동하는 시험(예: 브랜치의 새 컨트롤러)은 이 릴리스와 나란히 돌면 안 됩니다.
컨트롤러 두 개가 한 핀을 두고 다투기 때문입니다. 이 릴리스를 멈출 때 함정이 둘 있습니다.

- **스케일을 내리지 말고 Application을 동결하세요.** `argocd.argoproj.io/skip-reconcile=true`는
  Argo CD가 손대지 않게 하지만, 아무것도 안 돌아가는데도 `Synced`, `Healthy`로
  보입니다. 배지가 아니라 DaemonSet을 확인하세요.
- **손으로 DaemonSet에 추가한 키는 Argo CD가 지우지 못합니다.** `kubectl patch`로 넣은
  `nodeSelector` 항목은 다른 field manager 소유라서, sync하면 이미지는 복구되지만 그
  항목은 남아 파드가 0개로 유지됩니다.

**복구가 수동인 이유.** 멈춘 상태와 시험이 git 밖에서 적용되어, 수렴할 git 정의가
없습니다. 되돌리기 전에 팬을 구동하는 다른 Application이 있는지
(`kubectl get applications -n argocd | grep -i pifan`, 팬 노드의 privileged 파드) 먼저
확인하세요. 시험이 도는 중에 동결을 풀면 핀에 두 번째 컨트롤러가 뜹니다.

**절차 (시험이 끝났거나 폐기된 뒤).**

```sh
# 1. 시험 제거. 직접 만든 Application에는 finalizer가 없으므로 커스텀 리소스를 먼저
#    지우고(오퍼레이터가 자기 finalizer를 정리), 네임스페이스, 클러스터 범위 객체 순으로
#    지웁니다. Grafana CRD는 건드리지 마세요.
kubectl delete application <trial-app> -n argocd
kubectl delete <trial-custom-resources> --all -A
kubectl delete namespace <trial-namespace>
kubectl delete crd <trial-crds>
kubectl delete clusterrole,clusterrolebinding <trial-rbac>

# 2. 이 릴리스의 동결을 풀고 git 정의로 DaemonSet을 다시 만듭니다.
kubectl annotate application pifanctl -n argocd argocd.argoproj.io/skip-reconcile-
kubectl delete ds pifanctl-agent pifanctl-controller-default -n pifanctl
kubectl patch application pifanctl -n argocd --type merge -p '{"operation":{"sync":{}}}'
```

Argo CD는 이미 sync한 리비전에 대해 삭제된 객체를 스스로 다시 만들지 않으므로
명시적 sync가 필요합니다. `PrometheusRule`과 `GrafanaDashboard`는 이 차트를 재사용하는
시험과 이름이 같아 둘이 함께 있는 동안 Application에 `SharedResourceWarning`이 뜨며,
시험을 제거하면 이 릴리스로 돌아옵니다.

**확인.** 에이전트와 컨트롤러가 모두 git의 이미지로 `Running`이고, 컨트롤러 로그가
가장 뜨거운 노드를 따라가며, 모든 `pifanctl-*` 타깃의 `up`이 1이고, `Pifanctl*` 알림이
없어야 합니다.
