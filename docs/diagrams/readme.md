# Diagrams



## Getting Started
With activated Python with version `3.6+`, install packages with following commands:

> [!NOTE]
> We tested with Python 3.13.1 for configuration

```bash
cd docs/diagrams
pip install --upgrade pip
pip install --upgrade -r requirements.txt
```

And Launch Jupyter notebooks in this directory


## draw.io diagrams (`system-overview.drawio`, `logical-architecture.drawio`)

These two need precise manual placement (centered icon groups, tight
uniform-height rows) that Graphviz's automatic rank layout couldn't reliably
reproduce -- see the git history on `logical-architecture` for what that
looked like before (isolated clusters with large dead space, left-anchored
icons leaving a wall of empty space in single-icon rows). They're authored in
[draw.io](https://www.diagrams.net/) instead.

- **Edit them**: open the `.drawio` file in the [draw.io desktop app](https://github.com/jgraph/drawio-desktop),
  the [VS Code extension](https://marketplace.visualstudio.com/items?itemName=hediet.vscode-drawio),
  or [app.diagrams.net](https://app.diagrams.net/) (it can open/save directly
  from/to a GitHub repo, no server needed).
- **Re-export after editing**: the `.svg` next to each `.drawio` file is what
  README embeds. Regenerate it with the draw.io CLI (`brew install --cask
  drawio` on macOS):
  ```bash
  drawio -x -f svg -e --svg-theme light -o system-overview.svg system-overview.drawio
  drawio -x -f svg -e --svg-theme light -o logical-architecture.svg logical-architecture.drawio
  ```
  `-e` embeds a copy of the diagram inside the SVG, so the exported file is
  itself re-editable (drag it back into draw.io). Use `--svg-theme light`
  (not `auto`): `auto` leaves the page background transparent and picks
  theme-adaptive text colors, which renders as near-invisible low-contrast
  text on GitHub's dark theme -- these diagrams instead paint their own
  opaque light background so they look the same regardless of the
  surrounding page theme. Always re-export and commit the `.drawio` and
  `.svg` together.
- `build_overview.py` / `build_logical.py` are the scripts used to
  *bootstrap* each diagram's initial layout (base64-embed icons from
  `../assets/icons/` and the `diagrams` package's bundled icons via the
  shared `dio.py` helper, then write the `.drawio` XML). They're a one-time
  scaffold, not a build step: once you've hand-edited a `.drawio` file, don't
  re-run its script -- it will overwrite those edits.

## Troubleshooting

if you see error message like:
```bash
ExecutableNotFound: failed to execute PosixPath('dot'), make sure the Graphviz executables are on your systems' PATH
```

You may need to install graphviz with
```bash
pip install graphviz
sudo apt-get install graphviz
brew install graphviz
choco install graphviz
```
