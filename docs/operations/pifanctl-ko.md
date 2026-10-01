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
