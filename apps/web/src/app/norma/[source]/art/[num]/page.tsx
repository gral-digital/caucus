import Link from "next/link";
import { notFound } from "next/navigation";

type Comma = { number: string; text: string };
type Norma = {
  source: string;
  source_title: string;
  articolo: string;
  rubrica: string | null;
  citation: string;
  abrogato: boolean;
  effective_from: string;
  commi: Comma[];
  source_url: string | null;
};

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function fetchNorma(source: string, num: string): Promise<Norma | null> {
  const res = await fetch(
    `${API}/api/v1/norma/${encodeURIComponent(source)}/art/${encodeURIComponent(num)}`,
    { cache: "no-store" },
  );
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`API ${res.status}`);
  return (await res.json()) as Norma;
}

export default async function NormaPage({
  params,
}: {
  params: Promise<{ source: string; num: string }>;
}) {
  const { source, num } = await params;
  const norma = await fetchNorma(source, num);
  if (!norma) notFound();

  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <Link href="/" className="text-sm text-ink/60 hover:text-ink">
        ← Torna alla chat
      </Link>

      <header className="mt-6 border-b border-ink/10 pb-4">
        <p className="text-sm uppercase tracking-wide text-ink/50">{norma.source_title}</p>
        <h1 className="font-serif text-2xl text-ink">
          Art. {norma.articolo}
          {norma.rubrica ? ` (${norma.rubrica})` : ""}
        </h1>
        <p className="mt-1 text-xs text-ink/50">
          {norma.citation} · testo consolidato al{" "}
          {new Date(norma.effective_from).toLocaleDateString("it-IT")}
        </p>
        {norma.abrogato && (
          <p className="mt-3 rounded border border-amber-400/60 bg-amber-50 px-3 py-2 text-sm text-amber-900">
            ⚠️ Articolo abrogato: il testo è riportato a fini storici.
          </p>
        )}
      </header>

      <article className="prose-legal mt-6 space-y-4">
        {norma.commi.map((c) => (
          <p key={c.number} id={`c${c.number}`} className="scroll-mt-24">
            <span className="mr-2 font-medium text-ink/50">{c.number}.</span>
            {c.text}
          </p>
        ))}
      </article>

      {norma.source_url && (
        <footer className="mt-10 border-t border-ink/10 pt-4 text-xs text-ink/50">
          Fonte ufficiale:{" "}
          <a href={norma.source_url} target="_blank" rel="noreferrer" className="underline">
            {norma.source_url}
          </a>
        </footer>
      )}
    </main>
  );
}
