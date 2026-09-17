const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";

export const runtime = "nodejs";

export async function DELETE(_request: Request, { params }: { params: Promise<{ filename: string }> }) {
  const { filename } = await params;
  const upstream = await fetch(`${backendUrl}/library/${encodeURIComponent(filename)}`, { method: "DELETE" });

  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("content-type") ?? "application/json",
    },
  });
}
