import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';

type ChannelStatus = 'available' | 'coming-soon';

interface Channel {
  readonly name: string;
  readonly status: ChannelStatus;
  readonly platforms: string;
  readonly install: string;
  readonly verify?: string;
  readonly note?: string;
  readonly issueUrl?: string;
}

const CHANNELS: readonly Channel[] = [
  {
    name: 'GitHub Releases (binary)',
    status: 'available',
    platforms: 'Linux x86_64 / arm64, macOS arm64',
    install: `curl -fsSL https://github.com/gaev-tech/api-tracker/releases/latest/download/clite-$(uname -s)-$(uname -m).tar.gz \\
  | tar -xz -C /usr/local/bin
chmod +x /usr/local/bin/clite`,
    verify: `clite version`,
    note: 'Static binary, no Python required at runtime.',
  },
  {
    name: 'pipx',
    status: 'available',
    platforms: 'Any with Python 3.10+',
    install: `pipx install clite`,
    verify: `clite version`,
    note: 'Isolates the install in its own venv. Best default for developer machines.',
  },
  {
    name: 'PyPI (pip)',
    status: 'coming-soon',
    platforms: 'Any with Python 3.10+',
    install: `pip install clite   # not yet published`,
    note: 'Lands in M4.B once the package is registered on pypi.org. IPLAN §6.3.2.',
    issueUrl: 'https://github.com/gaev-tech/api-tracker/issues',
  },
  {
    name: 'Homebrew',
    status: 'coming-soon',
    platforms: 'macOS, Linux',
    install: `brew install gaev-tech/clite/clite   # not yet published`,
    note: 'Lands in M4.B via tap repo gaev-tech/homebrew-clite. IPLAN §6.3.3.',
    issueUrl: 'https://github.com/gaev-tech/api-tracker/issues',
  },
  {
    name: 'APT',
    status: 'coming-soon',
    platforms: 'Debian, Ubuntu',
    install: `# placeholder — see /installation in M4.B
sudo curl -fsSL apt.apitracker.ru/key.gpg | gpg --dearmor -o /usr/share/keyrings/clite.gpg
echo "deb [signed-by=/usr/share/keyrings/clite.gpg] https://apt.apitracker.ru stable main" | sudo tee /etc/apt/sources.list.d/clite.list
sudo apt-get update && sudo apt-get install clite`,
    note: 'Lands in M4.B via a self-hosted APT repo at apt.apitracker.ru. IPLAN §6.3.4.',
    issueUrl: 'https://github.com/gaev-tech/api-tracker/issues',
  },
  {
    name: 'npm wrapper',
    status: 'coming-soon',
    platforms: 'Any with Node 18+',
    install: `npm install -g @gaev-tech/clite --registry https://registry.npmjs.org/   # not yet published`,
    verify: `npx --registry https://registry.npmjs.org/ @gaev-tech/clite --version`,
    note: 'Lands in M4.B; postinstall script downloads the matching binary from GitHub Releases. IPLAN §6.3.5.',
    issueUrl: 'https://github.com/gaev-tech/api-tracker/issues',
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
