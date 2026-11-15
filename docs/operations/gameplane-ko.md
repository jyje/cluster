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

공개 호스트는 `gameplane.app.jyje.online`입니다. Gateway, Certificate, HTTPRoute는 Application(`extraResources`)에 있고
공용 `envoy-web` 클래스에 합류합니다. 80, 443 포트는 아직 ingress-nginx가 노드에서 쥐고 있어서, Application 안의
작은 브리지 Ingress가 위 Certificate로 TLS를 끝내고 Envoy 프록시의 전용 `http-bridge` 리스너(8080 포트)로 평문 HTTP 전달을 합니다(`envoy-gateway-system`의
`envoy-web`을 가리키는 `ExternalName` Service 사용). 이 구간은 ingress-nginx에서 다른 모든 앱으로 가는 구간처럼
클러스터 안에 머뭅니다. 그다음 HTTPRoute가 모든 경로를 `gameplane-web`으로 보냅니다.
즉 공개 트래픽은 이미 Envoy Gateway를 지납니다. [envoy-gateway-migration-ko.md](../networks/envoy-gateway-migration-ko.md)의
컷오버에서 Envoy가 포트를 가져가면 브리지 Ingress, Service, 리스너는 지웁니다.

브리지에서 알아 둘 점이 둘 있습니다.

- ingress-nginx는 일부 백엔드 오류를 자체 오류 페이지로 바꿉니다(`custom-http-errors`). 대시보드 API는 401과 404를
  직접 응답하고 SPA가 그 값을 읽으므로, 브리지 Ingress는 목록을 쓰지 않는 코드로 덮어씁니다.
- ingress-nginx는 `proxy-ssl-secret`이 없으면 `proxy-ssl-*` 어노테이션을 모두 무시해서 SNI를 보내지 않고, Envoy의
  HTTPS 리스너가 연결을 끊습니다. 그래서 브리지는 HTTPS가 아니라 평문 HTTP 리스너를 씁니다. HTTPS 리스너는
  포트포워드 확인과 최종 구성을 위해 남겨 둡니다.

DNS 레코드는 다른 `app.jyje.online` 이름들과 같은 DDNS 호스트를 가리키는 CNAME입니다. Certificate가 발급되려면
Let's Encrypt HTTP-01 챌린지 전에 이 레코드가 있어야 합니다.

Homer 카드는 Ingress 어노테이션이 아니라 `homer-instance`의 `4. Games` 그룹에 둔 수동 항목입니다. 브리지 Ingress에서
HTTPRoute로 옮겨도 카드가 유지됩니다.

공개 구간 없이 Envoy 경로만 확인하려면 포트포워드를 씁니다.

```bash
kubectl -n envoy-gateway-system port-forward \
  $(kubectl -n envoy-gateway-system get svc -l gateway.envoyproxy.io/owning-gatewayclass=envoy-web -o name) 8443:8443
```

```bash
curl -sI --resolve gameplane.app.jyje.online:8443:127.0.0.1 https://gameplane.app.jyje.online:8443/
```

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

## 가이드: 웹 UI로 첫 Factorio 서버 만들기

대시보드에서 Factorio 서버를 만드는 가이드입니다. 아래 내용은 Git에 들어가지 않습니다. 서버는 operator가
reconcile하는 `GameServer`이고, 기존 `factorio` Application에는 손대지 않습니다. 이 클러스터에 특화된 점이
있어서 먼저 확인하세요.

**시작하기 전에**

1. **Admin Settings, General**의 **External URL**을 `https://gameplane.app.jyje.online`으로 설정합니다.
   공유 링크와 콜백이 이 값에서 만들어집니다.
2. 기존 서버의 주소를 재사용하지 마세요. `factorio` Application이 예약 주소의 UDP 34197을 씁니다.
   두 번째 서버는 다른 포트가 필요합니다.
3. Factorio는 UDP만 씁니다. 클라이언트 버전이 다르면 접속할 수 없으니, 모듈 이미지 버전에 클라이언트를 맞추세요.

**서버 만들기** (Servers, Create server, 템플릿 **Factorio**)

1. **이름과 비밀번호.** 게임 비밀번호를 설정합니다. 비워 두면 서버가 열려 있는 상태가 되므로, 다른 사람이
   닿을 수 없는 테스트에만 비워 두세요. **Public**은 끕니다. 이 템플릿은 `require_user_verification`이 항상
   켜져 있어서 모든 플레이어에게 Factorio 계정이 필요합니다.
2. **배치.** 노드 셀렉터 `app.jyje.online/raspi.type: 5b`를 추가합니다. 시뮬레이션이 코어 하나에 묶이므로
   Pi 4가 아니라 Pi 5 노드에서 돌립니다. 모듈 이미지는 멀티 아키텍처 이미지이고 arm64 빌드가 있습니다.
3. **리소스.** 템플릿은 1Gi를 요청하고 4Gi와 CPU 2개까지 허용합니다. 노드가 바쁘면 기존 서버 크기처럼
   한도를 낮춥니다.
4. **스토리지.** 기본 StorageClass(NFS)에 5Gi입니다. 세이브가 여기에 쌓이므로 로컬 디스크보다
   자동 저장이 느릴 수 있습니다.
5. **노출.** 이 단계가 가장 중요합니다.
   - `addressPool` 없이 `LoadBalancer`를 고르지 **마세요**. MetalLB의 `default-addresspool`에 노드 주소가
     들어 있고, 노드 주소를 Service에 주면 전에 ARP 충돌이 났습니다. `factorio-private`는 주소가 하나이고
     기존 서버 전용으로 예약돼 있습니다.
   - 첫 테스트는 **NodePort**를 고르고 포트를 고정합니다. 그다음 남는 WAN UDP 포트를 그 노드 포트로
     포워딩하거나, LAN에서 `<노드 주소>:<노드 포트>`로 바로 접속해 봅니다.
   - 나중에는 `addressPool`로 전용 MetalLB 풀을 쓰거나, 라우터 포워딩이 필요 없는 릴레이 터널(frp,
     Tailscale, playit.gg)을 씁니다.
   마법사에 노출 선택지가 보이지 않으면 operator에서 기본으로 꺼 둔 것입니다(Gameplane 저장소의 네트워킹
   문서 참고).
6. 첫 실행에서는 **idle sleep**과 **wake on connect**를 꺼 둡니다.

**확인하기**

1. 서버가 **Running**이 되고, 로그에 파드 안 UDP 34197로 게임을 호스팅한다고 찍힙니다.
2. Factorio 클라이언트의 직접 연결로, 서버 Overview의 주소로 접속합니다. 눈에 띄는 변경을 만들고 자동 저장을
   기다린 뒤, 대시보드에서 서버를 재시작하고 다시 접속해서 변경이 남아 있는지 봅니다.
3. 백업은 백업 대상을 설정한 뒤에 합니다. 지금은 설정된 곳이 없습니다.

**정리**: 대시보드에서 서버를 지우면 파드와 Service가 사라집니다. 클레임도 같이 지워졌는지 확인해서 NFS
공간이 풀리게 하세요.

## 롤아웃 확인

1. Argo CD가 의도한 리비전을 동기화했고 Application이 `Healthy`입니다.
2. `gameplane-operator`, `gameplane-api`, `gameplane-web` Deployment가 `Ready`입니다.
3. Certificate가 `Ready`, Gateway 리스너가 `Programmed`, HTTPRoute가 `Accepted`입니다.
4. 포트포워드로 대시보드가 응답하고 관리자가 로그인됩니다.
