# @gaev-tech/clite

`clite` — AI-driven task tracker CLI for [apitracker.ru](https://apitracker.ru), packaged as an npm binary wrapper.

The package itself is tiny: on `npm install` a `postinstall` script downloads the platform-matching binary from the official [GitHub Releases](https://github.com/gaev-tech/clite/releases) and verifies its SHA256 before placing it on your `PATH`.

## Install

```bash
npm install -g @gaev-tech/clite --registry https://registry.npmjs.org/
clite --version
```

Or one-shot:

```bash
npx --registry https://registry.npmjs.org/ @gaev-tech/clite --version
```

## Supported platforms

- macOS arm64, macOS x64
- Linux x64
- Windows x64

Other Node-supported platforms are not (yet) covered — see the canonical [installation page](https://apitracker.ru/installation) for alternative channels.

## Alternative channels

If the wrapper is the wrong shape for you, install via:

- PyPI: `pipx install clite`
- Homebrew: `brew install gaev-tech/clite/clite`
- APT: see <https://apitracker.ru/installation>
- GitHub Releases: <https://github.com/gaev-tech/clite/releases/latest>

## License

MIT.
