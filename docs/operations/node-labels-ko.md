# 노드 라벨

English version: [node-labels.md](node-labels.md)

노드 라벨은 `node-labels` Application(`clusters/r4spi/apps/node-labels.yaml`)으로 Argo CD가
관리합니다. `kubectl label`로 직접 붙이지 마세요.

## 라벨의 의미

라벨은 노드에 붙는 `키=값` 꼬리표입니다. 워크로드는 `nodeSelector`(정확히 일치)나 노드
어피니티로 노드를 고릅니다. 모든 키는 `app.jyje.online` 도메인 하나를 씁니다.

| 키 | 값 | 의미 |
| --- | --- | --- |
| `app.jyje.online/node.family` | `raspberry-pi` | 하드웨어 계열 |
| `app.jyje.online/raspi.ram` | `8g` | RAM 크기 |
| `app.jyje.online/raspi.type` | `4b`, `5b` | Pi 모델: Pi 4(4KB 페이지, 느린 코어) 또는 Pi 5(빠른 코어) |

현재 노드: `raspi-40`, `raspi-41`은 `4b`이고 `raspi-50`, `raspi-51`은 `5b`입니다.

라벨은 우열이 아니라 하드웨어 종류를 나타냅니다. 어떤 소프트웨어는 한 종류가 필요합니다.
Envoy와 게임 서버는 `5b` 노드에서 실행하고, Envoy는 4KB 페이지 노드에서 힙을 매핑하지 못하며,
qdrant는 `4b`에 고정돼 있습니다.

## 관리 방식

- 노드마다 이름과 `app.jyje.*` 라벨만 적은 `Node` 매니페스트가 있고, `manifest-group` 차트로
  렌더링합니다. kubelet과 다른 컨트롤러가 붙이는 라벨은 선언하지 않습니다.
- 서버 사이드 적용으로 Argo CD는 선언한 키만 소유합니다.
- 모든 Node에 `argocd.argoproj.io/sync-options: Prune=false,Delete=false`가 있어서,
  Application을 지워도 Argo CD가 Node를 prune하거나 삭제하지 않습니다.
- Application은 자동 동기화가 없습니다. 병합 뒤에는 `apps`를 먼저 동기화하고(라벨이
  Application 리소스 안에 있습니다) 그다음 `node-labels`를 동기화합니다.

## 라벨 바꾸기

1. `clusters/r4spi/apps/node-labels.yaml`에서 노드의 `labels`를 고치고 병합합니다.
2. `apps`, 그다음 `node-labels`를 동기화합니다.
3. Git에서 키를 지워도 Argo CD가 유일한 소유자일 때만 노드에서 지워집니다. `kubectl label`로
   처음 붙인 키는 그 도구가 계속 소유하므로 한 번 직접 지웁니다:
   `kubectl label node <이름> <키>-`.

## 노드 추가와 교체

노드가 조인하기 전이나 직후에 정확한 이름의 `Node` 항목을 추가하고 동기화합니다. 노드가 클러스터를
완전히 떠나면 그 항목도 지웁니다. 남겨 두면 Argo CD가 존재하지 않는 노드의 빈 Node 객체를 만듭니다.

노드를 빼고 다시 조인해도 라벨은 Git에서 오므로 다음 동기화가 돌면 바로 복구됩니다. 그 전까지는
그 라벨로 선택하는 워크로드가 그 노드에 스케줄되지 않습니다.

## 이력

라벨은 예전에 수동으로 붙였고 두 도메인으로 나뉘어 있었습니다(Pi 4 노드는 `app.jyje.live`, Pi 5
노드는 `app.jyje.online`). 네 단계로 옮겼습니다. 기존 라벨을 그대로 선언하고, 모든 노드에
`app.jyje.online` 키를 추가하고, qdrant와 Envoy 프록시를 그 키로 옮기고, 마지막으로
`app.jyje.live` 키를 제거했습니다(마지막 제거는 위에서 설명한 대로 `kubectl label`로 한 번 직접
지웠습니다). `app.jyje.live` 도메인은 폐기했습니다. `raspi-51`의 `5b` 라벨은 이 이전 전에 수동으로
붙였고 지금은 선언에 포함돼 있습니다.
