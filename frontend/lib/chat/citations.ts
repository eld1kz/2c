// The agent cites evidence as [[type:id]] (SPEC §7). In the final answer each becomes a markdown
// link with the private `cite:` scheme, which the renderer turns into an evidence chip.

export const CITATION = /\[\[([a-z_]{1,30}:[A-Za-z0-9_]{1,40})\]\]/g;
export const CITE_SCHEME = "cite:";

export function linkCitations(markdown: string): string {
  return markdown.replace(CITATION, (_, ref: string) => `[${ref}](${CITE_SCHEME}${ref})`);
}

/** Visible while drafting: citations stay as quiet plain text until the answer is checked. */
export function plainCitations(text: string): string {
  return text.replace(CITATION, "[$1]");
}
