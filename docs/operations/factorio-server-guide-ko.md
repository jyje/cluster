# Factorio 서버 가이드

English version: [factorio-server-guide.md](factorio-server-guide.md)

`factorio` Application으로 배포한 Factorio 서버의 운영 안내입니다(롤아웃은
[envoy-factorio-cutover.md](envoy-factorio-cutover.md) 참고). 아래 코드는 스케치이므로
사용 전에 `helm template`이나 dry-run으로 확인하세요. 평문 비밀번호나 토큰은 절대
이 저장소에 커밋하지 마세요.

## 현재 서버 구성

- Pod 1개(`replicas: 1`), 전략은 `Recreate`, 저장 볼륨은 `5Gi` 하나(`factorio-data`)입니다.
- 게임은 UDP 34197에서 받습니다. Envoy `factorio` Gateway의 예약된 사설 주소로
  노출하고, 공유기 포워딩 하나가 WAN UDP 34197을 그 주소로 보냅니다. RCON과 TCP는
  없습니다.
- 설정은 ConfigMap(`overrides.json`)에서 오고, 시작 스크립트가 매번 이미지의
  `server-settings.example.json` 위에 `jq`로 덮어씁니다. `overrides.json`에 적은
  키만 바뀝니다. 설정은 시작할 때만 읽으므로 변경하면 Pod를 재시작해야 합니다.
- 자동 저장은 5분마다 3슬롯입니다. 저장 파일은 `/factorio/saves/world.zip`이고,
  시작할 때 가장 최근 저장을 불러옵니다.
- `require_user_verification`이 `true`라서 모든 플레이어에게 유효한 Factorio 계정이
  필요합니다. 서버는 공개 목록에 올리지 않습니다(`visibility.public: false`).

## 게임 비밀번호 설정

비밀번호를 `overrides.json`에 넣지 마세요. 그 ConfigMap은 공개 저장소에서 렌더링됩니다.

1. 이 저장소의 다른 시크릿과 같은 방식으로 `game_password` 키를 가진 Secret을
   SealedSecret으로 만듭니다(Application의 `extraResources` 항목, `kubeseal`로
   암호화). 값은 로컬에서 암호화합니다.

   ```yaml
   apiVersion: bitnami.com/v1alpha1
   kind: SealedSecret
   metadata:
     name: factorio-secret
   spec:
     encryptedData:
       settings.json: <kubeseal 출력, 평문 값은 절대 안 됨>
   ```

   시크릿의 값은 작은 JSON 문서입니다: `{"game_password": "..."}`.

2. 차트의 `persistence` 블록으로 ConfigMap 옆에 마운트합니다
   (`type: secret`, `objectName: factorio-secret`, `mountPath: /etc/factorio-secret`,
   `readOnly: true`).
3. 시작 스크립트의 병합에 파일을 추가합니다:
   `jq -s '.[0] * .[1] * .[2]' example.json overrides.json /etc/factorio-secret/settings.json`.
4. Application을 동기화하고 Pod가 재시작되면 클라이언트가 비밀번호를 묻습니다.
   비밀번호를 바꿀 때는 새 SealedSecret과 재시작이 필요합니다.

비밀번호는 가벼운 무단 접속을 막는 용도입니다. `require_user_verification: true`는
유지하고, 접속자를 정확히 정하려면 아래 화이트리스트를 함께 쓰세요.

## 관리자 지정

예제 설정 파일에는 `admins` 키가 없습니다. 서버는 `--server-adminlist`로 넘기는 별도
목록 파일을 읽습니다.

1. Factorio 사용자 이름의 JSON 배열(예: `["alice", "bob"]`)을 저장 볼륨의 파일이나
   ConfigMap에 둡니다. 사용자 이름은 비밀은 아니지만 저장소에 두면 공개됩니다.
2. 시작 스크립트의 `exec` 줄에 `--server-adminlist /factorio/server-adminlist.json`을
   추가하고 재시작합니다.
3. 이후 관리자는 게임 안에서 `/promote 이름`, `/demote 이름`으로 다른 사람을 승격하거나
   강등할 수 있습니다. 예제 설정에서 `allow_commands`는 `admins-only`,
   `only_admins_can_pause_the_game`은 `true`라서 명령과 일시정지는 기본적으로 관리자만
   쓸 수 있습니다.
4. 닫힌 서버로 운영하려면 화이트리스트도 추가합니다: `--use-server-whitelist`와
   `--server-whitelist /factorio/server-whitelist.json`(같은 JSON 배열 형식)입니다.
   목록의 사용자만 접속할 수 있고, 관리자가 `/whitelist`로 관리합니다.

RCON은 계속 꺼 둡니다. 위의 모든 것은 RCON 없이 동작합니다.

## 여러 게임

Factorio 서버 프로세스는 저장 파일 하나만 돌립니다. 게임이 여러 개면 프로세스도 여러
개가 필요합니다. 현실적인 구성은 두 가지입니다.

**한 번에 한 게임, 저장 여러 개(가장 저렴).** 게임마다 저장 파일(또는 볼륨)을 따로 두고,
Pod가 불러올 게임을 `--start-server-load-latest` 대신 `--start-server <이름>`으로
고릅니다. 게임을 바꾸는 일은 설정 변경과 재시작입니다. 한 번에 한 게임만 할 때 알맞습니다.

**게임마다 Deployment 하나(동시에 실행 가능).** 게임마다 `factorio` Application을
복제합니다. 이름, `existingClaim`, UDP 포트(예: 34198), Gateway 리스너와 `UDPRoute`,
공유기 포워딩을 각각 따로 둡니다. UDP에는 호스트 이름이 없어서 두 번째 게임이 같은
포트를 쓰면서 이름으로 구분할 수는 없습니다. 예약된 주소 하나에 포트가 다른 리스너를
여러 개 둘 수 있습니다.

### 레플리카와 게임 보관

한 게임은 정확히 레플리카 1개여야 합니다. 같은 게임의 레플리카가 2개면 서버
프로세스 둘이 같은 저장과 같은 포트를 쓰다가 저장이 깨집니다. Deployment에는 소수
레플리카가 없으므로 쓸 값은 `0`과 `1`입니다.

- `replicas: 1`: 게임이 실행 중입니다.
- `replicas: 0`: 게임이 보관(정지) 상태입니다. 볼륨과 저장은 남고 Pod와 메모리는
  반환됩니다.

그래서 게임 정의는 Git에 여러 개 두고 원하는 것만 실행할 수 있습니다. 예를 들어
Deployment 3개 중 2개를 `replicas: 0`으로 둡니다. 보관한 게임이 실행 중인 게임과
포트를 공유하면 `UDPRoute`는 실행 중인 게임만 가리키게 하고, 나머지는 `0`으로 둡니다.

## 표준 부하에서 게임 1개를 위한 인프라

여기서 "표준 부하"는 중간 크기 기지에서 약 4명이 플레이하는 경우입니다.

이 서버에서 측정한 값(새 맵, 플레이어 1명, 시작 후 몇 분)은 메모리 약 445MiB(최고
약 460MiB), CPU는 코어 하나의 몇 퍼센트입니다. 이것은 바닥값이지 표준 부하가 아닙니다.

계획용 경험치는 다음과 같습니다(이 클러스터에서 잰 값이 아니라 추정치입니다).

| 자원 | 작은 기지, 1~2명 | 표준, 약 4명 | 큰 기지 |
| --- | --- | --- | --- |
| CPU | 빠른 코어 1개 | 전용 빠른 코어 1개 | 매우 빠른 코어 1개 |
| 메모리 | 1~2 GiB | 2~4 GiB | 8 GiB 이상 |
| 저장 볼륨 | 1 GiB | 2~5 GiB | 10 GiB 이상 |
| 네트워크 | 1 Mbit/s 미만 | 1~2 Mbit/s와 접속 시 순간 증가 | 더 큼 |

참고:

- 시뮬레이션은 사실상 단일 스레드라서 코어 수가 아니라 코어 하나의 속도가 중요합니다.
  코어가 느리면 모든 플레이어의 게임 속도가 초당 60 업데이트 아래로 떨어집니다.
- 접속하는 플레이어는 맵 전체를 내려받으므로, 업로드 대역폭은 저장 크기만큼의 순간
  전송(초반 몇 MiB, 후반 수십 MiB)을 감당해야 합니다.
- 디스크는 거의 한계가 되지 않습니다. 저장 파일이 작아서 자동 저장 3슬롯과 수동 저장
  하나는 5 GiB에 오래도록 충분히 들어갑니다.

현재 요청은 CPU `250m`, 메모리 `512Mi`이고 메모리 한도 `2Gi`에 CPU 한도는 없습니다.
작은 규모에는 충분합니다. 표준 규모에는 CPU 요청을 `1000m`, 메모리 요청을 `2Gi`,
메모리 한도를 `4Gi`로 올리고, 더 빠른 코어를 위해 Pi 4보다 Raspberry Pi 5 노드를
쓰세요. Envoy 프록시에 이미 쓰는 `NotIn 4b` 노드 어피니티가 그 방법의 예입니다. 값을
확정하기 전에 실제 플레이어로 다시 측정하세요.
