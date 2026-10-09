# Key Usage가 없는 클러스터 CA: Python 3.13+ strict TLS에서 거부됨

English version: [cluster-ca-key-usage.md](cluster-ca-key-usage.md)

## 개요

Python 3.14 클라이언트(pifanctl)가 MicroK8s API 서버와 통신하지 못했습니다.
핸드셰이크가 OpenSSL 오류 92로 실패했습니다.

```text
CA cert does not include key usage extension
```

원인은 네트워크, 서버 인증서, 클라이언트 라이브러리가 아니라 **클러스터 CA 인증서**
였습니다. CA에 **Key Usage** 확장이 없었습니다. 오래된 MicroK8s 버전은 이런 CA를
만들었고, Python 3.13부터 strict X.509 검사가 기본으로 켜지면서 런타임을 3.12에서
3.14로 옮기자마자 실패하기 시작했습니다.

해결은 **같은 키, subject, 일련번호, 만료일**로 CA 인증서를 다시 발급하면서 Key
Usage를 추가하고, 모든 노드의 파일을 교체하는 것이었습니다. leaf 인증서는 하나도
다시 만들지 않았고, 노드가 클러스터를 떠나지도, 워크로드가 멈추지도 않았습니다.

| 항목 | 내용 |
|------|------|
| 증상 | strict TLS 클라이언트는 오류 92로 실패. Go 클라이언트(kubectl, Argo CD, kubelet)는 정상 |
| 원인 | CA 인증서에 `keyUsage`(`keyCertSign`) 확장이 없음 |
| 계기 | Python 3.13+의 `ssl.create_default_context()`가 `VERIFY_X509_STRICT`를 켬 |
| 해결 | 일련번호, subject, SKI를 유지한 채 Key Usage를 추가해 같은 키로 CA 재발급 |
| 영향 | API 재시작 1회(약 10초), 워크로드 영향 없음 |
| 추적 | cluster 이슈 #157, pifanctl PR #76과 이슈 #77 |

## 먼저 알아야 할 배경

### CA 인증서가 담아야 하는 것

다른 인증서를 서명하는 인증서에는 세 가지가 있어야 합니다.

| 확장 | 의미 | 이 CA의 상태 |
|------|------|--------------|
| Basic Constraints, critical, `CA:TRUE` | 이 인증서는 CA가 될 수 있음 | 있음 |
| Key Usage, `keyCertSign`(그리고 `cRLSign`) | 이 키로 인증서를 서명해도 됨 | **없음** |
| Subject/Authority Key Identifier | 인증서를 발급한 키와 연결 | 있음 |

RFC 5280은 CA 인증서에 Key Usage가 있다면 `keyCertSign`을 포함해야 하고, 넣는 것을
강하게 권장합니다. 예전 도구들은 확장이 없어도 눈감아 줬지만 strict 검증은 그렇지
않습니다.

### 일부 클라이언트만 실패하는 이유

`VERIFY_X509_STRICT`는 RFC 5280을 더 엄격하게 적용하는 OpenSSL 플래그입니다. Python
3.13이 기본 컨텍스트에 이 플래그(와 `VERIFY_X509_PARTIAL_CHAIN`)를 추가했고,
urllib3는 그 기본값을 그대로 씁니다.

| 클라이언트 | strict 검사 | 기존 CA 결과 |
|------------|-------------|--------------|
| Python 3.12 이하 | 기본 꺼짐 | 정상 |
| Python 3.13+ (pifanctl, Kubernetes Python 클라이언트) | 켜짐 | 오류 92로 실패 |
| Go (kubectl, kubelet, Argo CD, 컨트롤러) | Go 자체 검증기 | 정상 |

그래서 클러스터의 다른 구성요소는 문제를 전혀 눈치채지 못했습니다. strict 클라이언트가
탄광의 카나리아였던 셈입니다.

검증을 끄는 우회(`verify_ssl=False`, strict 플래그 제거, urllib3 패치, Python 3.12
유지)는 결함을 숨기고 보안을 약화하므로 일부러 쓰지 않았습니다.

## 클러스터 구성

MicroK8s는 PKI를 `$SNAP_DATA/certs`(`/var/snap/microk8s/current`)에 둡니다.

- 컨트롤 플레인 노드가 `ca.crt`와 `ca.key`를 갖고 모든 leaf 인증서(API 서버,
  kubelet, controller, scheduler, proxy, client)를 서명합니다.
- 워커 노드는 클러스터 CA의 사본을 `ca.remote.crt`로 갖습니다. 워커의 `ca.crt`는
  별개의 로컬 CA이며 이번 문제와 무관합니다.
- CA 인증서는 `credentials/*.config` kubeconfig에 `certificate-authority-data`로
  내장되고, kube-apiserver, kubelet, kube-controller-manager 인자에서 파일 경로로
  참조됩니다.
- 컨트롤러 매니저가 모든 네임스페이스에 `kube-root-ca.crt` ConfigMap으로 CA를
  게시하고, 파드는 이것을 신뢰 CA로 마운트합니다.
- `front-proxy-ca`는 다른 CA이고 건드리지 않았습니다.

## 조사 과정

1. Python 3.14로 API 엔드포인트에 읽기 전용 접속을 재현: 오류 92.
2. `openssl x509 -text`로 CA 확인: critical `CA:TRUE`, SKI/AKI 있음, **Key Usage 없음**.
3. 실제 Kubernetes Python 클라이언트(36.x, urllib3 2.8)로 같은 실패를 확인. 직접 만든
   테스트 코드의 부산물이 아님을 증명.
4. 이 CA를 신뢰하는 다른 곳을 조사해 영향 범위 파악: 노드 kubeconfig, kubelet 클라이언트
   CA, root CA ConfigMap. 웹훅과 Argo CD는 클러스터 CA를 쓰지 않았음.
5. 새 노드와 비교: 나중에 합류한 워커의 로컬 CA에는 이미 `Certificate Sign, CRL Sign`이
   있었음. 현재 MicroK8s는 올바른 CA를 만들고, 최초의 CA만 결함이 있었음.

## 실험 (아무것도 건드리기 전에, 오프라인)

같은 프로필(자체 서명, critical `CA:TRUE`, SKI/AKI, Key Usage 없음)의 임시 PKI와 그
CA로 서명한 서버 인증서를 만들어 시험했습니다.

| 실험 | 결과 |
|------|------|
| 기존 CA, `openssl verify -x509_strict` | 오류 92로 실패 |
| 기존 CA, non-strict | 통과 |
| 같은 키와 subject로 Key Usage를 넣어 재발급, **기존 leaf 그대로**, strict | 통과 |
| Python 3.14 핸드셰이크, 기존 CA와 재발급 CA | 실패, 통과 |
| 신/구 CA를 함께 담은 번들, **구 CA가 먼저** | 실패 |
| 신/구 CA를 함께 담은 번들, **신 CA가 먼저** | 통과 |

실험에서 배운 점:

- 서명은 CA **공개키**로 검증합니다. 키가 같으면 그 키로 발급한 모든 인증서가 계속
  유효합니다. 그래서 CA 인증서 재발급은 CA 키 교체(rotation)와 다릅니다.
- OpenSSL은 번들에서 처음 일치하는 발급자를 고릅니다. 구 CA를 앞에 두고 신/구를 같이
  배포하면 안 됩니다.

이 시험을 **컨트롤 플레인 노드에서** 실제 키로 다시 했습니다. 키는 제자리에서 읽기만
했고 복사하지 않았으며, 새 공개 인증서만 임시 디렉터리에 썼습니다. 여기서 핵심 함정이
나왔습니다.

## 일련번호 함정

노드에서의 첫 시도는 새 CA를 임의의 일련번호로 만들었고, 서버 인증서가 이렇게
실패했습니다.

```text
error 20 ... unable to get local issuer certificate
```

서버 인증서의 Authority Key Identifier에는 키 ID뿐 아니라 서명한 CA의 **발급자 이름과
일련번호**도 들어 있습니다.

```text
X509v3 Authority Key Identifier:
    keyid:<ski>
    DirName:/CN=<ca-subject>
    serial:<ca-serial>
```

OpenSSL은 이 필드를 모두 비교해 발급자를 찾습니다. 일련번호가 다른 재발급 CA는 더
이상 일치하지 않아 체인이 만들어지지 않습니다. `-set_serial 0x<기존 일련번호>`로 재발급
하자 해결됐습니다.

두 번째 발견: 클라이언트와 노드 인증서는 **AKI가 아예 없어서** CA와 무관하게 strict
검증에 실패합니다(오류 85). 이 인증서들은 서버 쪽 Go 구성요소가 검증하므로, 서버
인증서만 검증하는 Python 클라이언트에는 영향이 없습니다. 별개의 무해한 결함입니다.

## 사용한 절차

모든 명령은 노드에서 root로 실행했습니다. 키는 제자리에서 읽기만 했고 복사하지
않았습니다. `<serial>`, `<subject>`, `<days>`는 기존 인증서에서 가져옵니다.

### 1. 백업 (모든 노드)

```sh
umask 077
mkdir -p /root/ca-backup && chmod 700 /root/ca-backup
tar -cf /root/ca-backup/microk8s-pki-$(date +%Y%m%d-%H%M%S).tar \
  -C /var/snap/microk8s/current certs credentials args
```

이 아카이브에는 개인키가 들어 있으므로 Git 밖에 보관합니다.

### 2. 새 인증서 생성과 검증 게이트 (컨트롤 플레인)

```sh
S=/var/snap/microk8s/current
printf 'subjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid:always\nbasicConstraints=critical,CA:TRUE\nkeyUsage=critical,keyCertSign,cRLSign\n' > ext
openssl req -new -key $S/certs/ca.key -subj "<subject>" -out ca.csr
openssl x509 -req -in ca.csr -signkey $S/certs/ca.key \
  -days <days> -sha256 -set_serial 0x<serial> -extfile ext -out ca-new.crt
```

아래가 모두 만족될 때만 진행합니다.

- 일련번호, subject, SKI, 공개키가 기존 인증서와 동일
- `openssl verify -x509_strict -CAfile ca-new.crt server.crt`가 OK
- 나머지 leaf가 `-CAfile ca-new.crt`(non-strict)로 모두 OK

### 3. 컨트롤 플레인 교체

- 새 인증서를 `certs/ca.crt` 위에 덮어씁니다(소유자와 권한 유지).
- 각 `credentials/*.config`에서 디코딩한 값이 기존 CA와 같은 `certificate-authority-data`
  만 교체합니다.
- `microk8s.daemon-kubelite`를 재시작합니다. API는 약 10초 만에 돌아왔습니다.
- 이후 컨트롤러 매니저가 모든 네임스페이스의 `kube-root-ca.crt`를 갱신합니다. 약 1분
  걸렸으니 가정하지 말고 기다리며 확인합니다.

### 4. 워커를 한 대씩 교체

- 같은 게이트를 쓰되 기존 `certs/ca.remote.crt`와 비교합니다.
- `certs/ca.remote.crt`와 `kubelet.config`, `proxy.config`의 내장 CA를 교체합니다.
- `microk8s.daemon-kubelite`를 재시작하고, 노드가 Ready가 되고 파드가 Running인 것을
  확인한 뒤 다음 노드로 넘어갑니다.

키가 그대로이므로 아직 기존 파일을 신뢰하는 노드도 계속 동작합니다. 그래서 순차 교체가
안전합니다.

## 검증

- 기본 strict 컨텍스트의 Python 3.14가 API에 접속: OK.
- Python 3.12에 `VERIFY_X509_STRICT`를 추가해 **파드 안에서** 마운트된 `ca.crt`로 접속:
  OK.
- 모든 네임스페이스의 `kube-root-ca.crt`에 Key Usage가 있음.
- 모든 노드 Ready, 모든 Argo CD Application이 Synced와 Healthy.

인증 없이 보낸 Kubernetes 클라이언트 요청이 401을 받았다면, HTTP 응답이 왔다는 것은
이미 TLS가 성공했다는 좋은 신호입니다.

## 롤백

해당 노드의 아카이브를 `certs`, `credentials`, `args` 위에 복원하고
`microk8s.daemon-kubelite`를 재시작합니다. 전체를 되돌릴 때는 컨트롤 플레인부터 합니다.
MicroK8s에도 자체 인증서 작업의 undo가 있지만 손으로 수정한 파일은 되돌리지 못합니다.

## 일부러 하지 않은 것

- 새 CA 키, leaf 재발급, 노드 leave/rejoin, 워크로드 정지. 문서화된 `microk8s
  refresh-certs -e ca.crt` 절차는 이것들이 필요하지만, 같은 키 재발급에는 필요하지
  않았습니다.
- 어떤 곳에서도 검증을 끄지 않았습니다.
- `front-proxy-ca`와 AKI가 없는 클라이언트 인증서는 그대로 두었습니다.

## 다음에 확인할 것

- 런타임이나 라이브러리 업그레이드로 TLS 기본값이 바뀌면, strict 클라이언트 하나로
  모든 내부 CA를 일찍 시험합니다.
- CA 인증서를 재발급할 때 subject, 일련번호, SKI, 키를 유지합니다. leaf 인증서의 AKI가
  무엇을 고정하는지 확인합니다.
- 신뢰 번들에서는 순서가 중요합니다.
- CA를 게시하는 컨트롤러(여기서는 `kube-root-ca.crt`)는 갱신이 느립니다. 기다리며
  확인합니다.

## 참고 자료

- Python `ssl` 모듈, 기본 컨텍스트와 `VERIFY_X509_STRICT`:
  https://docs.python.org/3.14/library/ssl.html
- Python 3.13 TLS 변경 논의:
  https://discuss.python.org/t/python-3-13-x-ssl-security-changes/91266
- 같은 실패를 보고한 Kubernetes 클러스터 프로젝트:
  https://dev.hsrn.nyu.edu/hsrn-projects/kubernetes-bare-metal/-/issues/139
- Proxmox가 루트 CA에 Key Usage를 추가한 패치:
  https://lore.proxmox.com/all/s8ocy12d346.fsf@toolbox/t
- MicroK8s `refresh-certs`:
  https://canonical.com/microk8s/docs/command-reference#microk8s-refresh-certs-version-119
- RFC 5280, 4.2.1.3절(Key Usage)과 4.2.1.1절(Authority Key Identifier)
