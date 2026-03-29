import { NextResponse } from "next/server";
import { getRalphState, getInboxCount, getNeedsActionCount, getDoneCount } from "@/lib/vault";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET() {
  const [ralph, inbox, action, done] = await Promise.all([
    getRalphState(),
    getInboxCount(),
    getNeedsActionCount(),
    getDoneCount(),
  ]);
  return NextResponse.json({
    ...ralph,
    counts: { inbox, action, done },
    maxIterations: 5,
    isLooping: ralph.iteration > 0,
  });
}
