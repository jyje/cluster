# Factorio server guide

Korean version: [factorio-server-guide-ko.md](factorio-server-guide-ko.md)

Operating notes for the Factorio server deployed by the `factorio` Application
(see [envoy-factorio-cutover.md](envoy-factorio-cutover.md) for the rollout). The
snippets below are sketches: validate each one with `helm template` or a dry run
before using it, and never commit a plain-text password or token to this
repository.

## How the server is set up today

- One Pod, `replicas: 1`, strategy `Recreate`, one `5Gi` save claim (`factorio-data`).
- The game listens on UDP 34197. It is exposed through the Envoy `factorio`
  Gateway on a reserved private address, and a single router forward carries
  WAN UDP 34197 to it. No RCON, no TCP.
- Settings come from a ConfigMap (`overrides.json`) that the start script merges
  over the image's `server-settings.example.json` with `jq` at every start. Only
  the keys listed in `overrides.json` change. Settings are read at start, so a
  change needs a Pod restart.
- Autosave every 5 minutes with 3 slots. The save is `/factorio/saves/world.zip`
  and the server loads the latest save on start.
- `require_user_verification` is `true`, so every player needs a valid Factorio
  account. The server is not listed publicly (`visibility.public: false`).

## Set a game password

Do not put the password in `overrides.json`: the ConfigMap is rendered from this
public repository.

1. Create a Secret with the key `game_password` as a SealedSecret, the same way
   other secrets in this repository are handled (`extraResources` entry in the
   Application, encrypted with `kubeseal`). Example shape, with the value
   encrypted locally:

   ```yaml
   apiVersion: bitnami.com/v1alpha1
   kind: SealedSecret
   metadata:
     name: factorio-secret
   spec:
     encryptedData:
       settings.json: <output of kubeseal, never the plain value>
   ```

   The secret value is a small JSON document: `{"game_password": "..."}`.

2. Mount it next to the ConfigMap with the chart's `persistence` block
   (`type: secret`, `objectName: factorio-secret`, `mountPath: /etc/factorio-secret`,
   `readOnly: true`).
3. Add the file to the merge in the start script:
   `jq -s '.[0] * .[1] * .[2]' example.json overrides.json /etc/factorio-secret/settings.json`.
4. Sync the Application and let the Pod restart. Clients are then asked for the
   password. Rotating it is a new SealedSecret plus a restart.

The password stops casual joins. Keep `require_user_verification: true`, and use
the whitelist below when you want to name exactly who may play.

## Name administrators

The example settings file has no `admins` key. The server reads a separate list
file passed with `--server-adminlist`.

1. Put the JSON array of Factorio usernames in a file on the save claim or in a
   ConfigMap, for example `["alice", "bob"]`. Usernames are not secret, but they
   are public if you keep them in this repository.
2. Add `--server-adminlist /factorio/server-adminlist.json` to the `exec` line of
   the start script and restart.
3. Admins can then promote and demote others in game with `/promote name` and
   `/demote name`. `allow_commands` is `admins-only` and
   `only_admins_can_pause_the_game` is `true` in the example settings, so
   commands and pausing are admin-only by default.
4. For a closed server, also add a whitelist: `--use-server-whitelist` with
   `--server-whitelist /factorio/server-whitelist.json` (same JSON array format).
   Only listed users can join, and admins manage it with `/whitelist`.

RCON stays off. Everything above works without it.

## Several games

A Factorio server process runs exactly one save. More games therefore means more
processes. Two practical layouts:

**One game at a time, several saves (cheapest).** Keep each game as its own save
file, or its own claim, and choose which one the Pod loads with
`--start-server <name>` instead of `--start-server-load-latest`. Switching games
is a configuration change and a restart. Use this when only one game is played
at once.

**One Deployment per game (games can run side by side).** Copy the `factorio`
Application per game: its own name, its own `existingClaim`, its own UDP port
(for example 34198), its own Gateway listener and `UDPRoute`, and its own router
forward. UDP has no hostname, so a second game cannot share the port and tell
games apart by name. The single reserved address can carry several listeners on
different ports.

### Replicas, and parking a game

Each game must run at exactly one replica. Two replicas of one game would run
two server processes against the same save and the same port, and corrupt the
save. A Deployment has no fractional replica count, so the useful values are
`0` and `1`:

- `replicas: 1`: the game is running.
- `replicas: 0`: the game is parked. The claim and save stay, the Pod and its
  memory are released.

So you can keep many game definitions in Git and run only the ones you want,
for example three Deployments with two at `replicas: 0`. When parked games share
a port with the active one, point the `UDPRoute` at the active game only and
keep the other `replicas` at `0`.

## Sizing for one game at standard load

"Standard load" here means about 4 players on a mid-size base.

Measured on this server (fresh map, one player, a few minutes after start): about
445 MiB of memory (peak about 460 MiB) and a few percent of one core. That is the
floor, not the standard load.

Rules of thumb for planning (estimates, not measurements from this cluster):

| Resource | Small base, 1 to 2 players | Standard, about 4 players | Large base |
| --- | --- | --- | --- |
| CPU | 1 fast core | 1 fast core, dedicated | 1 very fast core |
| Memory | 1 to 2 GiB | 2 to 4 GiB | 8 GiB or more |
| Save claim | 1 GiB | 2 to 5 GiB | 10 GiB or more |
| Network | under 1 Mbit/s | 1 to 2 Mbit/s plus a join spike | more |

Notes:

- The simulation is effectively single threaded, so what matters is the speed of
  one core, not the core count. A slower core shows up as game speed dropping
  below 60 updates per second for everyone.
- A joining player downloads the whole map, so size the upload for a burst of
  the save size (a few MiB early, tens of MiB later).
- Disk is rarely the limit. Saves are small. Three autosave slots plus a
  manual save fit easily in 5 GiB for a long time.

Current requests are `250m` CPU and `512Mi` memory with a `2Gi` memory limit and
no CPU limit. That is enough for the small case. For the standard case, raise
the CPU request to `1000m`, the memory request to `2Gi` and the memory limit to
`4Gi`, and prefer a Raspberry Pi 5 node over a Pi 4 node for the faster core.
The `NotIn 4b` node affinity already used for the Envoy proxies shows how to do
that. Re-measure with real players before settling on numbers.
