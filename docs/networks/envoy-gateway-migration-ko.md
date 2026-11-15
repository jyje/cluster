# Envoy Gateway 마이그레이션

추적 이슈: #207. ingress-nginx에서 Envoy Gateway로 웹 트래픽을 옮기는 설계와, 포트를 바꾸기 전에 확인할 항목을 정리합니다.

## 현재 상태

- Envoy Gateway는 `envoy-gateway-system`에서 돌고 있습니다. `envoy-web` Gateway(ClusterIP, 아직 외부 진입점 없음)와 `factorio` Gateway(UDP)가 있습니다.
- 80, 443 포트는 아직 ingress-nginx가 노드 네트워크에서 가지고 있고 모든 공개 호스트를 서비스합니다. 컷오버 전까지 외부에서 보이는 것은 바뀌지 않습니다.
- 먼저 옮기는 앱은 `homer-instance`(`app.jyje.online`)와 `error-pages`(`error.app.jyje.online`)입니다. 상태가 없고 위험이 낮기 때문입니다.

## 설계

### 리스너와 라우트

라우팅은 앱이 각자 소유합니다. 앱의 `Gateway`, `Certificate`, `HTTPRoute`는 그 앱의 Argo CD Application(`extraResources`)에 앱 네임스페이스로 선언합니다. Gateway에는 앱 호스트용 HTTPS 리스너가 8443 포트에 하나 있고, 자기 네임스페이스의 라우트만 받습니다(`allowedRoutes.namespaces.from: Same`). 그래서 다른 앱이 남의 호스트를 가로챌 수 없습니다.

이 Gateway들은 모두 공용 `envoy-web` GatewayClass(`manifests/envoy-factorio-gateways/web-gatewayclass.yaml`)를 씁니다. 이 클래스의 `EnvoyProxy`에 `mergeGateways: true`가 있어서 클래스 안의 모든 Gateway가 프록시 한 벌을 같이 씁니다. 앱을 추가해도 프록시 파드가 늘지 않고(노드 메모리가 빠듯합니다), 컷오버 때 옮길 포트도 한 벌입니다. 대신 클래스 전체에서 리스너가 포트, 프로토콜, 호스트명 조합으로 유일해야 하고, 겹치면 `Accepted=False`로 거부됩니다. `factorio` Gateway는 UDP LoadBalancer Service가 필요해서 별도 클래스를 씁니다.

이 라우트들은 아직 휴면 상태입니다. 실제 호스트 이름을 갖고 있지만, 외부에서 Gateway로 들어오는 트래픽이 없습니다. Ingress는 그대로 남아 계속 서비스합니다.

컨트롤러는 `envoy-gateway` Application에 적힌 네임스페이스만 지켜봅니다. 첫 Gateway나 라우트를 만들기 전에 거기에 네임스페이스를 추가해야 합니다. 네임스페이스 자체는 지금처럼 따로 관리합니다.

Hermes Henry pilot Gateway는 아직 `manifests/envoy-factorio-gateways/henry-gateway.yaml`에 있습니다. 공용 클래스로 옮겨 놓았고, 나중에 같은 패턴으로 앱 쪽으로 옮길 수 있습니다.

### 인증서

앱마다 Gateway 옆에 같은 네임스페이스로 명시적 `Certificate`를 선언합니다. 그래서 TLS 시크릿에 네임스페이스를 넘나드는 `ReferenceGrant`가 필요 없습니다. Gateway 어노테이션은 쓰지 않습니다.

- 80 포트를 아직 ingress-nginx가 받는 동안에는 그쪽 HTTP-01 solver만 챌린지를 끝낼 수 있습니다. 그래서 기존 `nginx-letsencrypt-prod` 발급자를 씁니다.
- Certificate는 옛 Ingress가 사라진 뒤에도 계속 갱신되므로, 시크릿이 Ingress에 매이지 않습니다.
- 컷오버 때 80 포트가 Envoy로 넘어가면, Certificate를 Gateway API HTTP-01 solver가 있는 발급자로 옮기고 cert-manager에 `config.gatewayAPI.enabled: true`를 켭니다. 지금 켜지 않는 이유는, 80 포트가 Envoy를 가리키기 전에는 그 solver가 챌린지를 끝낼 수 없고 cert-manager만 재시작되기 때문입니다.

### Homer 카드

homer-operator는 아직 `enableGatewayAPI: false`라서 카드는 Ingress 어노테이션에서 계속 나옵니다. 컷오버 때 옵션을 켜고, 어노테이션을 HTTPRoute로 옮기고, Ingress를 지우는 일을 한 번에 해서 카드가 중복되지 않게 합니다.

## 컷오버 전 확인

Envoy 서비스로 포트 포워딩하고 각 호스트를 실제 이름으로 요청하면, 공개 트래픽을 건드리지 않고 TLS와 라우팅을 확인할 수 있습니다.

```bash
kubectl -n envoy-gateway-system port-forward \
  $(kubectl -n envoy-gateway-system get svc -l gateway.envoyproxy.io/owning-gatewayclass=envoy-web -o name) 8443:8443
```

```bash
curl -sI --resolve app.jyje.online:8443:127.0.0.1 https://app.jyje.online:8443/
```

```bash
curl -sI --resolve error.app.jyje.online:8443:127.0.0.1 https://error.app.jyje.online:8443/
```

Gateway가 `Programmed=True`인지, 인증서가 발급된 뒤 두 리스너가 `ResolvedRefs=True`인지, 각 라우트가 `Accepted=True`인지도 확인합니다.

## 컷오버 개요

1. cert-manager의 Gateway API 지원을 켜고 Gateway API solver가 있는 발급자를 추가한 뒤, 두 Certificate를 그 발급자로 옮깁니다.
2. ACME 챌린지용 HTTP 리스너와 HTTP에서 HTTPS로의 리다이렉트를 Gateway에 추가합니다.
3. 노드의 80, 443 포트를 비우고(ingress-nginx DaemonSet 중지) Envoy를 그 포트로 노출합니다. 짧은 중단이 예상되므로 시간을 잡아서 진행합니다.
4. homer-operator의 `enableGatewayAPI`를 켜고 Homer 어노테이션을 HTTPRoute로 옮깁니다.
5. 옮긴 앱의 Ingress를 지우고 다음 묶음에 같은 일을 반복합니다.

## 롤백

새 경로가 검증될 때까지 ingress-nginx 매니페스트를 git에 남겨 둡니다. 되돌릴 때는 ingress-nginx DaemonSet을 호스트 포트에 다시 띄우고 Cloudflare Tunnel과 라우터를 그쪽으로 돌립니다. Ingress와 그 인증서는 각자의 제거 단계 전까지 그대로라서 데이터는 잃지 않습니다.
