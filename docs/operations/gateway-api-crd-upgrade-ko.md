# Gateway API CRD 업그레이드 (1.2.1에서 1.6.3)

English version: [gateway-api-crd-upgrade.md](gateway-api-crd-upgrade.md)

## 개요

`gateway-api` Application은 `helm/gateway-api/` 아래의 작은 래퍼 차트로 표준
채널 Gateway API CRD를 설치합니다. 래퍼에는 업스트림 릴리스 매니페스트
`standard-install.yaml`이 수정 없이 들어 있고, 이 저장소의 `extraResources`
훅이 더해져 있습니다.

| 항목 | 1.2.1 | 1.6.3 |
|------|-------|-------|
| CRD 수 | 5 | 10 |
| 새 CRD | | `BackendTLSPolicy`, `ListenerSet`, `TCPRoute`, `TLSRoute`, `UDPRoute` |
| 그 밖의 객체 | 없음 | `ValidatingAdmissionPolicy`와 바인딩 `safe-upgrades.gateway.networking.k8s.io` |
| 기존 5개의 저장 버전 | `v1` (`ReferenceGrant`는 `v1beta1`) | 변경 없음 |

`ReferenceGrant`는 1.6.3부터 `v1`도 제공하지만 저장 버전은 계속 `v1beta1`이라서
저장 버전 이전 작업이 필요 없습니다.

## safe-upgrades 정책이 하는 일

번들에는 `gateway.networking.k8s.io` 그룹의 CRD에 대해 두 가지를 거부하는
어드미션 정책이 들어 있습니다.

1. 표준 채널 CRD 위에 실험 채널 CRD 설치
2. v1.5.0보다 오래된 CRD 번들 설치

두 번째 규칙은 롤백에 영향이 있습니다. 업그레이드 후에는 커밋만 되돌려 Argo CD가
1.2.1을 다시 적용하게 해서는 거부됩니다.

## 롤백

클러스터에 접근할 수 있는 곳에서 아래를 실행한 뒤 커밋을 되돌립니다.

```sh
kubectl delete validatingadmissionpolicybinding safe-upgrades.gateway.networking.k8s.io
```

그러면 Argo CD가 오류 없이 1.2.1을 적용합니다. 새 CRD 5개는 남지만(자동 동기화는
prune하지 않음) 무해합니다. 1.6.3을 다시 동기화하면 바인딩이 다시 만들어집니다.

## 시험

업그레이드, 롤백, 재업그레이드를 일회용 kind 클러스터(쿠버네티스 v1.36.4와
v1.37.0)에서 Argo CD와 같은 필드 매니저의 서버 측 적용으로 실행했습니다.
클러스터에는 운영과 같은 `GatewayClass` 3개와 샘플 `Gateway`, `HTTPRoute`,
`ReferenceGrant`를 두었습니다.

| 확인 | 결과 |
|------|------|
| 1.2.1에서 1.6.3 업그레이드 | 성공, CRD 10개 모두 번들 v1.6.3 |
| 전후 객체 | spec 모두 동일 |
| 기존 종류를 `v1beta1`로, `ReferenceGrant`를 새 `v1`로 조회 | 조회됨 |
| 같은 적용을 한 번 더 | 변경 없음 (`resourceVersion` 유지) |
| 정책이 있는 상태에서 1.2.1 재적용 | 거부됨 |
| 바인딩 삭제 후 1.2.1 재적용 | 성공, 객체 동일 |
| 롤백 후 다시 업그레이드 | 성공, 바인딩 복귀 |
| 표준 위에 실험 채널 CRD | 거부됨 |

운영 API 서버도 렌더링한 번들을 서버 측 dry-run에서 받아들였습니다.

## 컨트롤러

업그레이드 시점에는 Gateway API 컨트롤러가 실행 중이지 않습니다. `Gateway`나
Route 객체가 없고, `GatewayClass` 3개는 현재 꺼져 있는 Istio가 남긴 것입니다.
Istio 1.30의 공식 대상은 Gateway API v1.5.1입니다. Istio를 다시 켜기 전에 해당
버전이 설치된 CRD 번들을 지원하는지 확인하거나, Istio가 문서화한 버전으로
래퍼를 고정하세요.
