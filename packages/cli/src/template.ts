/**
 * The template engine, in full (docs/plans/phase-19.md 19.A "Templates";
 * ADR 0004).
 *
 * Templates are real `.py` files, so ruff and mypy lint the templates
 * themselves — a `.hbs` file is unlintable text. That constraint is what
 * fixes this engine's feature set:
 *
 *   __Token__               five substitutions, see naming.ts
 *   # keel:if <flag>        keep the region only when <flag> is on
 *   # keel:endif
 *   # keel:insert <slot>    replace this line with generator-rendered lines
 *
 * There are no loops and no expressions, and adding either is the signal
 * that the template is doing work that belongs in the generator or in the
 * judgement half the slash command drives. A marker line never survives
 * into output; the text between `keel:if` and `keel:endif` is emitted
 * verbatim (minus one level of nothing — the region is not re-indented,
 * because a region that needs re-indenting is a region in the wrong place).
 *
 * `# keel:if` must be a whole line so that the template file stays valid
 * Python with every region present, which is exactly what makes the
 * "linters lint the templates" claim true.
 *
 * One flag is reserved and is deliberately never set by any generator:
 * `template_only` marks content that exists so the template file parses
 * and is dropped from every render. It is needed exactly where a class
 * body would otherwise be nothing but a `# keel:insert` marker — a
 * comment is not a statement, so the template would be a syntax error,
 * and a docstring is not an option because pydantic promotes a schema
 * class's docstring into the public OpenAPI document.
 */

import type { Names } from "./naming.js";

export interface RenderContext {
  names: Names;
  /** Flags `# keel:if <flag>` tests against. */
  flags: Set<string>;
  /** Line blocks that replace each `# keel:insert <slot>`. */
  inserts: Record<string, string[]>;
}

export class TemplateError extends Error {}

const IF_RE = /^\s*#\s*keel:if\s+([a-z0-9_-]+)\s*$/;
const ENDIF_RE = /^\s*#\s*keel:endif\s*$/;
const INSERT_RE = /^\s*#\s*keel:insert\s+([a-z0-9_-]+)\s*$/;

/** Substitutes the tokens. Plural before singular within each case, so
 * `__Resources__` is never matched as `__Resource__` followed by a stray
 * `s__`. */
export function substituteTokens(input: string, names: Names): string {
  return input
    .replaceAll("__Resources__", names.Resources)
    .replaceAll("__resources__", names.resources)
    .replaceAll("__RESOURCES__", names.RESOURCES)
    .replaceAll("__Resource__", names.Resource)
    .replaceAll("__resource__", names.resource)
    .replaceAll("__RESOURCE__", names.RESOURCE)
    .replaceAll("__app__", names.app);
}

/**
 * Resolves the marker comments, then substitutes tokens over the result.
 *
 * Order matters: markers are resolved first so an inserted block is not
 * itself re-scanned for markers (a generator-rendered line containing
 * "# keel:if" would otherwise be interpreted rather than emitted), and
 * tokens are substituted last so inserted blocks get the same treatment
 * as template text.
 */
export function render(source: string, context: RenderContext, label: string): string {
  const lines = source.split("\n");
  const out: string[] = [];
  /** Stack of "is this region being kept". */
  const keeping: boolean[] = [];
  const isKeeping = () => keeping.every(Boolean);

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]!;

    const ifMatch = IF_RE.exec(line);
    if (ifMatch) {
      keeping.push(context.flags.has(ifMatch[1]!));
      continue;
    }
    if (ENDIF_RE.test(line)) {
      if (keeping.length === 0) {
        throw new TemplateError(`${label}:${i + 1}: "# keel:endif" with no matching "# keel:if".`);
      }
      keeping.pop();
      continue;
    }

    if (!isKeeping()) continue;

    const insertMatch = INSERT_RE.exec(line);
    if (insertMatch) {
      const slot = insertMatch[1]!;
      const block = context.inserts[slot];
      if (block === undefined) {
        throw new TemplateError(
          `${label}:${i + 1}: no lines supplied for insertion slot "${slot}". ` +
            `Every "# keel:insert" in a template must have a matching entry in the ` +
            `generator's insert map — a missing one is a generator bug, not an empty region.`,
        );
      }
      out.push(...block);
      continue;
    }

    out.push(line);
  }

  if (keeping.length > 0) {
    throw new TemplateError(`${label}: ${keeping.length} unclosed "# keel:if" region(s).`);
  }

  return substituteTokens(collapseBlankRuns(out).join("\n"), context.names);
}

/**
 * Dropping a `# keel:if` region routinely leaves three blank lines where
 * Python wants two, and `ruff format --check` is a gate this generator has
 * to pass without a formatting pass of its own. Collapsing any run of 3+
 * blank lines to 2 is the whole fix, and it cannot affect a file with no
 * dropped regions (Python source never legitimately has three blank lines
 * in a row — ruff format removes them).
 */
function collapseBlankRuns(lines: string[]): string[] {
  const out: string[] = [];
  let blanks = 0;
  for (const line of lines) {
    if (line.trim() === "") {
      blanks += 1;
      if (blanks > 2) continue;
    } else {
      blanks = 0;
    }
    out.push(line);
  }
  return out;
}

/** Applies the same token substitution to a template's own path. */
export function renderPath(relativePath: string, names: Names): string {
  return substituteTokens(relativePath, names);
}
