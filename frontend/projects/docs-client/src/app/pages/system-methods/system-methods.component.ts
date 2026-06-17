import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, Signal, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { Observable, of } from 'rxjs';
import { catchError } from 'rxjs/operators';

import { SystemMethodCatalog } from './system-methods.types';

@Component({
  selector: 'app-system-methods',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './system-methods.component.html',
  styleUrls: ['./system-methods.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SystemMethodsComponent {
  private readonly http: HttpClient = inject(HttpClient);

  private readonly catalog$: Observable<SystemMethodCatalog | null> = this.http
    .get<SystemMethodCatalog>('assets/system-methods.json')
    .pipe(catchError(() => of(null)));

  protected readonly catalog: Signal<SystemMethodCatalog | null> = toSignal(
    this.catalog$,
    { initialValue: null },
  );
}
