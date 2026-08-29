# Install research-cli

Goal: `research-cli --version` works on PATH. Then run the skill playbook.

## Frozen binary (no Python)

```bash
mkdir -p "$HOME/.local/bin"
export PATH="$HOME/.local/bin:$PATH"
base="https://github.com/ErcinDedeoglu/research-cli/releases/latest/download"
os="$(uname -s)"; arch="$(uname -m)"
case "$os-$arch" in
  Darwin-arm64) asset=research-cli-Darwin-arm64 ;;
  Linux-x86_64) asset=research-cli-Linux-x86_64 ;;
  Linux-aarch64|Linux-arm64) asset=research-cli-Linux-aarch64 ;;
  *) echo "unsupported: $os $arch"; exit 1 ;;
esac
curl -fsSL -o "$HOME/.local/bin/research-cli" "$base/$asset"
chmod +x "$HOME/.local/bin/research-cli"
command -v research-cli
```

Windows: download `$base/research-cli-Windows-x86_64.exe` as `research-cli.exe` on PATH.

macOS quarantine: `xattr -d com.apple.quarantine "$HOME/.local/bin/research-cli"`.

## Already on PATH

`research-cli --self-update`. `research-cli --version` is SemVer.

## Zipapp / source

- zipapp: `$base/research-cli.pyz` then `python3 research-cli.pyz`
- checkout: `pip install -e .`

Then write keys (`research-cli help keys`) and run search from the skill.
