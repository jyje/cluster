# Gameplane

English version: [gameplane.md](gameplane.md)

`gameplane` Application 운영 메모입니다. Gameplane은 쿠버네티스 네이티브 게임 서버 컨트롤 패널입니다
(https://github.com/GameplanePanel/Gameplane, 차트 0.4.0, pre-v1).
추적 이슈: [#301](https://github.com/jyje/cluster/issues/301).
아직 게임 서버는 만들지 않았습니다. 비밀번호, 토큰, 개인키는 저장소에 올리지 않습니다.

## 구성

- Argo CD Application `gameplane` 하나가 vendoring한 차트(`helm/gameplane/gameplane-0.4.0`)를
  `gameplane-system`에 배포합니다. 차트가 이후 게임 서버용 `gameplane-games`를 만듭니다.
- CRD는 Argo CD가 server-side apply로 차트와 함께 동기화하므로, 차트의 pre-upgrade CRD 훅은 껐습니다.
  Application을 지우면 CRD가 prune되면서 모든 GameServer도 같이 사라집니다. 게임이 생긴 뒤에는 지우지 마세요.
- API는 SQLite 데이터베이스를 `2Gi` 클레임에 둡니다. 이 클러스터의 유일한 StorageClass는 NFS이고,
  WAL 모드 SQLite는 NFS에서 문제가 생길 수 있습니다. 첫 롤아웃 뒤 API 로그에서 데이터베이스 잠금 오류를 살펴보세요.
- 익명 사용 통계는 껐습니다(`api.telemetry.enabled: false`).
- 기본 모듈 소스는 `ghcr.io`에서 모듈 카탈로그를 한 시간마다 가져옵니다.

## 에이전트 mTLS 자료

차트가 CA를 직접 만들 수도 있지만, Argo CD는 오프라인으로 렌더링해서 렌더링할 때마다 새 CA가 나옵니다.
그래서 CA와 클라이언트 인증서는 Application 안의 SealedSecret으로 둡니다.

| 시크릿 | 키 |
|---|---|
| `gameplane-external-ca-v1` | `ca.crt`, `ca.key` |
| `gameplane-external-client-v1` | `tls.crt`, `tls.key` |

교체할 때는 새 자료를 만들어 새 버전 이름(`-v2`)으로 봉인하고, `api.agentMTLS`가 새 이름을 가리키게 한 뒤
API와 operator가 롤링되게 합니다. 에이전트는 CA를 신뢰하므로, CA를 바꾸면 기존 게임 파드를 재시작해야 합니다.
개인키는 저장소에 두지 않고 봉인된 형태만 둡니다.

## 대시보드 접근

공개 호스트는 `gameplane.app.jyje.online`입니다. Ingress와 Certificate는 Application(`extraResources`)에 있고, Ingress는
`higress` 클래스를 씁니다. Higress가 모든 경로를 대시보드를 서빙하고 API를 프록시하는 `gameplane-web`으로 바로 보냅니다.
Certificate는 Ingress가 쓰는 시크릿 옆에 둔 명시적 리소스입니다(이름 `gameplane-envoy`는 옛 이름 그대로입니다).

Ingress에서 알아 둘 점이 셋 있습니다.

- 대시보드 API는 401과 404를 직접 응답하고 SPA가 그 값을 읽습니다. Higress는 백엔드 오류를 그대로 전달하므로, 예전 컨트롤러처럼
  전역 오류 페이지를 꺼 둘 필요가 없습니다.
- 요청 속도 상한은 `higress.io/route-limit-rps`이고 클라이언트별이 아니라 라우트별입니다. 본문 크기 상한과 연결 수 상한은 없습니다.
  업로드, WebSocket, SSE는 게이트웨이 전체의 한 시간 유휴 타임아웃이 맡습니다.
- Homer 카드가 브라우저에서 `/healthz`로 ping하므로, Ingress가 대시보드 출처에 한해 CORS를 허용합니다.

DNS 레코드는 다른 `app.jyje.online` 이름들과 같은 DDNS 호스트를 가리키는 CNAME입니다. Certificate가 발급되려면
Let's Encrypt HTTP-01 챌린지 전에 이 레코드가 있어야 합니다.

Homer 카드는 Ingress 어노테이션이 아니라 `homer-instance`의 `3. Management` 그룹에 둔 수동 항목입니다.

## 첫 관리자

비밀번호는 12자 이상이어야 합니다. 셸 기록에 남지 않도록 표준입력으로 넘깁니다.

```bash
printf '%s' "$ADMIN_PASSWORD" | kubectl -n gameplane-system exec -i deploy/gameplane-api -- \
  /api bootstrap-admin --username admin --password-stdin
```

## 싱글 사인온 (authentik)

대시보드는 로컬 admin 계정과 함께 authentik으로 로그인합니다.

- authentik 쪽은 [`authentik.yaml`](../../clusters/r4spi/apps/authentik.yaml)의 `authentik-gameplane-oidc`
  블루프린트입니다. Gameplane은 클라이언트 시크릿이 필요해서, 블루프린트 안에 시크릿을 넣어 봉인했습니다.
  같은 시크릿을 Gameplane Application에도 `gameplane-oidc`로 한 번 더 봉인해 둡니다.
- 애플리케이션은 `AuthentikAdmin`에만 묶여 있고([authentik-access-ko.md](authentik-access-ko.md) 참고),
  `ClusterAdmin`도 함께 들어옵니다.
- 역할은 `groups` 클레임에서 정해집니다. `AuthentikAdmin`과 `ClusterAdmin`은 대시보드 admin이 되고,
  `defaultRole: deny`가 그 외 사용자를 거부합니다.
- 리디렉션 URL은 레거시 경로 `/auth/oidc/callback`입니다. Gameplane이 Helm으로 설정한 이 프로바이더의 별칭으로
  유지하는 경로입니다. 블루프린트가 이 경로와 `/auth/oidc/helm/callback` 형태를 모두 등록합니다.
- 로컬 admin은 긴급용 로그인으로 켜 둡니다. 비밀번호를 보관하세요.

클라이언트 시크릿을 교체할 때는 새 값을 만들어 두 곳에 봉인하고 두 Application을 동기화합니다. 소유자 계정으로
확인합니다. 로그인 화면에 "authentik" 버튼이 보이고, 로그인하면 admin으로 대시보드에 들어가야 합니다. 문제 해결은
[authentik-access-ko.md](authentik-access-ko.md)를 따릅니다. 로그인이 `invalid_request`로 끝나면 프로바이더에서
`grant_types`가 빠진 것입니다.

## 가이드: UDP Gateway 뒤의 게임 서버

게임 서버는 대시보드에서 만듭니다. 서버는 operator가 reconcile하는 `GameServer`라서 서버 자체는 Git에 들어가지
않습니다. 공개 UDP는 Git에 있는 `games` Gateway를 지나 들어옵니다([envoy-udp-gateway-ko.md](envoy-udp-gateway-ko.md)
참고). 이 클러스터에 특화된 점은 다음과 같습니다.

1. **Admin Settings, General**의 **External URL**을 `https://gameplane.app.jyje.online`으로 설정합니다.
   공유 링크와 콜백이 이 값에서 만들어집니다.
2. **이미지를 고정합니다.** 마법사에서 버전을 고른 뒤, 서버 설정(`spec.image`)에 태그와 digest로 이미지를
   지정합니다. 떠다니는 태그나 채널은 게임 버전을 마음대로 바꾸고, 다른 버전의 클라이언트는 접속할 수 없습니다.
   이미지에 arm64 네이티브 빌드가 있는지 확인하세요. x86 바이너리만 들어 있는 이미지는 에뮬레이터로 돌아서
   훨씬 느립니다.
3. **배치.** 노드 셀렉터 `app.jyje.online/raspi.type: 5b`를 추가합니다. 시뮬레이션이 코어 하나에 묶이므로
   Pi 4가 아니라 Pi 5 노드를 씁니다.
4. **이름.** 공개 라우트는 서버 이름과 같은 Service로 트래픽을 보냅니다(`manifests/envoy-gateways/games-route.yaml`의
   `world-1`). 서버를 그 이름으로 만들거나 라우트를 바꾸세요.
5. **노출.** `ClusterIP`로 둡니다. 공개 UDP는 Gateway로 들어옵니다. 전용 주소 풀 없이 `LoadBalancer`를 고르지
   **마세요**. MetalLB의 `default-addresspool`에 노드 주소가 들어 있고, 노드 주소를 Service에 주면 전에 ARP 충돌이
   났습니다.
6. 첫 실행에서는 **idle sleep**과 **wake on connect**를 꺼 둡니다.
7. 게임 비밀번호를 설정하고 서버를 비공개 목록으로 둡니다.

**확인하기**

1. 서버가 **Running**이 되고, 로그에 파드 안 UDP 포트로 게임을 호스팅한다고 찍힙니다.
2. 클라이언트의 직접 연결로 공개 이름과 게임 포트에 접속합니다. 눈에 띄는 변경을 만들고 자동 저장을 기다린 뒤,
   대시보드에서 서버를 재시작하고 다시 접속해서 변경이 남아 있는지 봅니다.
3. 백업은 백업 대상을 설정한 뒤에 합니다. 지금은 설정된 곳이 없습니다.

**기존 월드 옮기기**: 서버를 멈추고, 데이터 볼륨의 saves 디렉터리에 세이브를 복사합니다(대시보드 Files 탭, 또는
`kubectl exec`와 파이프). 서버를 시작하고 로그에서 세이브를 읽었는지 확인합니다. 서버 버전은 세이브를 만든 버전과
같거나 더 높아야 하고, 세이브에 쓰인 모드는 서버에도 있어야 합니다.

**정리**: 대시보드에서 서버를 지우면 파드와 Service가 사라집니다. 클레임도 같이 지워졌는지 확인해서 NFS
공간이 풀리게 하세요.

## 게임이 Starting과 AgentStale에 머물 때

각 게임의 에이전트 사이드카는 쿠버네티스 API로 상태를 보고합니다. Gameplane의 기본 정책은 API 서버로 가는 길을
TCP 443과 6443만 열어 두는데, MicroK8s는 API를 16443에서 제공하고, Calico는 Service 주소가 엔드포인트로
변환된 뒤에 정책을 검사합니다. 그래서 heartbeat가 타임아웃되고(에이전트 로그의
`dial tcp 10.152.183.1:443: i/o timeout`), 게임은 실제로 돌고 있는데도 서버가 `Starting`과 `AgentStale`로
보입니다. Application의 `allow-agent-to-microk8s-apiserver` 정책이 게임과 sentinel 파드에 16443을 열어 줍니다.
같은 증상이 다시 보이면 `kubectl get endpoints kubernetes`의 엔드포인트 포트와 이 정책을 비교하세요.

게임 로그에는 10초마다 `New RCON connection from <노드 주소>` 줄이 찍힙니다. kubelet 프로브가 RCON 포트를
확인하는 것이라 문제가 아닙니다.

## 롤아웃 확인

1. Argo CD가 의도한 리비전을 동기화했고 Application이 `Healthy`입니다.
2. `gameplane-operator`, `gameplane-api`, `gameplane-web` Deployment가 `Ready`입니다.
3. Certificate가 `Ready`, Gateway 리스너가 `Programmed`, HTTPRoute가 `Accepted`입니다.
4. 포트포워드로 대시보드가 응답하고 관리자가 로그인됩니다.
