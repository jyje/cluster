# Henry Gateway API pilot

Tracks [#207](https://github.com/jyje/cluster/issues/207). The pilot uses
Traefik chart 42.3.1 (Proxy v3.7.17) and the existing standard Gateway API
v1.6.3 CRDs. The chart is vendored unchanged and uses its native
`extraObjects` value for the HTTPRoute.

The pilot does not change Henry, its existing Ingress, DNS, TLS, or OIDC
configuration. It matches only GET requests to the exact root path on a
test-only hostname. Do not follow the login redirect or send credentials
through this HTTP listener.

## Verify after a manual sync

1. Confirm the `gateway-api` Application is synced and Henry has ready Service
   endpoints. Manually sync only the `traefik-henry-pilot` Application.
2. Confirm the pilot GatewayClass is accepted, the Gateway is programmed, and
   the HTTPRoute reports `Accepted=True` and `ResolvedRefs=True` for the pilot
   listener. Do not proceed if any condition is missing or false.
3. Forward the pilot Service to loopback:

   ```sh
   kubectl --context microk8s -n traefik-henry-pilot \
     port-forward --address localhost svc/traefik-henry-pilot 18080:80
   ```

4. In another terminal, verify the root redirects to sign-in without a session,
   the API path returns 404, and the wrong host returns 404:

   ```sh
   curl -sS -D - -o /dev/null -H 'Host: henry-pilot.invalid' http://localhost:18080/
   curl -sS -o /dev/null -w '%{http_code}\n' -H 'Host: henry-pilot.invalid' http://localhost:18080/api/auth/me
   curl -sS -o /dev/null -w '%{http_code}\n' -H 'Host: unmatched.invalid' http://localhost:18080/
   ```

The pilot verifies routing and the unauthenticated response only. A later
cutover must verify HTTPS, OIDC callbacks, secure cookies, unauthorized access,
streaming, uploads, certificate renewal, and traffic rollback.

## Rollback

If the pilot was synced, remove its Application definition from Git, reconcile
the parent, then delete the pilot Application with cascading resource deletion
if the parent did not prune it. Check that the pilot HTTPRoute, Gateway,
GatewayClass, Deployment, and Service are gone. Leave the shared CRDs and
Henry's production resources in place.
