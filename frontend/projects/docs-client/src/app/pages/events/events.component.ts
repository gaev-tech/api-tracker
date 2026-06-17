import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, Signal, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { Observable, of } from 'rxjs';
import { catchError } from 'rxjs/operators';

import { EventCatalog } from './events.types';

@Component({
  selector: 'app-events',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './events.component.html',
  styleUrls: ['./events.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class EventsComponent {
  private readonly http: HttpClient = inject(HttpClient);

  private readonly catalog$: Observable<EventCatalog | null> = this.http
    .get<EventCatalog>('assets/event-catalog.json')
    .pipe(catchError(() => of(null)));

  protected readonly catalog: Signal<EventCatalog | null> = toSignal(
    this.catalog$,
    { initialValue: null },
  );
}
