import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  Signal,
  computed,
  inject,
} from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { SafeHtml } from '@angular/platform-browser';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { Observable, of } from 'rxjs';
import { catchError, map, switchMap } from 'rxjs/operators';

import { MarkdownService } from '../../services/markdown.service';

interface TutorialMeta {
  readonly slug: string;
  readonly title: string;
}

const TUTORIALS: readonly TutorialMeta[] = [
  { slug: 'getting-started', title: 'Getting Started' },
  { slug: 'rsql-primer', title: 'RSQL primer' },
  { slug: 'ai-driven-workflow', title: 'AI-driven workflow' },
  { slug: 'writing-automations', title: 'Writing automations' },
];

@Component({
  selector: 'app-tutorial',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './tutorial.component.html',
  styleUrls: ['./tutorial.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TutorialComponent {
  private readonly route: ActivatedRoute = inject(ActivatedRoute);
  private readonly md: MarkdownService = inject(MarkdownService);

  protected readonly slug: Signal<string | null> = toSignal(
    this.route.paramMap.pipe(map((p) => p.get('slug'))),
    { initialValue: null },
  );

  private readonly content$: Observable<SafeHtml | null> =
    this.route.paramMap.pipe(
      switchMap((p) => {
        const slug = p.get('slug');
        if (!slug) return of<SafeHtml | null>(null);
        return this.md
          .loadTutorial(slug)
          .pipe(catchError(() => of<SafeHtml | null>(null)));
      }),
    );

  protected readonly content: Signal<SafeHtml | null> = toSignal(
    this.content$,
    { initialValue: null },
  );

  protected readonly tutorials: readonly TutorialMeta[] = TUTORIALS;

  protected readonly currentMeta: Signal<TutorialMeta | null> = computed(() => {
    const s = this.slug();
    return TUTORIALS.find((t) => t.slug === s) ?? null;
  });
}
