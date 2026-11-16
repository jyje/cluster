# 공식 Helm 차트로 n8n 운영하기

이 문서는 `n8n` Application을 8gears 차트(2.1.1)에서 공식 차트(1.19.0)로 옮기는 작업 계획입니다. 추적 이슈: #256.

이 변경의 Application은 **자동 동기화가 꺼져 있습니다**. 병합해도 전환이 시작되지 않습니다. 백업을 마친 뒤 직접 동기화하세요.

## 유지되는 것과 바뀌는 것

| 항목 | 8gears 릴리스 | 이 변경의 공식 차트 |
| :-- | :-- | :-- |
| 릴리스 이름 | `n8n` | `n8n` (`fullnameOverride`) |
| PVC | `n8n`, 10Gi, `subdir-usb` | `n8n`, 같은 크기와 클래스. 같은 객체라 데이터가 남습니다. |
| ConfigMap, ServiceAccount | `n8n` | `n8n` |
| Deployment, Service, Ingress | `n8n` | `n8n-main`. 차트가 `-main`을 붙이며 값으로 바꿀 수 없습니다. |
| 파드 셀렉터 | 8gears 라벨 | 공식 라벨. Deployment 셀렉터는 제자리에서 바꿀 수 없습니다. |
| 데이터베이스 | 볼륨 안의 SQLite | 볼륨 안의 SQLite (`queueMode` 끔, `database.type: sqlite`) |
| Valkey | 배포됨 | 없어짐 |
| 이미지 | `n8nio/n8n:2.6.2` | 차트 기본값 `2.47.4`. 첫 시작에 n8n이 데이터를 옮깁니다. |
| 호스트, TLS, Homer 어노테이션 | 그대로 | 그대로 |

차트의 셀렉터 라벨 `app.kubernetes.io/name: n8n`이 같아서 Homer 카드는 계속 보입니다.

## 시크릿

차트는 `secretRefs.existingSecret`이 가리키는 시크릿에서 네 개의 키를 읽습니다.

| 키 | 값 |
| :-- | :-- |
| `N8N_ENCRYPTION_KEY` | n8n이 이미 쓰는 키 |
| `N8N_HOST` | `n8n.app.jyje.online` |
| `N8N_PORT` | `5678` |
| `N8N_PROTOCOL` | `https` |

8gears 릴리스는 키를 지정하지 않아서, n8n이 데이터 볼륨 안의 `/home/node/.n8n/config`에 `encryptionKey`로 직접 만들었습니다. 그 값을 시크릿에 복사하세요. 시크릿의 키가 다르면 저장된 자격 증명을 복호화할 수 없습니다. 키를 로그에 찍거나 커밋하지 마세요. 저장소의 SealedSecret 절차로 봉인하세요.

## 리허설 (운영에 영향 없음)

1. 볼륨을 백업합니다. SQLite 파일이 일관되도록 먼저 쓰는 쪽을 멈추세요.
   ```bash
   kubectl -n n8n scale deploy/n8n --replicas=0
   kubectl -n n8n run n8n-backup --rm -i --restart=Never --image=busybox \
     --overrides='{"spec":{"containers":[{"name":"b","image":"busybox","command":["sh","-c","cp -a /data /backup/n8n-$(date +%F)"],"volumeMounts":[{"name":"d","mountPath":"/data"},{"name":"b","mountPath":"/backup"}]}],"volumes":[{"name":"d","persistentVolumeClaim":{"claimName":"n8n"}},{"name":"b","persistentVolumeClaim":{"claimName":"<backup-pvc>"}}]}}'
   kubectl -n n8n scale deploy/n8n --replicas=1
   ```
   `<backup-pvc>`는 직접 관리하는 볼륨으로 바꾸세요. 복사본에 `database.sqlite`와 `config`가 있는지 확인하세요.
2. Application 값으로 차트를 렌더링해서 이름을 비교합니다.
   ```bash
   yq '.spec.source.helm.valuesObject' clusters/r4spi/apps/n8n.yaml > /tmp/n8n-values.yaml
   helm template n8n helm/n8n-io/n8n-1.19.0 -f /tmp/n8n-values.yaml -n n8n
   ```
3. 복사본으로 새 차트와 이미지를 시험합니다. 백업을 임시 네임스페이스의 새 PVC로 복원하고, `ingress.enabled=false`와 `persistence.existingClaim=<복원한 PVC>`, 같은 시크릿으로 차트를 설치합니다. 포트 포워딩으로 로그인, 자격 증명, 워크플로 하나를 확인하세요. 시험하는 동안 외부 부작용(스케줄 트리거)은 막으세요.

## 전환

1. 마지막 백업을 합니다(위 1단계). 원래 볼륨은 롤백용으로 그대로 둡니다.
2. `n8n` 네임스페이스에 시크릿 `n8n-encryption`을 만듭니다.
3. 이 변경을 병합합니다. 아직 동기화되지 않습니다.
4. Argo CD에서 `n8n`을 **Prune 끔**으로 직접 동기화합니다. 옛 Deployment `n8n`과 Valkey 객체는 새 매니페스트에 없어서 out of sync로 보입니다. 새 파드가 Ready가 된 뒤에 옛 Deployment를 직접 지워서, 볼륨을 쓰는 쪽이 하나만 남게 하세요.
5. 확인: Application이 Synced와 Healthy, 파드 Ready, 로그인, 저장된 자격 증명, 워크플로 하나 실행, 웹훅 하나 응답.
6. 안정된 기간이 지나면 남은 8gears 객체를 지우고, 자동 동기화를 다시 켜고, Renovate 카탈로그 항목(`helm-sources/catalog.yaml`)을 공식 소스로 옮깁니다. 이 마지막 변경은 더 일찍 할 수 없습니다. 벤더링 검사가 Application이 벤더링하는 차트를 가리킬 것을 요구하기 때문입니다.

## 롤백

1. `n8n-main`을 0으로 줄입니다.
2. 이 변경을 되돌려 옛 Application을 복원하고 동기화합니다. 같은 PVC로 8gears 릴리스가 돌아옵니다.
3. n8n이 이미 데이터를 2.47.4로 옮겼다면, 옛 2.6.2 이미지가 열지 못할 수 있습니다. 먼저 전환 전 백업을 PVC에 복원하세요. 전환 뒤에 받아들인 워크플로 실행은 따로 처리해야 합니다.
