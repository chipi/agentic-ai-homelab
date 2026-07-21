// Fleet registry — loads the specialist agents from bugfix-fleet/agents/*.md
// (opencode-native markdown + frontmatter, so the SAME files feed opencode
// natively and our dispatcher/pi adapter — the shared bake-off artifact).

import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

export interface Agent {
  name: string;
  description: string; // the dispatch key
  model: string;
  area: string;
  systemPrompt: string;
}

// simple frontmatter parse (no yaml dep): key: value lines between --- ... ---
function parseAgent(file: string): Agent {
  const raw = fs.readFileSync(file, "utf8");
  const m = raw.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/);
  if (!m) throw new Error(`bad agent file (no frontmatter): ${file}`);
  const fm: Record<string, string> = {};
  for (const line of m[1].split("\n")) {
    const kv = line.match(/^(\w+):\s*(.*)$/);
    if (kv) fm[kv[1]] = kv[2].trim();
  }
  return {
    name: fm.name, description: fm.description, model: fm.model,
    area: fm.area ?? fm.name, systemPrompt: m[2].trim(),
  };
}

export function loadAgents(): Agent[] {
  const here = path.dirname(fileURLToPath(import.meta.url));
  const dir = path.resolve(here, "../../agents"); // bugfix-fleet/agents
  return fs.readdirSync(dir).filter((f) => f.endsWith(".md")).map((f) => parseAgent(path.join(dir, f)));
}
