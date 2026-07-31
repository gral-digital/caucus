/**
 * Taskpane Caucus per Word.
 *
 * Tre funzioni: ricerca giuridica (stream SSE dalla stessa API della web
 * app), inserimento della risposta nel documento, verifica delle citazioni
 * del documento aperto contro il corpus (trust layer via
 * /api/v1/citations/validate).
 *
 * La pagina è servita dalla web app Next (stessa origin → il rewrite
 * /api/v1 evita i problemi CORS). Fuori da Word le funzioni documento sono
 * disabilitate con un avviso, così la pagina resta ispezionabile nel
 * browser.
 */

/* global Office, Word */

let inWord = false;
let lastAnswerText = "";

const $ = (id) => document.getElementById(id);

// ---------------------------------------------------------------- bootstrap

if (typeof Office !== "undefined" && Office.onReady) {
  Office.onReady((info) => {
    inWord = info.host === Office.HostType.Word;
    if (!inWord) $("outside-office").hidden = false;
  });
} else {
  $("outside-office").hidden = false;
}

for (const tab of document.querySelectorAll(".tab")) {
  tab.addEventListener("click", () => {
    for (const t of document.querySelectorAll(".tab")) t.classList.remove("active");
    tab.classList.add("active");
    $("panel-ricerca").hidden = tab.dataset.tab !== "ricerca";
    $("panel-verifica").hidden = tab.dataset.tab !== "verifica";
  });
}

// ---------------------------------------------------------------- ricerca

const CITE_RE = /<cite\s+source="([a-z0-9-]+)"\s+part="[a-z]+"\s+num="([^"]+)"(?:\s+comma="([^"]+)")?\s*\/>/gi;

function renderAnswer(raw) {
  const el = $("answer");
  el.textContent = "";
  let last = 0;
  for (const m of raw.matchAll(CITE_RE)) {
    el.appendChild(document.createTextNode(raw.slice(last, m.index)));
    const span = document.createElement("span");
    span.className = "cite";
    span.textContent = `art. ${m[2]} ${m[1]}`;
    el.appendChild(span);
    last = m.index + m[0].length;
  }
  el.appendChild(document.createTextNode(raw.slice(last)));
}

$("ask").addEventListener("click", async () => {
  const question = $("question").value.trim();
  if (!question) return;
  $("ask").disabled = true;
  $("answer").hidden = false;
  $("insert").hidden = true;
  $("answer-status").hidden = false;
  $("answer-status").textContent = "Cerco nelle fonti…";
  lastAnswerText = "";

  try {
    const res = await fetch("/api/v1/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, mode: "ricerca" }),
    });
    if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let streaming = true;
    while (streaming) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      // Parse SSE minimale: righe "event: x" / "data: {json}"
      let event = null;
      for (const line of buffer.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7).trim();
        else if (line.startsWith("data: ") && event) {
          try {
            const data = JSON.parse(line.slice(6));
            if (event === "token" && data.text) {
              lastAnswerText += data.text;
              renderAnswer(lastAnswerText);
              $("answer-status").textContent = "";
            } else if (event === "done") {
              if (data.final_text) lastAnswerText = data.final_text;
              streaming = false;
            } else if (event === "error") {
              throw new Error(data.message || "errore");
            }
          } catch (e) {
            if (e instanceof SyntaxError) continue; // frame parziale
            throw e;
          }
          event = null;
        }
      }
      // Tieni solo l'ultima riga (potenzialmente parziale)
      buffer = buffer.slice(buffer.lastIndexOf("\n") + 1);
    }
    renderAnswer(lastAnswerText);
    $("answer-status").hidden = true;
    if (inWord && lastAnswerText) $("insert").hidden = false;
  } catch (err) {
    $("answer-status").textContent = `Errore: ${err.message}. L'API Caucus è raggiungibile?`;
  } finally {
    $("ask").disabled = false;
  }
});

$("insert").addEventListener("click", async () => {
  if (!inWord || !lastAnswerText) return;
  // Nel documento le citazioni vanno in forma canonica testuale, senza tag.
  const clean = lastAnswerText
    .replace(CITE_RE, (_, source, num) => `art. ${num} ${source}`)
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/^#+\s*/gm, "");
  await Word.run(async (context) => {
    const selection = context.document.getSelection();
    selection.insertText(clean, Word.InsertLocation.replace);
    await context.sync();
  });
});

// ---------------------------------------------------------------- verifica

function checkItem(kind, ref, note) {
  const div = document.createElement("div");
  div.className = `check-item ${kind}`;
  const refSpan = document.createElement("span");
  refSpan.className = "ref";
  refSpan.textContent = ref;
  const noteSpan = document.createElement("span");
  noteSpan.textContent = note;
  div.append(refSpan, noteSpan);
  return div;
}

$("verify").addEventListener("click", async () => {
  const status = $("verify-status");
  const results = $("verify-results");
  results.hidden = true;
  results.textContent = "";
  status.hidden = false;

  let text = "";
  if (inWord) {
    status.textContent = "Leggo il documento…";
    await Word.run(async (context) => {
      const body = context.document.body;
      body.load("text");
      await context.sync();
      text = body.text || "";
    });
  } else {
    status.textContent = "Fuori da Word: incolla il testo nella domanda del tab Ricerca.";
    return;
  }
  if (!text.trim()) {
    status.textContent = "Il documento è vuoto.";
    return;
  }

  status.textContent = "Verifico le citazioni sul corpus…";
  try {
    const res = await fetch("/api/v1/citations/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text.slice(0, 300000) }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    status.hidden = true;
    results.hidden = false;
    if (data.total === 0) {
      results.appendChild(
        checkItem("warn", "—", "Nessun riferimento normativo riconosciuto nel documento."),
      );
      return;
    }
    for (const c of data.valid) {
      const ref = `art. ${c.num} ${c.source}`;
      if (c.abrogato) {
        results.appendChild(
          checkItem("warn", ref, "ABROGATO: citarlo come vigente è un errore."),
        );
      } else {
        results.appendChild(checkItem("ok", ref, "Verificato, vigente."));
      }
    }
    for (const c of data.invalid) {
      results.appendChild(
        checkItem("bad", `art. ${c.num} ${c.source}`, c.reason || "Non trovato nel corpus."),
      );
    }
  } catch (err) {
    status.textContent = `Errore: ${err.message}. L'API Caucus è raggiungibile?`;
  }
});
