import { NextRequest, NextResponse } from "next/server";
import { listBriefings } from "@/lib/vault";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET(request: NextRequest) {
  const slug = request.nextUrl.searchParams.get("file");
  const briefings = await listBriefings();

  if (slug) {
    const found = briefings.find((b) => b.filename === slug);
    if (!found) return NextResponse.json({ error: "Not found" }, { status: 404 });
    return NextResponse.json(found);
  }

  // Return list without full content to keep response small
  return NextResponse.json({
    briefings: briefings.map(({ content: _, ...rest }) => rest),
  });
}
