import { Routes } from '@angular/router';

import { LayoutComponent } from './layout/layout.component';

export const APP_ROUTES: Routes = [
  {
    path: '',
    component: LayoutComponent,
    children: [
      {
        path: '',
        loadComponent: () =>
          import('./pages/index/index.component').then((m) => m.IndexComponent),
      },
      {
        path: 'quickstart',
        loadComponent: () =>
          import('./pages/quickstart/quickstart.component').then(
            (m) => m.QuickstartComponent,
          ),
      },
      {
        path: 'installation',
        loadComponent: () =>
          import('./pages/installation/installation.component').then(
            (m) => m.InstallationComponent,
          ),
      },
      {
        path: 'cli',
        loadComponent: () =>
          import('./pages/cli-reference/cli-reference.component').then(
            (m) => m.CliReferenceComponent,
          ),
      },
      {
        path: 'cli/:command',
        loadComponent: () =>
          import('./pages/cli-reference/cli-reference.component').then(
            (m) => m.CliReferenceComponent,
          ),
      },
      {
        path: 'rsql',
        loadComponent: () =>
          import('./pages/rsql/rsql.component').then((m) => m.RsqlComponent),
      },
      {
        path: 'events',
        loadComponent: () =>
          import('./pages/events/events.component').then(
            (m) => m.EventsComponent,
          ),
      },
      {
        path: 'system-methods',
        loadComponent: () =>
          import('./pages/system-methods/system-methods.component').then(
            (m) => m.SystemMethodsComponent,
          ),
      },
      {
        path: 'automations',
        loadComponent: () =>
          import('./pages/automations/automations.component').then(
            (m) => m.AutomationsComponent,
          ),
      },
      {
        path: 'tutorials/:slug',
        loadComponent: () =>
          import('./pages/tutorial/tutorial.component').then(
            (m) => m.TutorialComponent,
          ),
      },
      {
        path: '**',
        redirectTo: '',
      },
    ],
  },
];
