// The only backend calls the browser may make through /api/backend. Anything else is refused,
// so the proxy can't be used to reach routes the UI has no business calling (e.g. POST /actions).

const ALLOWED: Record<"GET" | "POST", RegExp[]> = {
  GET: [
    /^me$/,
    /^position$/,
    /^forecast$/,
    /^forecast\/weeks\/\d{1,2}$/,
    /^insights$/,
    /^llm-budget$/,
    /^actions$/,
    /^records$/,
    /^records\/[a-z_]{1,30}:\d{1,12}$/,
    /^audit$/,
    /^audit\/verify$/,
    /^transactions$/,
  ],
  POST: [/^chat$/, /^actions\/\d{1,12}\/(approve|reject)$/, /^transactions\/\d{1,12}\/category$/, /^upload$/, /^demo\/reset$/, /^whatif$/, /^financing$/],
};

export function isAllowed(method: string, path: string): boolean {
  const rules = ALLOWED[method as keyof typeof ALLOWED];
  return rules !== undefined && rules.some((rule) => rule.test(path));
}
