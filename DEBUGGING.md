# Istio-system namespace debugging

디버깅 일시: 2026-02-05  
대상: `istio-system` 네임스페이스 및 관련 웹훅

---

## 1. 점검 목적

- `istio-system` 내 Pod/Deployment/DaemonSet 상태 확인
- Istio 웹훅(Validating/Mutating) 존재 및 설정 확인
- 네임스페이스 메타데이터 및 최근 이벤트 확인
- istiod 로그로 컨트롤 플레인·ztunnel 연동 상태 확인

---

## 2. 수행한 명령과 결과

### 2.1 리소스 목록

```bash
kubectl get all -n istio-system
kubectl get pods -n istio-system -o wide
```

**결과 요약**

| 리소스 | 개수 | 상태 |
|--------|------|------|
| Pod (istio-cni-node) | 4 | 1/1 Running |
| Pod (istiod) | 1 | 1/1 Running |
| Pod (ztunnel) | 4 | 1/1 Running |
| Service (istiod) | 1 | ClusterIP |
| DaemonSet (istio-cni-node, ztunnel) | 2 | 4/4 desired/current |
| Deployment (istiod) | 1 | 1/1 ready |
| HPA (istiod) | 1 | 1 replica, 0% cpu |

→ **모든 Pod 정상 Running**, 리소스 개수와 배포 형태는 Ambient 설치(istiod + CNI + ztunnel)와 일치.

### 2.2 웹훅 설정

```bash
kubectl get validatingwebhookconfigurations,mutatingwebhookconfigurations
```

**Istio 관련 웹훅**

- `istio-validator-istio-system` (Validating)
- `istiod-default-validator` (Validating)
- `istio-sidecar-injector` (Mutating)

→ Mutating 웹훅이 있어 `image: auto` 치환 등 사이드카/게이트웨이 injection 가능.

### 2.3 네임스페이스 상세

```bash
kubectl get namespace istio-system -o yaml
```

**결과**

- `phase: Active`
- `labels`: `kubernetes.io/metadata.name: istio-system` 만 존재 (injection 라벨 없음)
- `istio-system` 은 컨트롤 플레인 전용이므로 `istio-injection` 라벨이 없어도 됨. injection 라벨은 게이트웨이/워크로드가 배포되는 네임스페이스(예: `istio-ingress`)에만 필요.

### 2.4 이벤트

```bash
kubectl get events -n istio-system --sort-by='.lastTimestamp'
```

**결과:** `No resources found in istio-system namespace.`  
→ 최근 이벤트 없음, 비정상 스케줄/실패 징후 없음.

### 2.5 istiod 로그

```bash
kubectl logs -n istio-system deployment/istiod --tail=30
```

**결과:**  
- ztunnel 4개에 대한 WDS/WADS PUSH 정상
- `validationController successfully updated` (istio-validator-istio-system, istiod-default-validator)
- XDS push, ConnectedEndpoints:4 등 정상 메시지

→ 컨트롤 플레인과 데이터 플레인(ztunnel) 연동 정상.

### 2.6 ValidatingWebhookConfiguration failurePolicy

```bash
kubectl get validatingwebhookconfiguration istio-validator-istio-system -o jsonpath='{.webhooks[0].failurePolicy}'
```

**결과:** `Fail` (클러스터 현재 값)

Argo CD에서 보고하는 차이:

- **LIVE:** `failurePolicy: Fail`
- **DESIRED (Helm 차트):** `failurePolicy: Ignore`

차트(istio-istiod)가 생성하는 desired 상태는 `Ignore` 이며, Argo CD Sync 시 클러스터가 `Ignore` 로 맞춰짐.  
`Ignore` 로 두면 istiod 장애 시에도 해당 웹훅 때문에 API 요청이 막히지 않아 운영상 유리함.

---

## 3. 종합

| 항목 | 상태 | 비고 |
|------|------|------|
| Pod (istiod, CNI, ztunnel) | 정상 | 모두 Running |
| Service / Deployment / DaemonSet | 정상 | 목록 및 replica 일치 |
| 네임스페이스 | 정상 | Active, 이벤트 없음 |
| istiod 로그 | 정상 | ztunnel 연동·validation 업데이트 정상 |
| 웹훅 존재 | 정상 | Validating 2종, Mutating 1종 |
| failurePolicy 불일치 | OutOfSync | LIVE=Fail, DESIRED=Ignore → Sync 시 Ignore 로 정리 가능 |

**결론:** `istio-system` 네임스페이스와 Istio Ambient 컴포넌트는 현재 정상 동작 중.  
Argo CD에서 `istio-validator-istio-system` 의 desired(`failurePolicy: Ignore`)대로 Sync 하면 일치 상태로 유지할 수 있음.

---

## 4. 이후 참고용 명령

```bash
# Pod 상세 (이미지, 재시작 등)
kubectl describe pod -n istio-system -l app=istiod

# istiod 로그 레벨/에러 위주
kubectl logs -n istio-system deployment/istiod --tail=100 | grep -E 'error|warn|Error'

# 웹훅 상세
kubectl get validatingwebhookconfiguration istio-validator-istio-system -o yaml
kubectl get mutatingwebhookconfiguration istio-sidecar-injector -o yaml
```
