"use client";

import { useEffect, useState } from "react";
import { UserPlus } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, ApiError } from "@/lib/api";
import type { User } from "@/types";

export default function UsersPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [form, setForm] = useState({ email: "", username: "", full_name: "", password: "", role: "USER" });
  const [error, setError] = useState<string | null>(null);

  function load() {
    api.get<User[]>("/api/v1/users").then(setUsers).catch(() => {});
  }
  useEffect(load, []);

  async function createUser() {
    setError(null);
    try {
      await api.post("/api/v1/users", form);
      setForm({ email: "", username: "", full_name: "", password: "", role: "USER" });
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create user");
    }
  }

  async function toggleActive(u: User) {
    await api.patch(`/api/v1/users/${u.id}/${u.is_active ? "deactivate" : "activate"}`);
    load();
  }

  return (
    <AppShell title="Users" adminOnly>
      <Card className="mb-5">
        <CardHeader>
          <CardTitle>Add User</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            <Input placeholder="Full name" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} className="w-auto" />
            <Input placeholder="Username" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} className="w-auto" />
            <Input placeholder="Email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} className="w-auto" />
            <Input
              placeholder="Password"
              type="password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              className="w-auto"
            />
            <Select value={form.role} onValueChange={(v) => setForm({ ...form, role: v ?? "USER" })}>
              <SelectTrigger className="w-[220px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="USER">Staff (USER)</SelectItem>
                <SelectItem value="ADMIN">Security Administrator (ADMIN)</SelectItem>
              </SelectContent>
            </Select>
            <Button size="sm" onClick={createUser}>
              <UserPlus /> Create
            </Button>
          </div>
          {error && <p className="mt-2 text-sm text-destructive">{error}</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>All Users</CardTitle>
          <CardDescription>{users.length} account(s)</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {users.map((u) => (
            <div key={u.id} className="flex items-center justify-between rounded-lg border px-4 py-3">
              <div>
                <p className="text-sm font-medium">{u.full_name || u.username}</p>
                <p className="text-xs text-muted-foreground">
                  {u.email} &middot; {u.username}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <Badge variant="secondary">{u.role}</Badge>
                <Badge variant={u.is_active ? "default" : "secondary"}>{u.is_active ? "Active" : "Deactivated"}</Badge>
                <Button size="sm" variant="outline" onClick={() => toggleActive(u)}>
                  {u.is_active ? "Deactivate" : "Activate"}
                </Button>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </AppShell>
  );
}
