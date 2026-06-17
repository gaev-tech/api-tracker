# clite

`clite` — command-line task engine for [apitracker.ru](https://apitracker.ru).

AI-driven task tracker with RSQL filtering, team / project access model, and a thin REST API surface that the CLI talks to directly.

## Install

Pick the channel that fits your environment.

### PyPI (recommended for Python users)

```bash
pipx install clite          # isolated, preferred
# or
pip install clite           # into current venv / system Python
```

Requires Python 3.13+.

### Homebrew (macOS / Linux)

```bash
brew install gaev-tech/clite/clite
```

### APT (Debian / Ubuntu)

```bash
curl -fsSL https://apt.apitracker.ru/key.gpg \
  | sudo gpg --dearmor -o /usr/share/keyrings/apit.gpg
echo "deb [signed-by=/usr/share/keyrings/apit.gpg] https://apt.apitracker.ru stable main" \
  | sudo tee /etc/apt/sources.list.d/apit.list
sudo apt update
sudo apt install clite
```

### npm (binary wrapper, any OS with Node 18+)

```bash
npm install -g @gaev-tech/clite --registry https://registry.npmjs.org/
# or one-shot
npx --registry https://registry.npmjs.org/ @gaev-tech/clite --version
```

### GitHub Releases (raw binaries)

See <https://github.com/gaev-tech/clite/releases/latest> for prebuilt binaries (`darwin-arm64`, `darwin-amd64`, `linux-amd64`, `windows-amd64.exe`) plus SHA256 checksums.

## Quickstart

```bash
clite auth login            # interactive auth via apitracker.ru
clite create task "buy milk"
clite get tasks
```

Full docs: <https://apitracker.ru/installation>, <https://apitracker.ru/quickstart>.

## License

MIT.
