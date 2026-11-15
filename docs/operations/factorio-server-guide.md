# Factorio server guide

Korean version: [factorio-server-guide-ko.md](factorio-server-guide-ko.md)

Operating notes for the Factorio server deployed by the `factorio` Application
(see [envoy-factorio-cutover.md](envoy-factorio-cutover.md) for the rollout).
Never commit a plain-text password, token or user list to this repository.

All `kubectl` commands below use the `factorio` namespace and the `factorio`
Deployment.

## How the server is set up today

- One Pod, `replicas: 1`, strategy `Recreate`, one `5Gi` save claim (`factorio-data`).
- The game listens on UDP 34197. It is exposed through the Envoy `factorio`
  Gateway on a reserved private address, and a single router forward carries
  WAN UDP 34197 to it. No RCON, no TCP.
- Settings come from a ConfigMap (`overrides.json`) and a SealedSecret
  (`factorio-secret`). The start script merges both over the image's
  `server-settings.example.json` with `jq` at every start. Settings are read at
  start, so a change needs a Pod restart.
- The server loads the most recently modified save in `/factorio/saves` on start.
  The loaded save is rewritten in place by every autosave, so there is no history
  of older autosaves. See [Checkpoints and backups](#checkpoints-and-backups).
- `require_user_verification` is `true`, so every player needs a valid Factorio
  account. The server is not listed publicly (`visibility.public: false`).
- The server runs on a Pi 5 node (`app.jyje.online/raspi.type: 5b`). See
  [node-labels.md](node-labels.md).

## Game password

A random default password is stored in the SealedSecret `factorio-secret`
(key `settings.json`, a JSON document with `game_password`). Only the encrypted
value is in Git. The Secret is mounted read-only at `/etc/factorio-secret` and
merged into the server settings at start.

Read the current default password:

```bash
kubectl -n factorio get secret factorio-secret -o jsonpath='{.data.settings\.json}' | base64 -d | jq -r .game_password
```

### Change it without a Git change

The start script also looks for the file `/factorio/game_password` on the save
volume. If it exists, its content replaces the password at the next start. Write
the new password from standard input, so it does not appear in the process list,
then restart:

```bash
printf %s 'NEW-PASSWORD' | kubectl -n factorio exec -i deploy/factorio -- sh -c 'cat > /factorio/game_password && chmod 600 /factorio/game_password'
kubectl -n factorio rollout restart deploy/factorio
```

An empty file means no password. Delete the file to go back to the Secret:

```bash
kubectl -n factorio exec deploy/factorio -- rm -f /factorio/game_password
kubectl -n factorio rollout restart deploy/factorio
```

The restart disconnects players for about a minute. The override lives on the
save volume, so it survives restarts and Pod replacements.

### Change it live, as an administrator

An admin can run `/config set password NEW-PASSWORD` in the in-game chat
(the `password` option is listed on the [Console](https://wiki.factorio.com/Console)
page). It changes the running server only. The start script rebuilds the settings
at every start, so after a restart the Secret, or the override file, applies again.
This needs an administrator, see below.

### Change the default

Create a new SealedSecret value and commit it:

```bash
printf '{"game_password": "NEW-PASSWORD"}' | kubeseal --raw --scope strict --namespace factorio --name factorio-secret --cert <controller-cert.pem>
```

Replace the `settings.json` value of the `factorio-secret` entry in
`clusters/r4spi/apps/factorio.yaml`, merge, then sync the `factorio` Application
(sync `apps` first so the Application resource has the new value).

## Administrators

The example settings file has no `admins` key. The server reads a separate list
file passed with `--server-adminlist`. It is set up here: the key
`server-adminlist.json` of the SealedSecret `factorio-secret` holds the JSON array
of administrator accounts, and the start script passes
`/etc/factorio-secret/server-adminlist.json`. Treat the list, and the optional
whitelist below, as secrets: they name real accounts, and this repository is
public, so only the encrypted value is in Git.

Change the administrators:

1. Seal a new JSON array, for example `["alice", "bob"]`, with the same
   `--scope strict --namespace factorio --name factorio-secret` options as the
   password (see [Change the default](#change-the-default)), but with the file name
   `server-adminlist.json`.
2. Replace the `server-adminlist.json` value of the `factorio-secret` entry in
   `clusters/r4spi/apps/factorio.yaml`, merge, sync `apps`, then sync `factorio`.
   The files are read-only, which is fine: the server only reads them at start.
3. Admins can promote and demote others in game with `/promote name` and
   `/demote name`. Those commands edit the server's own list, which is read-only
   here, so a promotion made in game does not survive a restart. Make permanent
   changes in the SealedSecret and restart.
4. `allow_commands` is `admins-only` and `only_admins_can_pause_the_game` is
   `true` in the example settings, so commands and pausing are admin-only by
   default.
5. For a closed server, also add a `server-whitelist.json` key the same way and
   pass `--use-server-whitelist --server-whitelist /etc/factorio-secret/server-whitelist.json`.
   Only listed users can join.

The generated settings file `/factorio/server-settings.json` contains the game
password, so the start script recreates it on every start with owner-only
permissions (mode 600).

## Console commands: pause, resume and saves

RCON is off, so commands run from the in-game chat by an administrator. The full
list is on the [Console](https://wiki.factorio.com/Console) page.

| Goal | Command | Notes |
| --- | --- | --- |
| Save now | `/server-save` | Admin only. Saves the game on the server. |
| Pause | `/c game.tick_paused = true` | Lua API property `tick_paused`. |
| Resume | `/c game.tick_paused = false` | |
| Change the password | `/config set password NEW-PASSWORD` | Running server only. |
| Other settings | `/config get` and `/config set` | Options include `max-players`, `autosave-interval`, `only-admins-can-pause`, `visibility-public`. |
| Admins | `/promote name`, `/demote name` | Not kept across restarts here. |
| Kick or ban | `/kick name`, `/ban name` | |

Notes:

- `/c` runs Lua. The Console page says that using it turns achievements off for
  that save.
- `auto_pause` is already on, so the game pauses by itself when nobody is
  connected.
- `only_admins_can_pause_the_game` is on, so players cannot pause on their own.
- To run commands from a terminal instead, the server would need RCON
  (`--rcon-port` and `--rcon-password`, see
  [Command line parameters](https://wiki.factorio.com/Command_line_parameters)).
  RCON is not enabled here. It needs a password in a Secret and a decision about
  who can reach the port, so enable it deliberately.

## Checkpoints and backups

The server rewrites the loaded save, `world.zip`, at every autosave. It does not
keep numbered autosave files. A checkpoint therefore has to be a copy you make.

Keep copies outside `/factorio/saves`. The server loads the most recently
modified file there, so an extra copy in that folder can be loaded by mistake.

Make a backup:

```bash
kubectl -n factorio exec deploy/factorio -- sh -c 'mkdir -p /factorio/backups && cp -p /factorio/saves/world.zip "/factorio/backups/world-$(date +%Y%m%d-%H%M).zip"'
```

For a consistent copy, run `/server-save` as an admin first. List and download:

```bash
kubectl -n factorio exec deploy/factorio -- ls -l /factorio/backups
kubectl -n factorio exec deploy/factorio -- cat /factorio/backups/NAME.zip > NAME.zip
```

Restore a backup:

```bash
kubectl -n factorio exec deploy/factorio -- sh -c 'mkdir -p /factorio/backups && mv /factorio/saves/world.zip /factorio/backups/world-before-restore.zip && cp /factorio/backups/NAME.zip /factorio/saves/world.zip'
kubectl -n factorio rollout restart deploy/factorio
```

The backups sit on the same volume as the live save, so they do not protect
against losing the volume. Download the ones that matter.

## Move a game from the Mac to the server

Official location of saves on macOS (see
[Application directory](https://wiki.factorio.com/Application_directory)):
`~/Library/Application Support/factorio/saves/`. Pick the newest `.zip`, or an
`_autosave` file.

Before you start, check that:

- The Mac game and the server are the same version, or the server is newer
  (both are 2.1.24 today). The server can load an older save.
- The mods match. The server has `base`, `elevated-rails`, `quality`, `recycler`
  and `space-age` enabled, which is the same set as an unmodded Space Age game.
  A save that uses other mods needs those mods in `/factorio/mods` and in its
  `mod-list.json` first.

Steps:

1. Quit the game on the Mac so the file is complete.
2. Back up the server save (see above) and move it out of the saves folder:

   ```bash
   kubectl -n factorio exec deploy/factorio -- sh -c 'mkdir -p /factorio/backups && mv /factorio/saves/world.zip "/factorio/backups/world-$(date +%Y%m%d-%H%M).zip"'
   ```

3. Copy the Mac save to the server:

   ```bash
   kubectl -n factorio exec -i deploy/factorio -- sh -c 'cat > /factorio/saves/world.zip' < "$HOME/Library/Application Support/factorio/saves/NAME.zip"
   ```

   Naming it `world.zip` keeps one save in the folder and keeps autosaves going to
   the same file.
4. Restart the server and check that it loaded the file:

   ```bash
   kubectl -n factorio rollout restart deploy/factorio
   kubectl -n factorio logs deploy/factorio | grep "Loading map"
   ```

5. Join with the same Factorio username you used on the Mac. A single-player
   character usually carries over by username. The first join can take a while
   because the client downloads the whole map.

## Official documentation

- [Console](https://wiki.factorio.com/Console): commands such as `/server-save`, `/config`, `/promote`, `/c`.
- [Command line parameters](https://wiki.factorio.com/Command_line_parameters): `--start-server`, `--server-adminlist`, `--rcon-port` and the rest.
- [Multiplayer](https://wiki.factorio.com/Multiplayer): dedicated servers, settings and admin lists.
- [Application directory](https://wiki.factorio.com/Application_directory): where saves and mods live on each system.
- [LuaGameScript](https://lua-api.factorio.com/latest/classes/LuaGameScript.html): the `tick_paused` property.

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

The server is sized for the standard case: `1000m` CPU and `2Gi` memory requests,
a `4Gi` memory limit (the chart's default CPU limit of `1500m` applies), and a
node selector on the Pi 5 label `app.jyje.online/raspi.type: 5b`, because the
Pi 4 node has the slower core. This chart does not implement `nodeAffinity`, so
use a node selector. For a small game the old values (`250m`, `512Mi`, `2Gi`
limit) were enough. Re-measure with real players before settling on numbers.
