import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { Marked } from 'marked';
import { Observable, from, map } from 'rxjs';

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/**
 * Renders markdown into safe HTML for tutorial pages.
 *
 * Tutorials live in `src/assets/tutorials/<slug>.md` and are loaded over HTTP
 * at runtime. Code blocks are wrapped with CSS hooks so the global stylesheet
 * can style them with JetBrains Mono — no external highlighter dependency.
 */
@Injectable({ providedIn: 'root' })
export class MarkdownService {
  private readonly http: HttpClient = inject(HttpClient);
  private readonly sanitizer: DomSanitizer = inject(DomSanitizer);
  private readonly marked: Marked;

  constructor() {
    this.marked = new Marked({
      gfm: true,
      breaks: false,
      async: false,
      renderer: {
        code(token: { text: string; lang?: string }): string {
          const safeText = escapeHtml(token.text);
          const langAttr = token.lang
            ? ` data-lang="${escapeHtml(token.lang)}"`
            : '';
          return `<pre class="md__code"${langAttr}><code>${safeText}</code></pre>`;
        },
        codespan(token: { text: string }): string {
          return `<code class="md__inline-code">${escapeHtml(token.text)}</code>`;
        },
      },
    });
  }

  /**
   * Loads a markdown file from `assets/tutorials/<slug>.md` and returns
   * the rendered HTML as a `SafeHtml`.
   */
  loadTutorial(slug: string): Observable<SafeHtml> {
    const url = `assets/tutorials/${slug}.md`;
    return this.http.get(url, { responseType: 'text' }).pipe(
      map((md: string) => this.marked.parse(md, { async: false }) as string),
      map((html: string) => this.sanitizer.bypassSecurityTrustHtml(html)),
    );
  }

  /**
   * Renders a markdown string into safe HTML synchronously (Promise-wrapped
   * to keep an observable-shaped API everywhere the service is consumed).
   */
  renderInline(markdown: string): Observable<SafeHtml> {
    const html = this.marked.parse(markdown, { async: false }) as string;
    return from(Promise.resolve(this.sanitizer.bypassSecurityTrustHtml(html)));
  }
}
