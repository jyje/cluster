# Factorio 서버 가이드

English version: [factorio-server-guide.md](factorio-server-guide.md)

`factorio` Application으로 배포한 Factorio 서버의 운영 안내입니다(롤아웃은
[envoy-factorio-cutover.md](envoy-factorio-cutover.md) 참고). 평문 비밀번호, 토큰,
사용자 목록은 절대 이 저장소에 커밋하지 마세요.

아래의 모든 `kubectl` 명령은 `factorio` 네임스페이스와 `factorio` Deployment를
기준으로 합니다.

## 현재 서버 구성

- Pod 1개(`replicas: 1`), 전략은 `Recreate`, 저장 볼륨은 `5Gi` 하나(`factorio-data`)입니다.
- 게임은 UDP 34197에서 받습니다. Envoy `factorio` Gateway의 예약된 사설 주소로
  노출하고, 공유기 포워딩 하나가 WAN UDP 34197을 그 주소로 보냅니다. RCON과 TCP는
  없습니다.
- 설정은 ConfigMap(`overrides.json`)과 SealedSecret(`factorio-secret`)에서 오고,
  시작 스크립트가 매번 이미지의 `server-settings.example.json` 위에 `jq`로 둘을
  병합합니다. 설정은 시작할 때만 읽으므로 변경하면 Pod를 재시작해야 합니다.
- 서버는 시작할 때 `/factorio/saves`에서 가장 최근에 수정된 저장을 불러옵니다.
  불러온 저장은 자동 저장 때마다 같은 파일에 덮어써지므로 이전 자동 저장의 이력은
  남지 않습니다. [체크포인트와 백업](#체크포인트와-백업)을 보세요.
- `require_user_verification`이 `true`라서 모든 플레이어에게 유효한 Factorio 계정이
  필요합니다. 서버는 공개 목록에 올리지 않습니다(`visibility.public: false`).
- 서버는 Pi 5 노드(`app.jyje.online/raspi.type: 5b`)에서 실행됩니다.
  [node-labels-ko.md](node-labels-ko.md)를 보세요.

## 게임 비밀번호

무작위 기본 비밀번호가 SealedSecret `factorio-secret`(키 `settings.json`, `game_password`가
든 JSON 문서)에 있습니다. Git에는 암호화된 값만 있습니다. Secret은 `/etc/factorio-secret`에
읽기 전용으로 마운트되어 시작할 때 서버 설정에 병합됩니다.

현재 기본 비밀번호 확인:

```bash
kubectl -n factorio get secret factorio-secret -o jsonpath='{.data.settings\.json}' | base64 -d | jq -r .game_password
```

### Git 변경 없이 바꾸기

시작 스크립트는 저장 볼륨의 `/factorio/game_password` 파일도 찾습니다. 파일이 있으면 다음
시작 때 그 내용이 비밀번호를 대체합니다. 새 비밀번호는 프로세스 목록에 보이지 않도록
표준 입력으로 쓰고 재시작하세요.

```bash
printf %s '새-비밀번호' | kubectl -n factorio exec -i deploy/factorio -- sh -c 'cat > /factorio/game_password && chmod 600 /factorio/game_password'
kubectl -n factorio rollout restart deploy/factorio
```

빈 파일은 비밀번호 없음을 뜻합니다. Secret 값으로 되돌리려면 파일을 지우세요.

```bash
kubectl -n factorio exec deploy/factorio -- rm -f /factorio/game_password
kubectl -n factorio rollout restart deploy/factorio
```

재시작하면 플레이어 접속이 약 1분 끊깁니다. 덮어쓰기 파일은 저장 볼륨에 있으므로 재시작과
Pod 교체 후에도 유지됩니다.

### 관리자로 즉시 바꾸기

관리자는 게임 안 채팅에서 `/config set password 새-비밀번호`를 실행할 수 있습니다(`password`
옵션은 [Console](https://wiki.factorio.com/Console) 문서에 있습니다). 실행 중인 서버에만
적용됩니다. 시작 스크립트가 시작할 때마다 설정을 다시 만들므로, 재시작하면 Secret(또는
덮어쓰기 파일) 값이 다시 적용됩니다. 관리자가 필요하며 아래를 보세요.

### 기본값 바꾸기

새 SealedSecret 값을 만들어 커밋합니다.

```bash
printf '{"game_password": "새-비밀번호"}' | kubeseal --raw --scope strict --namespace factorio --name factorio-secret --cert <controller-cert.pem>
```

`clusters/r4spi/apps/factorio.yaml`의 `factorio-secret` 항목 `settings.json` 값을 바꾸고
병합한 뒤 `factorio` Application을 동기화하세요(Application 리소스에 새 값이 들어가도록
`apps`를 먼저 동기화합니다).

## 관리자

예제 설정 파일에는 `admins` 키가 없고, 지금은 관리자가 지정돼 있지 않습니다. 관리자가
없으면 `/server-save`나 `/config` 같은 게임 안 명령을 아무도 쓸 수 없습니다. 서버는
`--server-adminlist`로 넘기는 별도 목록 파일을 읽습니다. 이 목록과 아래 화이트리스트는 실제
계정을 가리키고 이 저장소는 공개이므로 시크릿으로 다룹니다.

1. 비밀번호와 같은 SealedSecret에 JSON 배열을 키로 더합니다. 예를 들어
   `server-adminlist.json`에 `["alice", "bob"]`, `server-whitelist.json`에 같은 형식을
   넣습니다. 각 값은 로컬에서 `kubeseal`로 암호화합니다. Secret은 `/etc/factorio-secret`에
   마운트됩니다.
2. 시작 스크립트의 `exec` 줄에
   `--server-adminlist /etc/factorio-secret/server-adminlist.json`을 추가하고
   재시작합니다. 파일은 읽기 전용이지만 서버가 시작할 때만 읽으므로 문제없습니다.
3. 이후 관리자는 게임 안에서 `/promote 이름`, `/demote 이름`으로 다른 사람을 승격하거나
   강등할 수 있습니다. 이 명령은 서버의 목록 파일을 고치는데 여기서는 읽기 전용이라,
   게임 안에서 한 승격은 재시작하면 사라집니다. 영구 변경은 SealedSecret을 고치고
   재시작하세요.
4. 예제 설정에서 `allow_commands`는 `admins-only`, `only_admins_can_pause_the_game`은
   `true`라서 명령과 일시정지는 기본적으로 관리자만 쓸 수 있습니다.
5. 닫힌 서버로 운영하려면 `--use-server-whitelist`와
   `--server-whitelist /etc/factorio-secret/server-whitelist.json`을 추가합니다. 목록의
   사용자만 접속할 수 있습니다.

## 콘솔 명령: 일시정지, 재개, 저장

RCON이 꺼져 있어서 명령은 관리자가 게임 안 채팅에서 실행합니다. 전체 목록은
[Console](https://wiki.factorio.com/Console) 문서에 있습니다.

| 목적 | 명령 | 참고 |
| --- | --- | --- |
| 지금 저장 | `/server-save` | 관리자만. 서버에서 게임을 저장합니다. |
| 일시정지 | `/c game.tick_paused = true` | Lua API 속성 `tick_paused`. |
| 재개 | `/c game.tick_paused = false` | |
| 비밀번호 변경 | `/config set password 새-비밀번호` | 실행 중인 서버에만. |
| 다른 설정 | `/config get`, `/config set` | `max-players`, `autosave-interval`, `only-admins-can-pause`, `visibility-public` 등. |
| 관리자 | `/promote 이름`, `/demote 이름` | 여기서는 재시작하면 사라집니다. |
| 추방, 차단 | `/kick 이름`, `/ban 이름` | |

참고:

- `/c`는 Lua를 실행합니다. Console 문서에 따르면 이를 쓰면 해당 저장의 업적이 꺼집니다.
- `auto_pause`가 이미 켜져 있어서 아무도 접속하지 않으면 게임이 스스로 멈춥니다.
- `only_admins_can_pause_the_game`이 켜져 있어서 플레이어는 직접 일시정지할 수 없습니다.
- 터미널에서 명령을 실행하려면 서버에 RCON이 필요합니다(`--rcon-port`, `--rcon-password`,
  [Command line parameters](https://wiki.factorio.com/Command_line_parameters) 참고). 여기서는
  RCON을 켜지 않았습니다. 비밀번호를 Secret으로 두고 포트에 누가 접근할 수 있는지 정해야
  하므로 신중히 켜세요.

## 체크포인트와 백업

서버는 불러온 저장 `world.zip`을 자동 저장 때마다 덮어씁니다. 번호가 붙은 자동 저장 파일을
남기지 않으므로, 체크포인트는 직접 만든 복사본이어야 합니다.

복사본은 `/factorio/saves` 밖에 두세요. 서버는 그 폴더에서 가장 최근에 수정된 파일을
불러오므로, 폴더 안의 추가 복사본이 실수로 불러와질 수 있습니다.

백업 만들기:

```bash
kubectl -n factorio exec deploy/factorio -- sh -c 'mkdir -p /factorio/backups && cp -p /factorio/saves/world.zip "/factorio/backups/world-$(date +%Y%m%d-%H%M).zip"'
```

일관된 복사본을 위해 먼저 관리자로 `/server-save`를 실행하세요. 목록 보기와 내려받기:

```bash
kubectl -n factorio exec deploy/factorio -- ls -l /factorio/backups
kubectl -n factorio exec deploy/factorio -- cat /factorio/backups/NAME.zip > NAME.zip
```

백업 복원:

```bash
kubectl -n factorio exec deploy/factorio -- sh -c 'mkdir -p /factorio/backups && mv /factorio/saves/world.zip /factorio/backups/world-before-restore.zip && cp /factorio/backups/NAME.zip /factorio/saves/world.zip'
kubectl -n factorio rollout restart deploy/factorio
```

백업은 실제 저장과 같은 볼륨에 있으므로 볼륨을 잃는 경우는 막지 못합니다. 중요한 것은 내려받아
두세요.

## Mac의 게임을 서버로 옮기기

macOS의 저장 위치(공식 [Application directory](https://wiki.factorio.com/Application_directory)
문서)는 `~/Library/Application Support/factorio/saves/`입니다. 가장 최근 `.zip` 또는
`_autosave` 파일을 고르세요.

시작하기 전에 확인할 것:

- Mac 게임과 서버의 버전이 같거나 서버가 더 높아야 합니다(지금은 둘 다 2.1.24). 서버는 더
  낮은 버전의 저장을 불러올 수 있습니다.
- 모드가 같아야 합니다. 서버는 `base`, `elevated-rails`, `quality`, `recycler`, `space-age`를
  켜 둔 상태이고, 이는 모드 없는 Space Age 게임과 같은 구성입니다. 다른 모드를 쓰는 저장은
  그 모드를 `/factorio/mods`와 `mod-list.json`에 먼저 넣어야 합니다.

순서:

1. Mac에서 게임을 종료해 파일이 완전하게 합니다.
2. 서버 저장을 백업하고 저장 폴더 밖으로 옮깁니다.

   ```bash
   kubectl -n factorio exec deploy/factorio -- sh -c 'mkdir -p /factorio/backups && mv /factorio/saves/world.zip "/factorio/backups/world-$(date +%Y%m%d-%H%M).zip"'
   ```

3. Mac 저장을 서버로 복사합니다.

   ```bash
   kubectl -n factorio exec -i deploy/factorio -- sh -c 'cat > /factorio/saves/world.zip' < "$HOME/Library/Application Support/factorio/saves/NAME.zip"
   ```

   이름을 `world.zip`으로 하면 폴더에 저장이 하나만 있고 자동 저장도 같은 파일로 갑니다.
4. 서버를 재시작하고 파일을 불러왔는지 확인합니다.

   ```bash
   kubectl -n factorio rollout restart deploy/factorio
   kubectl -n factorio logs deploy/factorio | grep "Loading map"
   ```

5. Mac에서 쓰던 Factorio 사용자 이름으로 접속합니다. 싱글플레이 캐릭터는 보통 사용자 이름으로
   이어집니다. 클라이언트가 맵 전체를 내려받으므로 첫 접속은 시간이 걸릴 수 있습니다.

## 공식 문서

- [Console](https://wiki.factorio.com/Console): `/server-save`, `/config`, `/promote`, `/c` 같은 명령.
- [Command line parameters](https://wiki.factorio.com/Command_line_parameters): `--start-server`, `--server-adminlist`, `--rcon-port` 등.
- [Multiplayer](https://wiki.factorio.com/Multiplayer): 전용 서버, 설정, 관리자 목록.
- [Application directory](https://wiki.factorio.com/Application_directory): 시스템별 저장과 모드 위치.
- [LuaGameScript](https://lua-api.factorio.com/latest/classes/LuaGameScript.html): `tick_paused` 속성.

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

서버는 표준 규모에 맞춰 CPU 요청 `1000m`, 메모리 요청 `2Gi`, 메모리 한도 `4Gi`(차트
기본 CPU 한도 `1500m` 적용)로 잡고, 코어가 더 느린 Pi 4 노드를 피하려고 Pi 5 라벨
`app.jyje.online/raspi.type: 5b` 노드 셀렉터를 씁니다. 이 차트는 `nodeAffinity`를
구현하지 않으므로 노드 셀렉터를 쓰세요. 작은 게임에는 이전 값(`250m`, `512Mi`, 한도
`2Gi`)으로 충분했습니다. 값을 확정하기 전에 실제 플레이어로 다시 측정하세요.
