# 웹 트래픽을 Higress로 옮기기

추적 이슈: #207, #314(평가), #326(이전). 웹 트래픽이 ingress-nginx에서 Higress로 옮겨간 과정, 앱에 생긴 변화, 지금의 클러스터 구성을 기록한 문서입니다. 다른 문서가 이 파일을 링크하고 있어서 옛 파일 이름을 그대로 둡니다.

## 현재 상태

- **Higress**가 모든 공개 호스트(Ingress 17개)의 ingress 컨트롤러입니다. 워커 노드마다 게이트웨이 파드 하나(컨트롤 플레인 노드는 제외)로 도는 Deployment이고, `externalTrafficPolicy: Local`인 LoadBalancer Service 뒤에 있습니다.
- **입구**는 공유기가 80, 443 포트를 Higress 주소로 포트포워드하는 것입니다. 주소는 이 저장소 밖(비공개 설정)에 있는 MetalLB 풀 `web-private`에서 옵니다. 저장소에는 풀 이름만 있고 주소는 없습니다.
- **ingress-nginx는 더 이상 배포되지 않습니다.** Application, nginx용 발급자, 노드 주소를 담은 MetalLB 풀을 없앴고, 벤더링된 차트는 `helm/ingress`에 남겨 둡니다.
- **Envoy Gateway**는 게임과 UDP(`games` Gateway)에만 남습니다. Higress에는 UDP 리스너가 없다는 것을 실제 게이트웨이에서 확인했습니다.

## 웹에 Envoy Gateway가 아니라 Higress를 쓴 이유

Envoy Gateway는 Ingress가 아니라 Gateway API만 처리해서 앱들이 쓰던 `nginx.ingress.kubernetes.io/*` 어노테이션을 읽지 못합니다. Higress는 Envoy 기반이고 그 어노테이션 대부분을 그대로 읽으며 Gateway API도 지원합니다. 덕분에 이전이 작았고, 대부분의 Ingress는 클래스와 발급자만 바뀌었습니다.

## 어노테이션 대응

| nginx 어노테이션 | Higress |
|---|---|
| `enable-cors`, `cors-allow-*` | 같은 이름으로 동작 |
| `affinity`, `session-cookie-*` | 같은 이름으로 동작 |
| `proxy-read-timeout`, `proxy-send-timeout` | 쓰지 않음. 게이트웨이 전체 `downstream.idleTimeout`(3600초)이 대신함 |
| `limit-rps` | `higress.io/route-limit-rps`로 이름 변경. 클라이언트별이 아니라 라우트별 |
| `ssl-redirect` | 같은 이름으로 동작하고, 필요함(Higress는 기본으로 HTTP를 HTTPS로 리다이렉트하지 않음) |
| `limit-connections`, `proxy-body-size` | 대응 없음. 어떤 크기든 통과 |
| `configuration-snippet` (CORS 출처 반사) | 명시적 `cors-allow-origin` |
| `custom-http-errors` | `higress` Application의 EnvoyFilter로 대체. 아래 참고 |

놓치기 쉬운 설정이 둘 있습니다. Higress 게이트웨이는 기본값으로 라우트 타임아웃과 상관없이 180초 동안 데이터가 없는 연결을 끊으므로 `downstream.idleTimeout`을 3600으로 올렸습니다. 그리고 `ssl-redirect`를 두지 않으면 Higress는 HTTP를 HTTPS로 리다이렉트하지 않습니다.

## 사용자에게 달라 보이는 점

- 오류 화면이 다시 적용됩니다. EnvoyFilter(`higress-error-pages`)가 공개 호스트마다 Envoy custom response 필터를 켭니다. 상태 코드 401, 403, 404, 405, 408, 409, 410, 429, 500, 502, 503, 504에서 게이트웨이가 `error-pages` 서비스의 해당 화면을 받아 원래 상태 코드로 돌려줍니다. Gameplane 호스트(앱이 401과 404를 직접 읽음)와 `error-pages` 호스트(자기 자신으로 리다이렉트됨)는 제외했습니다. 본문이 있는 요청은 앱의 응답이 그대로 나가고, JSON을 요청해도 HTML 화면이 옵니다. 새 공개 호스트는 EnvoyFilter에 패치를 따로 추가해야 하며, 라우트 설정 이름 `higress-rds-443.<호스트>`로 매칭합니다.
- 요청 본문 크기 상한과 클라이언트별 연결 수 상한이 없어졌습니다. 상한이 있던 Ingress는 인증 뒤에 있습니다.
- 속도 제한은 클라이언트별이 아니라 라우트별입니다.

## 인증서

ClusterIssuer `higress-letsencrypt-stag`와 `higress-letsencrypt-prod`는 HTTP-01 챌린지 Ingress에 `ingressClassName: higress`를 씁니다. Ingress가 Higress로 옮겨갈 때 모든 Certificate가 프로덕션 발급자로 재발급됐고, Higress를 통한 첫 스테이징 발급은 31초 걸렸습니다. 인증서는 공개 80 포트가 Higress에 닿아야 갱신되므로, 공유기 규칙이 80 포트를 다른 곳으로 보내면 갱신이 멈춥니다.

## 이전 방법과 재사용할 것

공유기는 포트 단위로 보내서 호스트를 나눌 수 없습니다. 브리지(호스트를 Higress로 넘기는 nginx Ingress)로 호스트를 하나씩 옮기는 계획을 dev 호스트 둘에 시험했고 되지만 규칙이 셋 있습니다.

1. Higress로 HTTPS로 넘깁니다. 평문 HTTP로 넘기면 Higress가 `X-Forwarded-Proto`를 `http`로 덮어씁니다.
2. SNI 설정과 함께 `proxy-ssl-secret`을 둡니다. 시크릿이 없으면 ingress-nginx가 `proxy-ssl-name`과 SNI 설정을 무시하고 SNI 없이 접속해서 Higress가 핸드셰이크를 끊습니다. 첫 시도가 정확히 이 이유로 502가 났습니다.
3. 본문 크기처럼 아직 의미 있는 제한은 브리지에 남깁니다.

결국 이전은 한꺼번에 했습니다. 모든 호스트에 먼저 Higress Ingress를 두고(nginx Ingress의 복사본, Higress 주소에서 실제 호스트 이름으로 확인), 그다음 공유기를 바꾸고, 그다음 모든 Ingress를 제자리에서 `nginx`에서 `higress`로 바꿨습니다. 제자리 변경이 중요한 이유는, cert-manager가 Ingress용으로 만든 Certificate가 그 Ingress에 소유되어 있어서 Ingress를 다시 만들면 Certificate가 지워지기 때문입니다.

비용 대비 효과가 컸던 확인은 이렇습니다. 모든 호스트의 상태, 인증서, 본문, 리다이렉트를 옛 경로와 새 경로에서 비교하기, 고유한 경로를 요청해서 새 게이트웨이 로그에서 찾기, 변경마다 공개 호스트를 0.5초 간격으로 감시하기입니다. 시험은 #314와 #326에 적혀 있습니다.

## 알아 둘 한계

- 게이트웨이는 워커 노드가 필요합니다. 컨트롤 플레인 노드에는 올리지 않고, 워커 3대에서 한 대를 잃으면 파드 2개가 남습니다.
- 주소는 한 번에 한 노드가 광고하고, 준비된 게이트웨이 파드가 있는 노드 중에서 고릅니다. 광고 노드가 바뀌면 몇 초 동안 연결이 끊길 수 있습니다.
- 웹 주소의 풀에는 노드가 갖지 않은 주소만 두어야 합니다. 노드 주소와 겹치는 풀이 ARP 충돌을 일으킨 적이 있습니다([cluster-design.md](../architecture/cluster-design.md) 참고).

## 롤백

ingress-nginx 차트는 `helm/ingress`에 벤더링된 채로 남아 있고(배포는 안 함) 배포만 사라졌습니다. 되돌리려면 제거 이전의 git 기록에서 `ingress-nginx` Application과 nginx ClusterIssuer를 복원하고, Ingress를 nginx 발급자와 `nginx` 클래스로 되돌리고, 공유기가 노드를 다시 가리키게 합니다. Higress와 ingress-nginx는 상태를 공유하지 않으므로 양방향 모두 설정 변경입니다.
