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
import { Observable, of } from 'rxjs';
import { catchError } from 'rxjs/operators';

import { RsqlReference } from './rsql.types';

@Component({
  selector: 'app-rsql',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './rsql.component.html',
  styleUrls: ['./rsql.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RsqlComponent {
  private readonly http: HttpClient = inject(HttpClient);

  private readonly reference$: Observable<RsqlReference | null> = this.http
    .get<RsqlReference>('assets/rsql-reference.json')
    .pipe(catchError(() => of(null)));

  protected readonly reference: Signal<RsqlReference | null> = toSignal(
    this.reference$,
    { initialValue: null },
  );

  protected readonly entities: Signal<readonly string[]> = computed(() =>
    Object.keys(this.reference()?.fields_by_entity ?? {}),
  );

  protected fieldsFor(entity: string): readonly { name: string; type: string; note: string }[] {
    return this.reference()?.fields_by_entity[entity] ?? [];
  }
}
