# UDP 게임 Gateway

`envoy-gateway-system`의 `games` Gateway가 공개 게임 트래픽을 Gameplane이 돌리는 서버로 보냅니다. Gateway,
프록시, 라우트는 `manifests/envoy-gateways/`에 있고, 서버 자체는 대시보드에서 만듭니다([gameplane-ko.md](gameplane-ko.md) 참고).

## 경로

공유기가 포워딩하는 WAN UDP 포트, 전용 MetalLB 풀의 LoadBalancer 주소, `games` Gateway의 Envoy 프록시,
`gameplane-games`의 `UDPRoute`, 게임 서버의 Service 순서입니다. 공개 이름은 다른 `app.jyje.online` 이름들처럼
공유기 DDNS 호스트를 가리키는 CNAME입니다. 공유기 포워딩은 Git 밖에 있습니다.

## 주소 풀

풀은 비공개 구성이라 이 저장소에 없습니다. DHCP 범위와 다른 풀 밖의 예약된 LAN 주소 하나를 담고 있고
`autoAssign: false`이며, 프록시 Service가 어노테이션으로 그 풀을 지정합니다. 게임 Service에 기본 풀을 쓰지
마세요. 기본 풀에는 노드 주소가 들어 있고, 노드 주소를 Service에 주면 전에 ARP 충돌이 났습니다.

MetalLB v0.13.3은 `serviceAllocation`을 지원하지 않아서 어떤 Service가 풀을 가져가는지 제한하지 못합니다. 옛
`metallb.universe.tf/address-pool` 키를 따르므로 매니페스트는 그 키와 새 키를 모두 지정합니다. 컨트롤러를 올리기
전에 셀렉터 제한을 다시 넣으세요.

### 풀 이름 바꾸기

MetalLB 풀은 이름을 바꿀 수 없고 두 풀이 같은 주소를 가질 수도 없어서, 이름 변경은 Git 밖의 수동 작업입니다.
이유는 이름이 Service가 나르는 내용을 드러내지 않아야 하기 때문입니다. 예약 주소가 잠시 풀려나므로 공개 UDP
포트가 1~3분 끊깁니다. 접속자가 없을 때 하세요.

1. `games-gateway.yaml`의 어노테이션 두 줄을 바꾼 변경을 병합합니다. `envoy-udp-poc` Application은 수동
   sync라서 이 시점에는 아무것도 바뀌지 않습니다.
2. 옛 `IPAddressPool`과 `L2Advertisement`를 저장하고, 저장본에서 이름을 바꾸고 `L2Advertisement`의
   `ipAddressPools`도 새 이름으로 고칩니다. 옛 쌍을 지우고 새 쌍을 한 번에 적용합니다.
3. `envoy-udp-poc`을 sync합니다. 프록시 Service가 같은 주소를 다시 받습니다.
4. `kubectl get svc -n envoy-gateway-system`의 `EXTERNAL-IP`가 예약 주소인지 확인하고, 게임에 한 번 접속합니다.

예시 값입니다(실제 주소와 이름으로 바꿔 쓰세요).

```bash
kubectl -n metallb-system get ipaddresspool old-pool -o yaml > pool.yaml
# 수정: metadata.name -> new-pool, spec.addresses는 "192.0.2.10/32" 그대로
kubectl -n metallb-system delete ipaddresspool,l2advertisement old-pool
kubectl apply -f pool.yaml
```

## 배치

프록시는 4KB 페이지 노드(`raspi.type: 4b`)에서 돌면 안 됩니다. Envoy의 TCMalloc이 거기서 힙을 매핑하지 못하고
시작 때 죽습니다. 게임 서버 자체도 `5b` 노드에서 돌려야 합니다. [node-labels-ko.md](node-labels-ko.md)를 보세요.

## 네임스페이스

Envoy 컨트롤러는 `envoy-gateway` Application에 적힌 네임스페이스만 지켜보므로 `gameplane-games`가 그 목록에
있습니다. 리스너는 그 네임스페이스의 라우트만 받습니다.

## 라우트 뒤의 서버 바꾸기

`games-route.yaml`의 `backendRefs`를 새 서버의 Service 이름으로 고치고 `envoy-udp-poc`를 동기화합니다.
Application은 기존 Gateway가 계속 추적되도록 옛 이름을 유지합니다. 라우트가 참조가 해석된 `Accepted`
상태인지 확인하고 클라이언트로 접속해 봅니다.

## 롤백

`backendRefs`를 이전 Service로 되돌리고 동기화합니다. 주소, 공유기 포워딩, DNS 이름은 바뀌지 않습니다.
