import { NextResponse } from "next/server";

export interface ArxivResult {
  arxiv_id: string;
  title: string;
  authors: string[];
  abstract: string;
  published: string;
}

export async function GET(request: Request): Promise<NextResponse> {
  const { searchParams } = new URL(request.url);
  const q = searchParams.get("q")?.trim() ?? "";

  if (q.length < 3) return NextResponse.json([]);

  const query = encodeURIComponent(`ti:${q}`);
  const url = `https://export.arxiv.org/api/query?search_query=${query}&max_results=8&sortBy=relevance`;

  const res = await fetch(url, {
    headers: { "User-Agent": "paper2md/1.0" },
    next: { revalidate: 300 },
  });

  if (!res.ok) {
    return NextResponse.json({ error: "ArXiv API error" }, { status: 502 });
  }

  const xml = await res.text();
  const results = parseAtomFeed(xml);
  return NextResponse.json(results);
}

function parseAtomFeed(xml: string): ArxivResult[] {
  const entries = xml.match(/<entry>([\s\S]*?)<\/entry>/g) ?? [];

  return entries.map((entry) => {
    const id = (entry.match(/<id>.*\/abs\/([^<\s]+)<\/id>/) ?? [])[1] ?? "";
    // Strip version suffix e.g. v3
    const arxiv_id = id.replace(/v\d+$/, "");

    const title = decode(
      (entry.match(/<title>([\s\S]*?)<\/title>/) ?? [])[1]?.trim() ?? ""
    );

    const authorMatches = [...entry.matchAll(/<name>([\s\S]*?)<\/name>/g)];
    const authors = authorMatches.map((m) => decode(m[1].trim()));

    const abstract = decode(
      (entry.match(/<summary>([\s\S]*?)<\/summary>/) ?? [])[1]?.trim() ?? ""
    ).replace(/\s+/g, " ");

    const published =
      (entry.match(/<published>([\s\S]*?)<\/published>/) ?? [])[1]?.slice(
        0,
        10
      ) ?? "";

    return { arxiv_id, title, authors, abstract, published };
  });
}

function decode(s: string): string {
  return s
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'");
}
