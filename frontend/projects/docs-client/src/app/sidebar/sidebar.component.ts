import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';

import { SearchComponent } from '../search/search.component';

interface NavLink {
  readonly path: string;
  readonly label: string;
  readonly exact?: boolean;
}

interface NavSection {
  readonly title: string;
  readonly accent: 'red' | 'blue' | 'yellow' | 'green';
  readonly links: readonly NavLink[];
}

const NAV_SECTIONS: readonly NavSection[] = [
  {
    title: 'Getting Started',
    accent: 'red',
    links: [
      { path: '/', label: 'Overview', exact: true },
      { path: '/quickstart', label: 'Quickstart' },
      { path: '/installation', label: 'Installation' },
    ],
  },
  {
    title: 'Reference',
    accent: 'blue',
    links: [
      { path: '/cli', label: 'CLI Reference' },
      { path: '/rsql', label: 'RSQL' },
      { path: '/events', label: 'Events' },
      { path: '/system-methods', label: 'System Methods' },
      { path: '/automations', label: 'Automations' },
    ],
  },
  {
    title: 'Tutorials',
    accent: 'yellow',
    links: [
      { path: '/tutorials/getting-started', label: 'Getting Started' },
      { path: '/tutorials/rsql-primer', label: 'RSQL primer' },
      { path: '/tutorials/ai-driven-workflow', label: 'AI-driven workflow' },
      { path: '/tutorials/writing-automations', label: 'Writing automations' },
    ],
  },
];

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [RouterLink, RouterLinkActive, SearchComponent],
  templateUrl: './sidebar.component.html',
  styleUrls: ['./sidebar.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SidebarComponent {
  readonly sections: readonly NavSection[] = NAV_SECTIONS;
}
