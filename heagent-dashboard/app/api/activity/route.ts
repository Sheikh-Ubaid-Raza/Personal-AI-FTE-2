import { NextRequest, NextResponse } from "next/server";
import { getRecentActivity } from "@/lib/vault";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET(request: NextRequest) {
  const limit = parseInt(request.nextUrl.searchParams.get("limit") ?? "20", 10);
  const activity = await getRecentActivity(Math.min(limit, 50));
  return NextResponse.json({ activity, count: activity.length });
}
