/** Types mirroring the JSON produced by `generate-cli-reference.py`. */

export interface CliOption {
  readonly names: readonly string[];
  readonly secondary_names: readonly string[];
  readonly type: string;
  readonly required: boolean;
  readonly default: unknown;
  readonly help: string;
  readonly multiple: boolean;
  readonly is_flag: boolean;
}

export interface CliArgument {
  readonly name: string;
  readonly type: string;
  readonly required: boolean;
  readonly nargs: number;
}

export interface CliExample {
  readonly cmd: string;
  readonly note: string;
}

export interface CliCommand {
  readonly path: string;
  readonly name: string;
  readonly summary: string;
  readonly description: string;
  readonly is_group: boolean;
  readonly options: readonly CliOption[];
  readonly arguments: readonly CliArgument[];
  readonly examples: readonly CliExample[];
}

export interface CliReference {
  readonly generator: string;
  readonly source: string;
  readonly commands: readonly CliCommand[];
}
