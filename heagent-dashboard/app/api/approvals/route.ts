import { NextResponse } from "next/server";
import { listApprovals } from "@/lib/vault";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET() {
  const approvals = await listApprovals();
  return NextResponse.json({ approvals, count: approvals.length });
}
