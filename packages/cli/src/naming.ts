/**
 * The five substitution tokens (docs/plans/phase-19.md 19.A "Templates")
 * derived from one PascalCase singular resource name.
 *
 * There are exactly five and there will not be a sixth: every other shape
 * a template needs (a permission code, a related_name, a URL segment) is
 * one of these five with a fixed suffix, and adding tokens for those is
 * how a token substituter turns into a template language.
 */

export interface Names {
  /** __Resource__ — PascalCase singular. `Invoice` */
  Resource: string;
  /** __resource__ — snake_case singular. `invoice` */
  resource: string;
  /** __resources__ — snake_case plural. `invoices` */
  resources: string;
  /** __Resources__ — PascalCase plural. `Invoices` */
  Resources: string;
  /** __app__ — the Django app label. `invoices` */
  app: string;
}

export class InvalidResourceName extends Error {}

/**
 * Plural rules kept to the three that cover ordinary English nouns, the
 * same scope `scripts/init.ts::pluralize` settled on. A resource whose
 * plural this gets wrong is a resource whose name should be reconsidered
 * before it becomes a URL segment and a database table.
 */
export function pluralize(word: string): string {
  if (/[^aeiou]y$/i.test(word)) return word.slice(0, -1) + "ies";
  if (/(s|x|z|ch|sh)$/i.test(word)) return word + "es";
  return word + "s";
}

/** `InvoiceLine` -> `invoice_line`. */
export function pascalToSnake(name: string): string {
  return name
    .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
    .replace(/([A-Z]+)([A-Z][a-z])/g, "$1_$2")
    .toLowerCase();
}

/** `invoice_line` -> `InvoiceLine`. */
export function snakeToPascal(name: string): string {
  return name
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join("");
}

export function namesFor(rawName: string): Names {
  const name = rawName.trim();
  if (!/^[A-Z][A-Za-z0-9]*$/.test(name)) {
    throw new InvalidResourceName(
      `Resource name must be PascalCase singular and alphanumeric (got "${rawName}"). ` +
        `It becomes a Python class name, a Django app label, and a URL segment.`,
    );
  }
  const snake = pascalToSnake(name);
  const snakePlural = pluralize(snake);
  return {
    Resource: name,
    resource: snake,
    resources: snakePlural,
    Resources: snakeToPascal(snakePlural),
    app: snakePlural,
  };
}
