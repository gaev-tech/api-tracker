import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  Signal,
  inject,
  signal,
} from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import { SearchItem, SearchService } from '../services/search.service';

@Component({
  selector: 'app-search',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './search.component.html',
  styleUrls: ['./search.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SearchComponent {
  private readonly search: SearchService = inject(SearchService);
  private readonly router: Router = inject(Router);

  protected readonly queryControl = new FormControl<string>('', { nonNullable: true });
  protected readonly results: Signal<readonly SearchItem[]>;
  protected readonly open = signal(false);

  constructor() {
    this.queryControl.valueChanges.subscribe((value) => {
      this.search.setQuery(value);
      this.open.set(value.trim().length >= 2);
    });
    this.results = toSignal(this.search.results$, { initialValue: [] });
  }

  protected pick(item: SearchItem): void {
    this.open.set(false);
    this.queryControl.setValue('', { emitEvent: false });
    this.router.navigateByUrl(item.url);
  }

  protected onFocus(): void {
    if (this.queryControl.value.trim().length >= 2) this.open.set(true);
  }

  protected onBlur(): void {
    // delay so a click on a result still registers
    setTimeout(() => this.open.set(false), 120);
  }

  protected typeLabel(t: SearchItem['type']): string {
    switch (t) {
      case 'command':
        return 'CLI';
      case 'rsql-field':
        return 'RSQL';
      case 'system-method':
        return 'METHOD';
      case 'event':
        return 'EVENT';
      case 'tutorial':
        return 'GUIDE';
      case 'page':
        return 'PAGE';
    }
  }
}
