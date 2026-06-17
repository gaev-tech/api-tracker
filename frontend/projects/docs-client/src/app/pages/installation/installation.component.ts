import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';

type ChannelStatus = 'available' | 'pending-first-release';

interface Channel {
  readonly name: string;
  readonly status: ChannelStatus;
  readonly platforms: string;
  readonly install: string;
  readonly verify?: string;
  readonly note?: string;
}

const CHANNELS: readonly Channel[] = [
  {
    name: 'GitHub Releases (binary)',
    status: 'available',
    platforms: 'Linux x86_64, macOS arm64 / x64, Windows x64',
    install: `# Pick the asset for your OS+arch from the latest release:
#   https://github.com/gaev-tech/clite/releases/latest
# Example for macOS arm64:
curl -fsSL \\
  -o /usr/local/bin/clite \\
  https://github.com/gaev-tech/clite/releases/latest/download/clite-darwin-arm64
chmod +x /usr/local/bin/clite`,
    verify: `clite --version`,
    note: 'Canonical source. All other channels repackage or fetch these binaries.',
  },
  {
    name: 'pipx',
    status: 'pending-first-release',
    platforms: 'Any with Python 3.13+',
    install: `pipx install clite`,
    verify: `clite --version`,
    note: 'Isolates the install in its own venv. Recommended for developer machines once `clite` is published to PyPI (IPLAN §6.3.2).',
  },
  {
    name: 'PyPI (pip)',
    status: 'pending-first-release',
    platforms: 'Any with Python 3.13+',
    install: `pip install clite`,
    verify: `clite --version`,
    note: 'Same package as pipx — use this if you prefer plain pip into a managed venv.',
  },
  {
    name: 'Homebrew',
    status: 'pending-first-release',
    platforms: 'macOS arm64 / x64',
    install: `brew install gaev-tech/clite/clite`,
    verify: `clite --version`,
    note: 'Tap repo: github.com/gaev-tech/homebrew-clite. Formula is rendered + pushed automatically by the release pipeline (IPLAN §6.3.3).',
  },
  {
    name: 'APT (Debian / Ubuntu)',
    status: 'pending-first-release',
    platforms: 'Debian / Ubuntu amd64',
    install: `curl -fsSL https://apt.apitracker.ru/key.gpg \\
  | sudo gpg --dearmor -o /usr/share/keyrings/apit.gpg
echo "deb [signed-by=/usr/share/keyrings/apit.gpg] https://apt.apitracker.ru stable main" \\
  | sudo tee /etc/apt/sources.list.d/apit.list
sudo apt update
sudo apt install clite`,
    verify: `clite --version`,
    note: 'Self-hosted, GPG-signed APT repo on apt.apitracker.ru (IPLAN §6.3.4).',
  },
  {
    name: 'npm wrapper',
    status: 'pending-first-release',
    platforms: 'macOS, Linux, Windows — any with Node 18+',
    install: `npm install -g @gaev-tech/clite --registry https://registry.npmjs.org/`,
    verify: `npx --registry https://registry.npmjs.org/ @gaev-tech/clite --version`,
    note: 'Binary wrapper: postinstall downloads the matching binary from GitHub Releases and verifies SHA256 (IPLAN §6.3.5).',
  },
];

@Component({
  selector: 'app-installation',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './installation.component.html',
  styleUrls: ['./installation.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class InstallationComponent {
  protected readonly channels: readonly Channel[] = CHANNELS;
}
