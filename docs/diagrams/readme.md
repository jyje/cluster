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
