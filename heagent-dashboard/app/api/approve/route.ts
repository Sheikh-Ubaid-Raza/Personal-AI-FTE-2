import { NextRequest, NextResponse } from "next/server";
import { approveTask } from "@/lib/vault";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  try {
    const body     = await request.json() as { filename?: string };
    const filename = body?.filename;
    if (!filename || typeof filename !== "string") {
      return NextResponse.json({ ok: false, message: "filename required" }, { status: 400 });
    }
    // Security: only allow Plan_ prefixed .md files
    if (!filename.startsWith("Plan_") || !filename.endsWith(".md") || filename.includes("/")) {
      return NextResponse.json({ ok: false, message: "Invalid filename" }, { status: 400 });
    }
    const result = await approveTask(filename);
    return NextResponse.json(result, { status: result.ok ? 200 : 400 });
  } catch {
    return NextResponse.json({ ok: false, message: "Server error" }, { status: 500 });
  }
}
