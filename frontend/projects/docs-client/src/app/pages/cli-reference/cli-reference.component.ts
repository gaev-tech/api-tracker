import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  Signal,
  computed,
  inject,
} from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { Observable, map, of } from 'rxjs';
import { catchError } from 'rxjs/operators';

import { CliCommand, CliReference } from './cli-reference.types';

@Component({
  selector: 'app-cli-reference',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './cli-reference.component.html',
  styleUrls: ['./cli-reference.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CliReferenceComponent {
  private readonly http: HttpClient = inject(HttpClient);
  private readonly route: ActivatedRoute = inject(ActivatedRoute);

  private readonly reference$: Observable<CliReference | null> = this.http
    .get<CliReference>('assets/cli-reference.json')
    .pipe(catchError(() => of(null)));

  protected readonly reference: Signal<CliReference | null> = toSignal(
    this.reference$,
    { initialValue: null },
  );
  protected readonly commandParam: Signal<string | null> = toSignal(
    this.route.paramMap.pipe(map((p) => p.get('command'))),
    { initialValue: null },
  );

  protected readonly allCommands: Signal<readonly CliCommand[]> = computed(
    () => this.reference()?.commands ?? [],
  );

  protected readonly leafCommands: Signal<readonly CliCommand[]> = computed(
    () => this.allCommands().filter((c: CliCommand) => !c.is_group),
  );

  protected readonly selectedCommand: Signal<CliCommand | null> = computed(
    () => {
      const slug = this.commandParam();
      if (!slug) return null;
      const wantedPath = slug.replace(/-/g, ' ').toLowerCase();
      const match = this.allCommands().find(
        (c: CliCommand) => c.path.toLowerCase() === wantedPath,
      );
      return match ?? null;
    },
  );

  protected readonly subCommandsOfSelected: Signal<readonly CliCommand[]> =
    computed(() => {
      const sel = this.selectedCommand();
      if (!sel?.is_group) return [];
      const depth = sel.path.split(' ').length + 1;
      return this.allCommands().filter(
        (c: CliCommand) =>
          c.path.startsWith(sel.path + ' ') &&
          c.path.split(' ').length === depth,
      );
    });

  protected slugFor(path: string): string {
    return path.replace(/ /g, '-');
  }

  protected formatDefault(value: unknown): string {
    if (value === null || value === undefined) return '—';
    if (typeof value === 'string') return value === '' ? '""' : value;
    return JSON.stringify(value);
  }
}
