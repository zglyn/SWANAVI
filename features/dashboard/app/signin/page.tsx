"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { SwanShell } from "@/components/swan/Shell";
import { getClient } from "@/lib/client";

export default function SignInPage() {
  const router = useRouter();
  const client = useMemo(getClient, []);
  const [email, setEmail] = useState("");

  async function demo() {
    await client.demoSignIn();
    router.push("/");
  }

  async function send() {
    await client.magicLink(email);
    router.push("/onboarding");
  }

  return (
    <SwanShell>
      <h1 className="text-4xl">Sign in</h1>
      <p className="swan-muted mt-3">Use the demo profile on stage, or send yourself a sign-in link.</p>
      <button type="button" className="swan-btn mt-6" onClick={demo}>Use demo profile</button>
      <form className="mt-6 space-y-3" onSubmit={(event) => { event.preventDefault(); send(); }}>
        <label className="block">Email
          <input type="email" required className="swan-line mt-2 w-full rounded-2xl border px-3 py-3" value={email} onChange={(event) => setEmail(event.target.value)} />
        </label>
        <button type="submit" className="swan-btn-ghost">Email me a link</button>
      </form>
    </SwanShell>
  );
}
