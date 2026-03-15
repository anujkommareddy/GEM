import { NextResponse } from "next/server";

export async function POST(request: Request) {
  try {
    const { name, email, project } = await request.json();

    if (!name || !email) {
      return NextResponse.json(
        { error: "Name and email are required" },
        { status: 400 }
      );
    }

    const supabaseUrl = process.env.SUPABASE_URL;
    const supabaseKey = process.env.SUPABASE_SERVICE_KEY;

    if (!supabaseUrl || !supabaseKey) {
      // Fallback: log to stdout so Vercel logs capture it
      console.log("WAITLIST_SIGNUP:", JSON.stringify({ name, email, project, timestamp: new Date().toISOString() }));
      return NextResponse.json({ success: true });
    }

    const res = await fetch(`${supabaseUrl}/rest/v1/waitlist`, {
      method: "POST",
      headers: {
        apikey: supabaseKey,
        Authorization: `Bearer ${supabaseKey}`,
        "Content-Type": "application/json",
        Prefer: "return=minimal",
      },
      body: JSON.stringify({
        name,
        email,
        project: project || null,
        created_at: new Date().toISOString(),
      }),
    });

    if (!res.ok) {
      const errorText = await res.text();
      console.error("Supabase error:", errorText);
      // Still return success to user — we logged it
      console.log("WAITLIST_SIGNUP_FALLBACK:", JSON.stringify({ name, email, project, timestamp: new Date().toISOString() }));
    }

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error("Waitlist error:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
