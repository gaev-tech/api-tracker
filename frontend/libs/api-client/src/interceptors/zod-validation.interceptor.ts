import { HttpInterceptorFn, HttpResponse } from '@angular/common/http';
import { tap } from 'rxjs';
import * as Sentry from '@sentry/angular';
import { schemaRegistry } from './schema-registry';

/**
 * HTTP interceptor that validates every API response against registered Zod schemas.
 * On validation failure: sends Sentry alert but does NOT block the response.
 */
export const ZodValidationInterceptor: HttpInterceptorFn = (req, next) => {
  return next(req).pipe(
    tap((event) => {
      if (!(event instanceof HttpResponse) || !event.body) return;

      for (const [, entry] of schemaRegistry) {
        if (req.method === entry.method && entry.pattern.test(req.url)) {
          const result = entry.schema.safeParse(event.body);
          if (!result.success) {
            Sentry.captureMessage(`API response validation failed: ${req.method} ${req.url}`, {
              level: 'warning',
              extra: {
                url: req.url,
                method: req.method,
                errors: result.error.issues,
                body: JSON.stringify(event.body).slice(0, 500),
              },
            });
          }
          break;
        }
      }
    }),
  );
};
