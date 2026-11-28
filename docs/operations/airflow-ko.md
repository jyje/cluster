# Apache Airflow 런북

[English](airflow.md)

Airflow 3.4.0을 공식 Helm 차트 1.22.0과 `KubernetesExecutor`로 운영합니다. [pilot-airflow-portability](https://github.com/jyje/pilot-airflow-portability) 프로젝트가 쓰는 외부 엔드포인트입니다. 롤아웃 이슈: #407.

목차: [개요](#개요) · [배포](#배포) · [시크릿](#시크릿) · [네트워크](#네트워크와-인증서) · [접근](#로그인-사용자-역할) · [API](#api-사용) · [DAG](#dag) · [운영](#운영) · [문제 해결](#문제-해결) · [이력](#이력)

## 개요

| 항목 | 선택 |
| :-- | :-- |
| 네임스페이스, Argo CD 프로젝트 | `airflow`, `ai` |
| 차트 | `helm/airflow/airflow-1.22.0` (공식, 로컬 패치는 표준 `extraResources` 키 하나) |
| 이미지 | `apache/airflow:3.4.0` (차트 기본값은 3.2.2라서 Application에서 고정) |
| 실행기 | `KubernetesExecutor`: 작업 하나에 파드 하나. Redis, Celery 워커, Flower, statsd 없음. triggerer는 끔 |
| 구성 요소 | api-server, scheduler, dag-processor 각 1개 |
| 메타데이터 DB | CloudNativePG 클러스터 `airflow-pg`(인스턴스 2개), Application `airflow-pg` |
| DAG | 번들 2개, [DAG](#dag) 참고 |
| 작업 로그 | 공유 볼륨 `subdir-usb`(2Gi). 작업 파드는 금방 사라지기 때문 |
| 엔드포인트 | `https://airflow.app.jyje.online` (Higress, Let's Encrypt, 라우트당 초당 20건 제한) |
| 로그인 | authentik(OpenID Connect), API 클라이언트용 로컬 사용자 |

| 파일 | 내용 |
| :-- | :-- |
| `clusters/r4spi/apps/airflow.yaml` | Application `airflow`: 차트 값과 SealedSecret. 소스가 둘(차트와 `manifests/airflow/pilot-e03`) |
| `clusters/r4spi/apps/airflow-pg.yaml` | Application `airflow-pg`: DB 클러스터와 소유자 시크릿 |
| `clusters/r4spi/apps/authentik.yaml` | 봉인된 로그인 블루프린트 `authentik-airflow-oidc` |
| `clusters/r4spi/apps/homer-instance.yaml` | 대시보드 카드, [homer-ko.md](homer-ko.md) 참고 |
| `helm-sources/catalog.yaml` | 차트의 Renovate 항목 |

Application을 둘로 나눈 것은 의도입니다. DB는 수명 주기가 다르고, 워크로드는 파일 단위로 분리합니다.

## 배포

차트 업그레이드는 [AGENTS.md](../../AGENTS.md)의 절차를 따릅니다. 추적 이슈, 벤더링 PR, 배포 PR 순서입니다.

변경을 병합한 뒤:

1. `apps`를 먼저 동기화합니다. Helm 값이 Application 안에 있어서, 그렇지 않으면 하위 Application이 옛 값을 씁니다.
2. DB를 바꿨으면 `airflow-pg`, 그다음 `airflow`를 동기화합니다. 둘 다 자동 동기화됩니다.
3. [아래 확인 항목](#변경-후-확인)을 점검합니다.

차트의 DB 마이그레이션 잡과 사용자 생성 잡은 성공하면 스스로 지워지는 Argo CD sync 훅입니다.

첫 설치는 시간이 걸립니다. 이미지를 처음 받고, 이 스토리지에서는 `initdb`와 복제본 합류가 느립니다. 마이그레이션 잡은 DB가 뜰 때까지 재시도합니다. DB가 준비된 뒤에도 어떤 구성 요소가 긴 백오프에 머물면 그 파드를 삭제해서 Deployment가 새로 만들게 합니다.

## 시크릿

평문 시크릿 값은 git에 없습니다. Airflow Application의 SealedSecret 8개와 authentik의 1개가 값을 담고 있습니다.

| 시크릿 | 용도 |
| :-- | :-- |
| `airflow-pg-creds` | `airflow` 데이터베이스 소유자(CloudNativePG initdb) |
| `airflow-metadata` | SQLAlchemy 연결 문자열(위와 같은 비밀번호) |
| `airflow-fernet` | 저장된 커넥션과 변수를 암호화하는 Fernet 키 |
| `airflow-api-secret` | API 시크릿 키 |
| `airflow-jwt` | JWT 서명 시크릿. 재시작과 복제본 사이에서 같은 값 유지 |
| `airflow-admin` | `admin` 사용자 비밀번호 |
| `airflow-pilot` | 권한이 제한된 `pilot` 사용자 비밀번호 |
| `airflow-oidc` | authentik 로그인용 OAuth 클라이언트 시크릿 |
| `authentik-airflow-oidc` | (authentik Application에 있음) 같은 클라이언트 시크릿이 든 봉인된 블루프린트 |

비밀번호는 git이 아니라 클러스터에서 읽습니다.

```bash
kubectl -n airflow get secret airflow-admin -o jsonpath='{.data.password}' | base64 -d
```

새 값은 같은 이름과 네임스페이스의 새 Secret을 봉인해서 Application 항목을 바꿉니다([introduction.md](../introduction.md#secrets) 참고).

| 교체 대상 | 추가로 할 일 |
| :-- | :-- |
| OAuth 클라이언트 시크릿 | `airflow-oidc`와 `authentik-airflow-oidc`를 같은 값으로 함께 다시 봉인 |
| JWT 서명 시크릿 | 모든 사용자가 로그아웃됨 |
| Fernet 키 | `airflow rotate-fernet-key` 실행. 하지 않으면 저장된 커넥션을 읽지 못함 |
| `admin` 또는 `pilot` 비밀번호 | 사용자 생성 잡은 기존 사용자를 바꾸지 않음. 새 Secret이 클러스터에 반영된 뒤 api-server 파드에서 `airflow users reset-password` 실행 |

## 네트워크와 인증서

이 호스트에는 다른 `app` 호스트처럼 DNS 제공자에 CNAME 레코드가 필요합니다. DNS는 이 저장소에서 관리하지 않으므로 수동 단계입니다. 이름이 풀리기 전에는 cert-manager가 HTTP-01 챌린지를 끝내지 못합니다. Certificate가 `False`로 남고 Challenge에는 `no such host`가 나옵니다. 레코드를 추가하면 1~2분 안에 인증서가 발급됩니다.

Homer 카드가 브라우저에서 `/api/v2/monitor/health`를 점검하기 때문에 Ingress가 대시보드 출처를 허용합니다(CORS).

## 로그인, 사용자, 역할

### 사람: authentik

사람은 authentik으로 로그인합니다. `airflow` 애플리케이션은 봉인된 블루프린트 `authentik-airflow-oidc`가 만들고 `AuthentikAdmin`(`ClusterAdmin`도 함께 통과)에 바인딩되어 있습니다. Airflow는 ID 토큰의 `groups` 클레임을 읽어 Application의 `apiServerConfig`에 적은 대로 역할에 매핑합니다.

| authentik 그룹 | Airflow 역할 |
| :-- | :-- |
| `AuthentikAdmin` | `Admin` |
| `ClusterAdmin` | `Admin` |

git에는 사람 이름이 없습니다. 누군가를 Airflow 관리자로 만들려면 그 사람의 authentik 계정을 `AuthentikAdmin`에 넣습니다([authentik-access-ko.md](authentik-access-ko.md) 참고). 역할은 로그인할 때마다 동기화되므로 그룹에서 빼면 다음 로그인부터 역할이 사라집니다. 모든 사람에게는 권한이 없는 기본 역할 `Public`도 붙습니다.

리디렉션 URI는 `https://airflow.app.jyje.online/auth/oauth-authorized/authentik`입니다.

### 로컬 사용자

| 사용자 | 역할 | 용도 |
| :-- | :-- | :-- |
| `admin` | `Admin` | 예비 계정과 API 관리 작업 |
| `pilot` | `PilotRunner` | pilot 클라이언트 |

Application의 `createUserJob`이 두 사용자와 `PilotRunner` 역할을 동기화 때마다 만듭니다. 여러 번 실행해도 안전하고 기존 사용자는 바꾸지 않습니다.

`PilotRunner` 권한:

| 리소스 | 동작 |
| :-- | :-- |
| `DAG:pilot_portability` | 읽기, 편집(실행 트리거에 편집이 필요) |
| `DAG Runs` | 생성, 읽기 |
| `Task Instances` | 읽기 |
| `XComs` | 읽기 |

다른 DAG 조회, 삭제, 작업 상태 변경, DAG 코드와 작업 로그 읽기, 커넥션, 변수, 설정, 풀 읽기는 할 수 없습니다. Airflow의 권한 판정 코드로 확인했습니다. e03 DAG는 포함하지 않습니다. pilot에 다른 DAG를 주려면 잡에 `-r "DAG:<dag_id>" -a can_read can_edit` 줄을 추가합니다. 줄을 지워도 권한은 사라지지 않으므로 `airflow roles del-perms`로 제거합니다.

### pilot 사용자 확인

스크립트는 `pilot`으로 로그인해 DAG를 한 번 실행하고 결과를 읽은 뒤, 나머지 호출이 거부되는지 확인합니다. 비밀번호와 토큰은 출력하지 않습니다.

```bash
python3 docs/operations/examples/verify-airflow-pilot.py
```

마지막 줄이 `failures: 0`이면 정상입니다.

## API 사용

먼저 `/auth/token`에서 JWT를 받고 베어러 토큰으로 보냅니다. `/auth/token`으로 받은 토큰은 24시간(`api_auth.jwt_expiration_time`, 86400), CLI 토큰은 1시간(`jwt_cli_expiration_time`, 3600) 유효합니다. 둘 다 기본값입니다.

```bash
TOKEN=$(curl -s -X POST https://airflow.app.jyje.online/auth/token \
  -H 'Content-Type: application/json' \
  -d '{"username":"pilot","password":"<비밀번호>"}' | jq -r .access_token)
curl -s -H "Authorization: Bearer $TOKEN" https://airflow.app.jyje.online/api/v2/dags
```

호출이 401을 돌려주면 토큰을 새로 받습니다. 토큰은 파일이 아니라 환경 변수에 둡니다. 접속 정보는 이슈나 PR이 아니라 비공개 채널로 전달합니다.

## DAG

| 번들 | 소스 | DAG |
| :-- | :-- | :-- |
| `dags-folder` | pilot 저장소의 `src/dags`를 `git-sync`로 가져옴(`main`, 60초마다) | `pilot_portability` |
| `pilot-e03` | `manifests/airflow/pilot-e03`의 ConfigMap `pilot-e03-dags`를 dag-processor와 작업 파드에 마운트. 런타임 디렉터리는 로그 볼륨에서 옴 | `pilot_reconcile`, `pilot_ts_settlement`, `pilot_mixed_language_chain` |

`dags-folder`에 DAG를 올리려면 pilot 저장소 `main`의 `src/dags/`에 푸시합니다. 몇 분 안에 나타납니다(`git-sync` 60초 주기 뒤 파서가 처리).

pilot DAG는 `pilot_portability`를 `items=10000`, `shards=1`로 실행하고 API로 상태와 XCom을 읽습니다. 기대하는 최종 XCom은 `333283335000`입니다.

`pilot-e03` 번들의 주의점 두 가지입니다([README](../../manifests/airflow/pilot-e03/README.md) 기준).

- 새로 설치할 때는 ARM64용 Node.js, Go, Java 런타임 파일과 파일 마운트 지점 세 개를 로그 볼륨의 런타임 디렉터리에 **동기화 전에** 준비해야 합니다. 이 파일들은 git에 없습니다.
- 소스 파일을 수정하면 Application을 동기화하고 dag-processor를 재시작합니다. `subPath`로 마운트하므로 제자리에서 갱신되지 않습니다. 새 작업 파드는 새 내용을 봅니다.

## 운영

### 변경 후 확인

- Argo CD에서 `airflow`와 `airflow-pg`가 Synced, Healthy입니다.
- `airflow-api-server`, `airflow-scheduler`, `airflow-dag-processor`, `airflow-pg` 파드 2개가 Ready입니다.
- `kubectl -n airflow exec deploy/airflow-scheduler -c scheduler -- airflow config get-value core executor`가 `KubernetesExecutor`를 출력하고, 파드 이미지 태그가 `3.4.0`입니다.
- `kubectl -n airflow exec deploy/airflow-scheduler -c scheduler -- airflow dags list-import-errors`가 비어 있습니다.
- 실행 중에 작업 파드가 나타나고 `Completed`로 끝납니다.

### 리소스

요청값은 구성 요소별 실측 사용량을 따릅니다(`kubectl -n airflow top pods --containers`). DAG 부하가 달라지면 다시 측정해서 조정합니다.

### 시작

api-server는 수신을 시작하기 전에 역할 권한을 DB에 동기화합니다. 그래서 startup probe를 5분까지 허용합니다(`startupProbe.failureThreshold: 30`).

### 삭제

Application을 지워도 DB 볼륨과 네임스페이스의 시크릿은 삭제되지 않습니다.

## 문제 해결

| 증상 | 원인과 조치 |
| :-- | :-- |
| Certificate가 `False`, Challenge에 `no such host` | DNS 레코드 없음. [네트워크](#네트워크와-인증서) 참고 |
| api-server가 `Startup probe failed`로 재시작 반복 | 시작이 probe보다 느림. DB부터 확인하고 `failureThreshold`를 올림 |
| 파드가 `wait-for-airflow-migrations`에서 `Connection refused`로 실패 | DB가 준비되지 않음. `kubectl -n airflow get clusters.postgresql.cnpg.io`와 마이그레이션 잡 확인 |
| DB가 준비된 뒤에도 구성 요소가 백오프에 머묾 | 파드 삭제 |
| authentik 로그인 실패 | 제공자(grant types, 리디렉션 URI)와 애플리케이션 바인딩 확인 |
| 로그인했는데 메뉴가 없음 | 계정이 `AuthentikAdmin`이나 `ClusterAdmin`에 없음 |
| API 호출이 401 | 토큰 만료 또는 비밀번호 변경 |
| `pilot`의 API 호출이 403 | 위 권한 범위 밖이면 정상 |
| 새 DAG가 보이지 않음 | dag-processor 파드의 `git-sync` 로그와 `airflow dags list-import-errors` 확인 |
| Homer 카드가 offline | 루트 페이지가 HEAD에 405로 답함. 카드는 `/api/v2/monitor/health`를 GET으로 점검해야 하고, Ingress가 대시보드 출처를 허용해야 함 |

## 이력

| 변경 | PR |
| :-- | :-- |
| 차트 1.22.0 벤더링과 `extraResources` 패치 | #406 |
| Airflow 3.4.0, DB, Renovate 항목 배포 | #408 |
| authentik 로그인, 실측 기반 메모리 요청 | #413 |
| api-server의 startup probe 연장 | #414 |
| 대시보드 카드와 헬스 체크 | #419, #421 |
| GitOps로 e03 DAG 번들과 시작 시간 제한 | #423, #425, #426 |
