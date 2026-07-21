// Langfuse tracing wrapper — every LLM leaf runs inside trace() so the bake-off
// gets model/tokens/cost/latency per role, per harness (RFC-0002). Points at the
// self-hosted Langfuse on the homelab (http://homelab:4000).
//
// STATUS: minimal. Swap the console span for the langfuse SDK client when wiring.

export interface LangfuseCfg {
  host: string; // http://homelab:4000
  publicKey: string;
  secretKey: string;
}

export async function trace<T>(
  name: string,
  model: string,
  issueNumber: number,
  fn: () => Promise<T>,
): Promise<T> {
  const started = Date.now();
  try {
    const out = await fn();
    // TODO(langfuse): emit a span {name, model, issueNumber, latency, tokens, cost}
    console.error(`[trace] ${name} model=${model} issue=#${issueNumber} ok ${Date.now() - started}ms`);
    return out;
  } catch (e) {
    console.error(`[trace] ${name} model=${model} issue=#${issueNumber} ERR ${Date.now() - started}ms`);
    throw e;
  }
}
