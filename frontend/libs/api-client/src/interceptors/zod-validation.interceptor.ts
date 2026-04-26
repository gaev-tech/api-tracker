import { HttpInterceptorFn, HttpResponse } from '@angular/common/http';
import { tap } from 'rxjs';
import * as Sentry from '@sentry/angular';
import { schemaRegistry } from './schema-registry';
import { ZodType } from 'zod';

function validateResponseAgainstSchema(
  body: unknown,
  schema: ZodType,
): { readonly success: boolean; readonly issues?: ReadonlyArray<{ readonly message: string }> } {
  const result = schema.safeParse(body);
  if (result.success) {
    return { success: true };
  }
  return { success: false, issues: result.error.issues };
}

function reportValidationFailure(
  requestMethod: string,
  requestUrl: string,
  issues: ReadonlyArray<{ readonly message: string }>,
  body: unknown,
): void {
  Sentry.captureMessage(`API response validation failed: ${requestMethod} ${requestUrl}`, {
    level: 'warning',
    extra: {
      url: requestUrl,
      method: requestMethod,
      errors: issues,
      body: JSON.stringify(body).slice(0, 500),
    },
  });
}

/**
 * HTTP interceptor that validates every API response against registered Zod schemas.
 * On validation failure: sends Sentry alert but does NOT block the response.
 */
export const ZodValidationInterceptor: HttpInterceptorFn = (request, next) => {
  return next(request).pipe(
    tap((event) => {
      if (!(event instanceof HttpResponse) || !event.body) {
        return;
      }
      const matchingEntry = schemaRegistry.findMatch(request.method, request.url);
      if (!matchingEntry) {
        return;
      }
      const validationResult = validateResponseAgainstSchema(event.body, matchingEntry.schema);
      if (!validationResult.success && validationResult.issues) {
        reportValidationFailure(request.method, request.url, validationResult.issues, event.body);
      }
    }),
  );
};
