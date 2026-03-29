import { NextResponse } from "next/server";
import { getFinancialData } from "@/lib/odoo";

export const dynamic = "force-dynamic";
// Cache for 5 minutes — Odoo data doesn't change per-second
export const revalidate = 300;

export async function GET() {
  const data = await getFinancialData();
  return NextResponse.json(data);
}
