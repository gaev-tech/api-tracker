export interface SystemMethodArg {
  readonly name: string;
  readonly type: string;
  readonly required: boolean;
  readonly default?: unknown;
}

export interface SystemMethodItem {
  readonly name: string;
  readonly summary: string;
  readonly args: readonly SystemMethodArg[];
  readonly returns: string;
}

export interface SystemMethodCatalog {
  readonly generator: string;
  readonly source: string;
  readonly items: readonly SystemMethodItem[];
}
