import { ZodType } from 'zod';

interface SchemaRegistryEntry {
  readonly method: string;
  readonly pattern: RegExp;
  readonly schema: ZodType;
}

class SchemaRegistryImpl {
  private readonly entries = new Map<string, SchemaRegistryEntry>();

  register(method: string, pattern: RegExp, schema: ZodType): void {
    const key = `${method}:${pattern.source}`;
    this.entries.set(key, { method, pattern, schema });
  }

  findMatch(requestMethod: string, requestUrl: string): SchemaRegistryEntry | undefined {
    for (const [, entry] of this.entries) {
      if (requestMethod === entry.method && entry.pattern.test(requestUrl)) {
        return entry;
      }
    }
    return undefined;
  }
}

export const schemaRegistry = new SchemaRegistryImpl();
