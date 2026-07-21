// GitHub App auth — the installation-token dance, hidden behind one function so
// the rest of the code never touches JWTs (RFC-0002). Uses @octokit/auth-app.
//
// Needs (from sops): APP_ID, the App's PRIVATE_KEY (.pem contents), and the
// INSTALLATION_ID (from installing the App on the target repo).

import { createAppAuth } from "@octokit/auth-app";
import { Octokit } from "@octokit/rest";

export interface AppConfig {
  appId: string;
  privateKey: string; // PEM contents
  installationId: string;
  webhookSecret: string;
}

export function loadAppConfig(): AppConfig {
  const need = (k: string) => {
    const v = process.env[k];
    if (!v) throw new Error(`missing env ${k} (see .env.example / sops)`);
    return v;
  };
  return {
    appId: need("GITHUB_APP_ID"),
    // allow \n-escaped single-line PEM in env
    privateKey: need("GITHUB_APP_PRIVATE_KEY").replace(/\\n/g, "\n"),
    installationId: need("GITHUB_APP_INSTALLATION_ID"),
    webhookSecret: need("GITHUB_WEBHOOK_SECRET"),
  };
}

/** An Octokit authenticated as the App installation — auto-refreshes the
 *  1-hour installation token under the hood. This is what posts labels,
 *  comments, PRs, and reviews as the bot identity. */
export function installationOctokit(cfg: AppConfig): Octokit {
  return new Octokit({
    authStrategy: createAppAuth,
    auth: {
      appId: cfg.appId,
      privateKey: cfg.privateKey,
      installationId: cfg.installationId,
    },
  });
}

/** Raw installation token — for authenticating git push over HTTPS
 *  (x-access-token:<token>@github.com/...). Expires in ~1h; mint fresh per push. */
export async function getInstallationToken(cfg: AppConfig): Promise<string> {
  const auth = createAppAuth({ appId: cfg.appId, privateKey: cfg.privateKey, installationId: cfg.installationId });
  const { token } = await auth({ type: "installation" });
  return token;
}
