"use client";

import { useEffect, useState } from "react";
import { Plus, Trash2, KeyRound, Download, Monitor } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { api, ApiError } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";
import type { ApiToken, ApiTokenCreated } from "@/types";

export default function TokensPage() {
  const [tokens, setTokens] = useState<ApiToken[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [justCreated, setJustCreated] = useState<ApiTokenCreated | null>(null);

  function load() {
    api.get<ApiToken[]>("/api/v1/tokens").then(setTokens).catch(() => {});
  }
  useEffect(load, []);

  async function createToken() {
    if (!name.trim()) return;
    setError(null);
    try {
      const created = await api.post<ApiTokenCreated>("/api/v1/tokens", { name });
      setJustCreated(created);
      setName("");
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create token");
    }
  }

  async function revoke(t: ApiToken) {
    setError(null);
    try {
      await api.del(`/api/v1/tokens/${t.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to revoke token");
    } finally {
      load();
    }
  }

  return (
    <AppShell title="Personal Access Tokens">
      <Card className="mb-5">
        <CardContent className="flex gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Monitor size={17} />
          </span>
          <div>
            <p className="text-sm font-semibold">For the SecurePrint Windows Agent</p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              A personal access token lets the desktop notification agent watch your print jobs and pop up a Windows
              alert the moment sensitive data is identified — without ever storing your account password on that
              machine. Create a token below, paste it into the agent&apos;s <code className="text-[11px]">config.yaml</code>,
              and revoke it any time from here.
            </p>
          </div>
        </CardContent>
      </Card>

      {justCreated && (
        <Alert className="mb-5">
          <AlertTitle>Token &quot;{justCreated.name}&quot; created</AlertTitle>
          <AlertDescription>
            This is shown once — copy it into the agent&apos;s config now. It won&apos;t be shown again.
            <code className="mt-2 block rounded bg-muted px-2 py-1 break-all">{justCreated.token}</code>
          </AlertDescription>
        </Alert>
      )}

      <Card className="mb-5">
        <CardHeader>
          <CardTitle>Create a Token</CardTitle>
          <CardDescription>Give it a name that identifies the machine it will run on</CardDescription>
        </CardHeader>
        <CardContent className="flex gap-2">
          <Input placeholder="e.g. Office Desktop" value={name} onChange={(e) => setName(e.target.value)} className="max-w-xs" />
          <Button size="sm" onClick={createToken}>
            <Plus /> Create Token
          </Button>
        </CardContent>
        {error && <p className="px-6 pb-4 text-sm text-destructive">{error}</p>}
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Your Tokens</CardTitle>
          <CardDescription>{tokens.length} token(s)</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {tokens.map((t) => (
            <div key={t.id} className="flex items-center justify-between rounded-lg border px-4 py-3">
              <div className="flex items-center gap-3">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
                  <KeyRound size={16} />
                </span>
                <div>
                  <p className="text-sm font-medium">{t.name}</p>
                  <p className="text-xs text-muted-foreground">
                    <code>{t.token_prefix}…</code> &middot; Created {formatDateTime(t.created_at)}
                    {t.last_used_at ? <> &middot; Last used {formatDateTime(t.last_used_at)}</> : <> &middot; Never used</>}
                  </p>
                </div>
              </div>
              <button onClick={() => revoke(t)} className="text-muted-foreground/50 hover:text-destructive">
                <Trash2 size={14} />
              </button>
            </div>
          ))}
          {tokens.length === 0 && <p className="py-6 text-center text-sm text-muted-foreground">No tokens yet.</p>}
        </CardContent>
      </Card>

      <div className="mt-4 flex items-center gap-2 text-xs text-muted-foreground">
        <Download size={13} />
        Download the agent from{" "}
        <code className="rounded bg-muted px-1 py-0.5 text-[11px]">apps/windows-agent</code> in the SecurePrint
        repository.
      </div>
    </AppShell>
  );
}
