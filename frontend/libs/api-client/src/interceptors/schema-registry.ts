import { ZodType } from 'zod';

export const schemaRegistry = new Map<
  string,
  { method: string; pattern: RegExp; schema: ZodType }
>();

/**
 * Register a Zod schema for response validation.
 * @param method HTTP method (GET, POST, etc.)
 * @param pattern URL pattern (regex)
 * @param schema Zod schema to validate against
 */
export function registerResponseSchema(method: string, pattern: RegExp, schema: ZodType): void {
  const key = `${method}:${pattern.source}`;
  schemaRegistry.set(key, { method, pattern, schema });
}
