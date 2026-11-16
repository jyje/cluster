# ingress-nginx 제거 기록

추적 이슈: #326(Higress로 이전), #207. ingress-nginx를 Higress로 바꾸면서 어떤 리소스를 지웠는지, 무엇을 일부러 남겼는지, Argo CD가 스스로 지우지 못하는 것이 무엇인지, 아무것도 남지 않았는지 어떻게 확인하는지를 기록합니다. 설계와 이유는 [envoy-gateway-migration-ko.md](../networks/envoy-gateway-migration-ko.md)에 있습니다.

## 지운 것

| 위치 | 지운 것 |
|---|---|
| Argo CD | Application `ingress-nginx`, `hermes-henry-route`, 그리고 웹용인 Homer, error-pages, Gameplane의 Envoy Gateway 웹 라우트 |
| `kube-system` | ingress-nginx DaemonSet과 파드, Service, ConfigMap, RBAC, IngressClass `nginx`, 어드미션 웹훅 |
| cert-manager | ClusterIssuer `nginx-letsencrypt-stag`, `nginx-letsencrypt-prod` |
| MetalLB | 노드 자신의 주소를 담은 풀과 그 광고 |
| Envoy Gateway | `envoy-web` GatewayClass, EnvoyProxy, Gateway, 프록시, 네임스페이스 4개의 감시 Role. 컨트롤러는 이제 `envoy-gateway-system`과 `gameplane-games`만 감시 |
| Higress | 평가용 객체: echo, whoami, httpbin 백엔드, 모든 시험 Ingress, 자체 서명 TLS 확인, 브리지 시험, 스테이징 프로브 |
| 저장소 | `ingress-nginx` Application, 호환성 시험 스크립트, 은퇴한 Traefik 문서 |
| 클러스터 | 빈 네임스페이스 `traefik-henry-pilot` |

## 일부러 남긴 것

- 벤더링된 차트 `helm/ingress`(ingress-nginx)와 `helm/traefik`. 어떤 것도 배포하지 않으며 `helm/README.md`의 행에도 그렇게 적었습니다.
- 쓰고 있는 MetalLB 풀(웹용과 게임용). 비공개 설정에 있고 git에 없어서 Argo CD가 관리하거나 지운 적이 없습니다.
- 게임 UDP Gateway를 위한 Envoy Gateway와, Envoy Gateway 자신이 필요로 하는 `topology-injector` 웹훅.
- 쓰지 않지만 이번 이전과 무관한 옛 Istio ClusterIssuer.
- `gameplane-envoy` Certificate. Gameplane 호스트의 인증서이고 이름은 옛 이름 그대로입니다.

## Argo CD가 지우지 못하는 것

Argo CD는 자기가 관리하는 것만 지웁니다. Certificate가 만든 시크릿, ACME 계정 키, 리더 선출 객체는 거기에 해당하지 않아서 남았고 이름을 지정해 지웠습니다.

- `kube-system`: 시크릿 `ingress-nginx-admission`(웹훅 인증서), Lease `ingress-nginx-leader`, 시크릿 `nginx-letsencrypt-prod`, `nginx-letsencrypt-stag`(지운 발급자의 ACME 계정 키).
- 지운 Certificate의 TLS 시크릿: `error-pages-envoy-tls`, `homer-envoy-tls`, `acme-probe-staging`, `c-tls`.

앱 오브 앱스에서 Application을 지우면 루트는 prune하지 않습니다(루트는 설계상 prune하지 않습니다). 그런 Application은 자기 리소스와 함께 개별로 지우고, 루트를 prune하지 마세요.

## 남은 것이 없는지 확인

아래 확인은 표시된 경우를 빼고 아무것도 출력되지 않아야 합니다.

```bash
kubectl get ingress -A -o json | jq -r '.items[] | select(.spec.ingressClassName != "higress") | .metadata.namespace + "/" + .metadata.name'
```

```bash
kubectl get ingressclass,validatingwebhookconfiguration,clusterrole,clusterrolebinding --no-headers | grep -i nginx
```

```bash
kubectl -n kube-system get deploy,ds,svc,cm,secret,sa,role,rolebinding,job,pdb,lease --no-headers | grep -i nginx
```

```bash
kubectl get certificate -A -o json | jq -r '.items[] | select(.spec.issuerRef.name | test("nginx")) | .metadata.namespace + "/" + .metadata.name'
```

```bash
kubectl get secret -A --no-headers | grep -E "envoy-tls|acme-probe"
```

마지막 확인에서는 Gameplane Ingress가 쓰는 `gameplane-system/gameplane-envoy-tls`만 나오는 것이 정상입니다.

## 다음에 컨트롤러를 제거할 때

1. 그것을 쓰는 Ingress와 Certificate를 찾아 먼저 옮깁니다. Ingress는 제자리에서 옮겨야 각 Ingress가 소유한 Certificate가 지워지지 않습니다.
2. LoadBalancer Service가 노드 주소 풀에 들어가지 않는지 확인합니다.
3. Application을 자기 리소스와 함께 개별로 지운 뒤, 발급자와 풀은 이름을 지정해 prune합니다.
4. 위 확인을 돌리고, 단계마다 전후에 모든 공개 호스트를 요청합니다.
