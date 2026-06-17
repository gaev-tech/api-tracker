export interface RsqlOperator {
  readonly op: string;
  readonly kind: string;
  readonly applies: string;
  readonly note: string;
}

export interface RsqlField {
  readonly name: string;
  readonly type: string;
  readonly note: string;
}

export interface RsqlExample {
  readonly expr: string;
  readonly note: string;
}

export interface RsqlReference {
  readonly generator: string;
  readonly source: string;
  readonly fallback: boolean;
  readonly operators: readonly RsqlOperator[];
  readonly fields_by_entity: Readonly<Record<string, readonly RsqlField[]>>;
  readonly examples: readonly RsqlExample[];
}
