"use client";

import type { UserProfile } from "@contracts/api";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { SwanShell } from "@/components/swan/Shell";
import { getClient } from "@/lib/client";

export default function ProfilePage() {
  const client = useMemo(getClient, []);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    client.getProfile().then(setProfile).catch(() => setProfile(null));
  }, [client]);

  async function save(next: UserProfile) {
    setProfile(next);
    await client.putProfile(next);
    setSaved(true);
  }

  async function remove() {
    await client.deleteAccount();
    setProfile(null);
  }

  if (!profile) {
    return (
      <SwanShell>
        <h1 className="text-4xl">No profile yet</h1>
        <Link href="/onboarding" className="swan-btn mt-6 inline-flex items-center">Set up Swan</Link>
      </SwanShell>
    );
  }

  return (
    <SwanShell>
      <h1 className="text-4xl">Profile</h1>
      {saved && <p className="mt-2 text-sm" role="status">Saved</p>}
      <label className="mt-6 block">Name
        <input className="swan-line mt-2 w-full rounded-2xl border px-3 py-3" value={profile.name} onChange={(event) => save({ ...profile, name: event.target.value })} />
      </label>
      <label className="mt-3 block">Home
        <input className="swan-line mt-2 w-full rounded-2xl border px-3 py-3" value={profile.home.address} onChange={(event) => save({ ...profile, home: { ...profile.home, address: event.target.value } })} />
      </label>
      <p className="swan-muted mt-3 text-sm">Airports {profile.home.airport_codes.join(" · ")}</p>
      <p className="mt-3">Wake {profile.sleep.wake_time} · sleep {profile.sleep.sleep_time}</p>
      <p className="mt-1">Interests {profile.travel.interests.join(", ")}</p>
      <button type="button" className="swan-btn-ghost mt-8" onClick={remove}>Delete my account</button>
    </SwanShell>
  );
}
