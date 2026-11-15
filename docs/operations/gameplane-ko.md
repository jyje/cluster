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

## 롤아웃 확인

1. Argo CD가 의도한 리비전을 동기화했고 Application이 `Healthy`입니다.
2. `gameplane-operator`, `gameplane-api`, `gameplane-web` Deployment가 `Ready`입니다.
3. Certificate가 `Ready`, Gateway 리스너가 `Programmed`, HTTPRoute가 `Accepted`입니다.
4. 포트포워드로 대시보드가 응답하고 관리자가 로그인됩니다.
