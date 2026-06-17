export interface EventItem {
  readonly type: string;
  readonly note: string;
}

export interface EventCatalog {
  readonly generator: string;
  readonly source: string;
  readonly items: readonly EventItem[];
}
