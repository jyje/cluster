# Apache Airflow

Airflow 3.4.0을 공식 Helm 차트 1.22.0과 `KubernetesExecutor`로 운영합니다. [pilot-airflow-portability](https://github.com/jyje/pilot-airflow-portability) 프로젝트가 쓰는 외부 엔드포인트입니다. 추적 이슈: #407.

## 구성

| 항목 | 선택 |
| :-- | :-- |
| 네임스페이스, Argo CD 프로젝트 | `airflow`, `ai` |
| 차트 | `helm/airflow/airflow-1.22.0` (공식, 로컬 패치는 표준 `extraResources` 키 하나) |
| 이미지 | `apache/airflow:3.4.0` (차트 기본값은 3.2.2라서 Application에서 고정) |
| 실행기 | `KubernetesExecutor`: 작업 하나에 파드 하나. Redis, Celery 워커, Flower, statsd 없음. triggerer는 끔 |
| 구성 요소 | api-server, scheduler, dag-processor 각 1개 |
| 메타데이터 DB | CloudNativePG 클러스터 `airflow-pg`(인스턴스 2개), Application `airflow-pg` |
| DAG | 공개 pilot 저장소의 `src/dags`를 `git-sync`로 가져옴(`main` 브랜치, 60초마다) |
| 작업 로그 | 공유 볼륨 `subdir-usb`(2Gi). 작업 파드는 금방 사라지기 때문 |
| 엔드포인트 | `https://airflow.app.jyje.online` (Higress, Let's Encrypt, 라우트당 초당 20건 제한) |
| 로그인 | authentik(OpenID Connect). 로컬 `admin` 사용자는 API 클라이언트와 예비용으로 유지 |

Application을 둘로 나눈 것은 의도입니다. DB는 수명 주기가 다르고, 워크로드는 파일 단위로 분리합니다.

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
| `airflow-oidc` | authentik 로그인용 OAuth 클라이언트 시크릿 |
| `airflow-pilot` | 권한이 제한된 pilot API 사용자의 비밀번호 |
| `authentik-airflow-oidc` | (authentik Application에 있음) 같은 클라이언트 시크릿이 든 봉인된 블루프린트 |

관리자 비밀번호는 git이 아니라 클러스터에서 읽습니다.

```bash
kubectl -n airflow get secret airflow-admin -o jsonpath='{.data.password}' | base64 -d
```

OAuth 클라이언트 시크릿을 바꿀 때는 `airflow-oidc`와 `authentik-airflow-oidc`를 같은 새 값으로 함께 다시 봉인합니다. 다른 값을 바꾸려면 같은 이름과 네임스페이스로 새 Secret을 봉인해서 Application의 항목을 교체합니다. JWT 시크릿을 바꾸면 모든 사용자가 로그아웃됩니다. Fernet 키를 바꿀 때는 `airflow rotate-fernet-key`가 필요하고, 그렇지 않으면 저장된 커넥션을 읽지 못합니다.

## authentik으로 로그인

사람은 authentik으로 로그인합니다. `airflow` 애플리케이션은 봉인된 블루프린트 `authentik-airflow-oidc`가 만들고, 다른 관리 도구처럼 `AuthentikAdmin`(`ClusterAdmin`도 함께 통과)에 바인딩되어 있습니다. Airflow는 ID 토큰의 `groups` 클레임을 읽어 Application의 `apiServerConfig`에 적은 대로 역할에 매핑합니다.

| authentik 그룹 | Airflow 역할 |
| :-- | :-- |
| `AuthentikAdmin` | `Admin` |
| `ClusterAdmin` | `Admin` |

git에는 사람 이름이 없습니다. 누군가를 Airflow 관리자로 만들려면 그 사람의 authentik 계정을 `AuthentikAdmin`에 넣습니다([authentik-access-ko.md](authentik-access-ko.md) 참고). 역할은 로그인할 때마다 동기화되므로 그룹에서 빼면 다음 로그인부터 역할이 사라집니다. 로그인은 했지만 어느 그룹에도 맞지 않는 계정은 `Public` 역할을 받아 아무것도 할 수 없습니다.

리디렉션 URI는 `https://airflow.app.jyje.online/auth/oauth-authorized/authentik`입니다. 로그인이 실패하면 authentik의 제공자 설정(grant types, 리디렉션 URI, 바인딩)부터 확인합니다.

## DNS

호스트 `airflow.app.jyje.online`에는 다른 `app` 호스트처럼 DNS 제공자에 CNAME 레코드가 필요합니다. DNS는 이 저장소에서 관리하지 않으므로 수동 단계입니다. 이름이 풀리기 전에는 cert-manager가 HTTP-01 챌린지를 끝내지 못합니다. Certificate가 `False`로 남고 Challenge에는 `no such host`가 나옵니다. 레코드를 추가하면 1~2분 안에 인증서가 발급됩니다. 새 Application 호스트에도 같은 단계가 필요합니다.

## API 사용

Airflow 3에는 인증이 필요한 공개 API가 있습니다. 먼저 `/auth/token`에서 JWT를 받고, 그것을 베어러 토큰으로 보냅니다. `/auth/token`으로 받은 토큰은 24시간(`api_auth.jwt_expiration_time`, 86400), CLI 토큰은 1시간(`jwt_cli_expiration_time`, 3600) 유효합니다. 둘 다 기본값이고 Application에서 바꾸지 않았습니다.

```bash
TOKEN=$(curl -s -X POST https://airflow.app.jyje.online/auth/token \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"<비밀번호>"}' | jq -r .access_token)
curl -s -H "Authorization: Bearer $TOKEN" https://airflow.app.jyje.online/api/v2/dags
```

토큰은 만료됩니다. 호출이 401을 돌려주면 새로 받고, 토큰은 파일이 아니라 환경 변수에 둡니다. 접속 정보는 이슈나 PR이 아니라 비공개 채널로 전달합니다.

## pilot DAG 게시와 실행

1. pilot 저장소 `main`의 `src/dags/`에 DAG를 푸시합니다. `git-sync`가 1분 안에 가져옵니다.
2. `pilot_portability`가 DAG 목록에 보이는지, 일시 중지 상태가 아닌지 확인합니다.
3. `items=10000`, `shards=1`로 실행을 만들고 API로 상태와 XCom을 읽습니다. 기대하는 최종 XCom은 `333283335000`입니다.

## 변경 후 확인

- Argo CD에서 `airflow`와 `airflow-pg`가 Synced, Healthy입니다.
- `airflow-api-server`, `airflow-scheduler`, `airflow-dag-processor`, `airflow-pg` 파드 2개가 Ready입니다.
- 실제 설정: `kubectl -n airflow exec deploy/airflow-scheduler -c scheduler -- airflow config get-value core executor`가 `KubernetesExecutor`를 출력하고, 파드 이미지 태그가 `3.4.0`입니다.
- 실행 중에 작업 파드가 나타나고 `Completed`로 끝납니다.

## 참고

- 차트의 DB 마이그레이션과 사용자 생성 잡은 성공하면 스스로 지워지는 Argo CD sync 훅입니다. 첫 동기화에서는 DB가 준비되기 전에 잡이 먼저 돌 수 있고, 준비될 때까지 재시도합니다.
- 리소스 요청은 구성 요소별 실측 사용량을 따릅니다(`kubectl -n airflow top pods --containers`). DAG 부하가 달라지면 다시 측정해서 조정합니다.
- Application을 지워도 DB 볼륨과 네임스페이스의 시크릿은 삭제되지 않습니다.
