import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import Fuse from 'fuse.js';
import { Observable, ReplaySubject, of } from 'rxjs';
import { catchError, map, shareReplay, switchMap } from 'rxjs/operators';

export interface SearchItem {
  readonly type:
    | 'page'
    | 'tutorial'
    | 'command'
    | 'rsql-field'
    | 'event'
    | 'system-method';
  readonly name: string;
  readonly description: string;
  readonly url: string;
}

interface SearchIndex {
  readonly items: readonly SearchItem[];
}

interface FuseLike {
  search(q: string): readonly { item: SearchItem }[];
}

@Injectable({ providedIn: 'root' })
export class SearchService {
  private readonly http: HttpClient = inject(HttpClient);

  private readonly fuse$: Observable<FuseLike | null> = this.http
    .get<SearchIndex>('assets/search-index.json')
    .pipe(
      catchError(() => of<SearchIndex>({ items: [] })),
      map(
        (index) =>
          new Fuse<SearchItem>([...index.items], {
            keys: [
              { name: 'name', weight: 0.7 },
              { name: 'description', weight: 0.2 },
              { name: 'type', weight: 0.1 },
            ],
            threshold: 0.4,
            ignoreLocation: true,
            minMatchCharLength: 2,
          }) as unknown as FuseLike,
      ),
      shareReplay({ bufferSize: 1, refCount: false }),
    );

  private readonly query$ = new ReplaySubject<string>(1);

  readonly results$: Observable<readonly SearchItem[]> = this.query$.pipe(
    switchMap((q: string) => {
      const trimmed = q.trim();
      if (trimmed.length < 2) return of<readonly SearchItem[]>([]);
      return this.fuse$.pipe(
        map((fuse) => {
          if (!fuse) return [] as readonly SearchItem[];
          return fuse
            .search(trimmed)
            .slice(0, 20)
            .map((r) => r.item);
        }),
      );
    }),
  );

  setQuery(q: string): void {
    this.query$.next(q);
  }
}
