import * as vscode from "vscode";

// The extension is deliberately thin: the full UI (streaming, diffs, approvals, cancel, undo) is the same web
// app served by `rx serve`, hosted here in an iframe. One UI to maintain, identical behaviour everywhere.

const TOKEN_KEY = "rx.token";
let panel: vscode.WebviewPanel | undefined;

function serverUrl(): string {
  return vscode.workspace.getConfiguration("rx").get<string>("serverUrl", "http://127.0.0.1:8000").replace(/\/+$/, "");
}

function isLoopback(url: string): boolean {
  try {
    const host = new URL(url).hostname;
    return host === "127.0.0.1" || host === "localhost" || host === "[::1]" || host === "::1";
  } catch {
    return false;
  }
}

async function getToken(context: vscode.ExtensionContext, force = false): Promise<string | undefined> {
  let token = force ? undefined : await context.secrets.get(TOKEN_KEY);
  if (!token) {
    token = await vscode.window.showInputBox({
      title: "RX server token",
      prompt: "Paste the token printed by `rx serve` (stored in VS Code's secret storage).",
      password: true,
      ignoreFocusOut: true,
    });
    if (token) await context.secrets.store(TOKEN_KEY, token.trim());
  }
  return token?.trim();
}

async function healthy(url: string): Promise<boolean> {
  try {
    const res = await fetch(`${url}/health`, { signal: AbortSignal.timeout(2500) });
    return res.ok;
  } catch {
    return false;
  }
}

function nonce(): string {
  const chars = "abcdefghijklmnopqrstuvwxyz0123456789";
  return Array.from({ length: 24 }, () => chars[Math.floor(Math.random() * chars.length)]).join("");
}

async function openPanel(context: vscode.ExtensionContext): Promise<void> {
  const url = serverUrl();
  if (!isLoopback(url)) {
    const go = await vscode.window.showWarningMessage(
      `RX is configured with a non-loopback server (${url}). The agent can run commands on that machine. Continue?`,
      { modal: true }, "Continue");
    if (go !== "Continue") return;
  }
  if (!(await healthy(url))) {
    const pick = await vscode.window.showErrorMessage(`No RX server answered at ${url}.`, "Start Local Server");
    if (pick) await vscode.commands.executeCommand("rx.startServer");
    return;
  }
  const token = await getToken(context);
  if (!token) return;
  const folder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? "";
  const frame = `${url}/ui#token=${encodeURIComponent(token)}&workspace=${encodeURIComponent(folder)}`;

  if (panel) {
    panel.reveal();
  } else {
    panel = vscode.window.createWebviewPanel("rxAgent", "RX Agent", vscode.ViewColumn.Beside,
      { enableScripts: true, retainContextWhenHidden: true });
    panel.onDidDispose(() => { panel = undefined; }, null, context.subscriptions);
  }
  const n = nonce();
  panel.webview.html = `<!doctype html><html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; frame-src ${url}; style-src 'nonce-${n}';">
<style nonce="${n}">html,body,iframe{margin:0;padding:0;width:100%;height:100%;border:0;overflow:hidden}</style></head>
<body><iframe src="${frame}" title="RX Agent"></iframe></body></html>`;
}

export function activate(context: vscode.ExtensionContext): void {
  context.subscriptions.push(
    vscode.commands.registerCommand("rx.open", () => openPanel(context)),
    vscode.commands.registerCommand("rx.setToken", async () => {
      if (await getToken(context, true)) vscode.window.showInformationMessage("RX token saved.");
    }),
    vscode.commands.registerCommand("rx.startServer", async () => {
      const folder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? process.cwd();
      const template = vscode.workspace.getConfiguration("rx").get<string>("serverCommand", "rx serve");
      const terminal = vscode.window.createTerminal({ name: "RX Server", cwd: folder });
      terminal.show();
      terminal.sendText(template.replace(/\$\{workspaceFolder\}/g, folder));
      vscode.window.showInformationMessage(
        "RX server starting. Copy the token it prints, run 'RX: Set Server Token', then 'RX: Open Agent'.");
    }),
  );
}

export function deactivate(): void {
  panel?.dispose();
}
