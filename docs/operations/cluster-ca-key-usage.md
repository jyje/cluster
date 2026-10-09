# Cluster CA without Key Usage: rejected by Python 3.13+ strict TLS

Korean version: [cluster-ca-key-usage-ko.md](cluster-ca-key-usage-ko.md)

## Overview

A Python 3.14 client (pifanctl) could not talk to the MicroK8s API server. The
handshake failed with OpenSSL error 92:

```text
CA cert does not include key usage extension
```

The cause was the cluster CA certificate, not the network, the server
certificate or the client library. The CA had no **Key Usage** extension. Older
MicroK8s releases generated such a CA. Python 3.13 and later turn on strict
X.509 checks by default, so it started failing as soon as the runtime moved
from 3.12 to 3.14.

The fix was to reissue the CA certificate **with the same key, subject, serial
number and expiry**, adding Key Usage, then replace the file on every node. No
leaf certificate was reissued, no node left the cluster and no workload was
stopped.

| Item | Value |
|------|-------|
| Symptom | Strict TLS clients fail with error 92. Go clients (kubectl, Argo CD, kubelet) work |
| Root cause | CA certificate lacks a `keyUsage` extension (`keyCertSign`) |
| Trigger | Python 3.13+ sets `VERIFY_X509_STRICT` in `ssl.create_default_context()` |
| Fix | Same-key CA reissue with Key Usage, preserving serial, subject and SKI |
| Impact | One API restart (about 10 seconds), no workload impact |
| Tracking | Cluster issue #157, pifanctl PR #76 and issue #77 |

## Background you need

### What a CA certificate must say

A certificate that signs other certificates should carry three things.

| Extension | Meaning | What this CA had |
|-----------|---------|------------------|
| Basic Constraints, critical, `CA:TRUE` | This certificate is allowed to be a CA | yes |
| Key Usage, `keyCertSign` (and `cRLSign`) | The key may be used to sign certificates | **missing** |
| Subject and Authority Key Identifier | Link a certificate to the key that issued it | yes |

RFC 5280 says a CA certificate that is used to verify signatures must have
Key Usage with `keyCertSign` when the extension is present, and strongly
recommends it. Many older tools tolerated a missing extension. Strict
validation does not.

### Why only some clients fail

`VERIFY_X509_STRICT` is an OpenSSL flag that enforces more of RFC 5280. Python
3.13 added it (together with `VERIFY_X509_PARTIAL_CHAIN`) to the default
context. urllib3 relies on that default.

| Client | Strict check | Result with the old CA |
|--------|--------------|------------------------|
| Python 3.12 and older | off by default | works |
| Python 3.13+ (pifanctl, Kubernetes Python client) | on | fails, error 92 |
| Go (kubectl, kubelet, Argo CD, controllers) | Go's own verifier | works |

This is why nothing else in the cluster noticed the problem. A strict client is
the canary.

Workarounds that disable verification (`verify_ssl=False`, clearing the strict
flag, patching urllib3, or staying on Python 3.12) hide the defect and weaken
security. They were deliberately not used.

## How the cluster is built

MicroK8s keeps its PKI under `$SNAP_DATA/certs` (`/var/snap/microk8s/current`).

- The control-plane node holds `ca.crt` and `ca.key` and signs every leaf
  certificate (API server, kubelet, controller, scheduler, proxy, client).
- Worker nodes hold a copy of the cluster CA as `ca.remote.crt`. Their own
  `ca.crt` is a separate local CA and is not part of this problem.
- The CA certificate is embedded as `certificate-authority-data` in the
  `credentials/*.config` kubeconfigs, and referenced by file path in the
  kube-apiserver, kubelet and kube-controller-manager arguments.
- The controller manager publishes the CA into every namespace as the
  `kube-root-ca.crt` ConfigMap, which pods mount as their trusted CA.
- `front-proxy-ca` is a different CA and was not touched.

## Investigation

1. Reproduce read-only with Python 3.14 against the API endpoint: error 92.
2. Inspect the CA with `openssl x509 -text`: critical `CA:TRUE`, SKI and AKI
   present, **no Key Usage**.
3. Confirm with the real Kubernetes Python client (36.x, urllib3 2.8): the same
   failure, so this is not an artifact of a hand-written test.
4. Check what else trusts this CA, to size the blast radius: node kubeconfigs,
   the kubelet client CA, the root CA ConfigMaps. Webhooks and Argo CD did not
   use the cluster CA.
5. Compare with newer nodes: workers joined later had a local CA that already
   contained `Certificate Sign, CRL Sign`. Current MicroK8s generates a correct
   CA, so only the original one was defective.

## Experiments (offline, before touching anything)

A throwaway PKI was built with the same profile (self-signed, critical
`CA:TRUE`, SKI and AKI, no Key Usage) and a server certificate signed by it.

| Experiment | Result |
|------------|--------|
| Old CA, `openssl verify -x509_strict` | fails with error 92 |
| Old CA, non-strict | passes |
| Same key and subject reissued with Key Usage, **old leaf unchanged**, strict | passes |
| Python 3.14 handshake against old CA, then reissued CA | fails, then passes |
| Trust bundle with both old and new CA, **old first** | fails |
| Trust bundle with both, **new first** | passes |

Lessons from these tests:

- A signature is checked against the CA **public key**. If the key is the same,
  every certificate it issued stays valid. Reissuing the CA certificate is
  therefore different from rotating the CA key.
- OpenSSL picks the first matching issuer in a bundle. Never publish old and
  new together with the old one first.

The same test was then repeated **on the control-plane node** with the real key
read in place (the key was never copied; only the new public certificate was
written to a temporary directory). That run found the main trap.

## The serial number trap

The first on-node attempt generated the new CA with a random serial number and
the server certificate failed with:

```text
error 20 ... unable to get local issuer certificate
```

The server certificate's Authority Key Identifier contains not only the key id
but also the **issuer name and serial number** of the CA that signed it:

```text
X509v3 Authority Key Identifier:
    keyid:<ski>
    DirName:/CN=<ca-subject>
    serial:<ca-serial>
```

OpenSSL matches the issuer by all of these fields. A reissued CA with a new
serial no longer matches, so the chain is not built. Reissuing with
`-set_serial 0x<old-serial>` fixed it.

A second finding: client and node certificates have **no AKI at all**, so they
fail strict verification (error 85) regardless of the CA. They are verified by
Go components on the server side, so this does not affect Python clients, which
only verify the server certificate. It is a separate, harmless defect.

## Procedure that was used

All commands run as root on the node. Keys are read in place and never copied.
`<serial>`, `<subject>` and `<days>` come from the existing certificate.

### 1. Back up (every node)

```sh
umask 077
mkdir -p /root/ca-backup && chmod 700 /root/ca-backup
tar -cf /root/ca-backup/microk8s-pki-$(date +%Y%m%d-%H%M%S).tar \
  -C /var/snap/microk8s/current certs credentials args
```

Keep these archives outside Git. They contain private keys.

### 2. Build and gate the new certificate (control plane)

```sh
S=/var/snap/microk8s/current
printf 'subjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid:always\nbasicConstraints=critical,CA:TRUE\nkeyUsage=critical,keyCertSign,cRLSign\n' > ext
openssl req -new -key $S/certs/ca.key -subj "<subject>" -out ca.csr
openssl x509 -req -in ca.csr -signkey $S/certs/ca.key \
  -days <days> -sha256 -set_serial 0x<serial> -extfile ext -out ca-new.crt
```

Do not continue unless all of these hold:

- serial, subject, SKI and public key are identical to the old certificate
- `openssl verify -x509_strict -CAfile ca-new.crt server.crt` is OK
- every other leaf verifies with `-CAfile ca-new.crt` (non-strict)

### 3. Replace on the control plane

- Write the new certificate over `certs/ca.crt` (keeps ownership and mode).
- In each `credentials/*.config`, replace `certificate-authority-data` only
  where the decoded value equals the old CA.
- Restart `microk8s.daemon-kubelite`. The API was back in about 10 seconds.
- The controller manager then refreshes `kube-root-ca.crt` in all namespaces.
  This took about a minute, so wait and verify instead of assuming.

### 4. Replace on each worker, one at a time

- Same gates, comparing against the old `certs/ca.remote.crt`.
- Replace `certs/ca.remote.crt` and the embedded CA in `kubelet.config` and
  `proxy.config`.
- Restart `microk8s.daemon-kubelite`, wait for the node to be Ready, check that
  its pods are Running, then move to the next node.

Because the key is unchanged, a node that still trusts the old file keeps
working. That is what makes the rolling order safe.

## Verification

- Python 3.14 with the default strict context connects to the API: OK.
- Python 3.12 with `VERIFY_X509_STRICT` added, run **inside a pod** with the
  mounted `ca.crt`: OK.
- `kube-root-ca.crt` in all namespaces contains Key Usage.
- All nodes Ready, all Argo CD Applications Synced and Healthy.

A 401 from an unauthenticated Kubernetes client request is a good sign here: an
HTTP response means TLS already succeeded.

## Rollback

Restore the node's archive over `certs`, `credentials` and `args`, then restart
`microk8s.daemon-kubelite`. Do the control plane first when rolling back the
whole change. MicroK8s also has an undo for its own certificate operations, but
it does not cover files edited by hand.

## What was deliberately not done

- No new CA key, no leaf reissue, no node leave/rejoin, no workload stop. The
  documented `microk8s refresh-certs -e ca.crt` procedure does need those, and
  it was not required for a same-key reissue.
- No verification was disabled anywhere.
- `front-proxy-ca` and the client certificates without AKI were left as they
  are.

## Things to check next time

- After a runtime or library upgrade changes TLS defaults, test one strict
  client against every internal CA early.
- When reissuing a CA certificate, keep subject, serial, SKI and key. Check the
  AKI of the leaf certificates to see what they pin.
- Order matters in a trust bundle.
- Controllers that publish the CA (here `kube-root-ca.crt`) refresh slowly.
  Wait and verify.

## References

- Python `ssl` module, default context and `VERIFY_X509_STRICT`:
  https://docs.python.org/3.14/library/ssl.html
- Python discussion of the 3.13 TLS changes:
  https://discuss.python.org/t/python-3-13-x-ssl-security-changes/91266
- A Kubernetes cluster project reporting the same failure:
  https://dev.hsrn.nyu.edu/hsrn-projects/kubernetes-bare-metal/-/issues/139
- Proxmox adding Key Usage to its root CA:
  https://lore.proxmox.com/all/s8ocy12d346.fsf@toolbox/t
- MicroK8s `refresh-certs`:
  https://canonical.com/microk8s/docs/command-reference#microk8s-refresh-certs-version-119
- RFC 5280, section 4.2.1.3 (Key Usage) and 4.2.1.1 (Authority Key Identifier)
