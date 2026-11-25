"use strict";

const base = document.body.dataset.base;
const form = document.querySelector("#chat-form");
const input = document.querySelector("#message");
const messages = document.querySelector("#messages");
const statusText = document.querySelector("#status");
const sendButton = document.querySelector("#send");
const clearButton = document.querySelector("#clear");

function newId() {
  const bytes = crypto.getRandomValues(new Uint8Array(24));
  return Array.from(bytes, value => value.toString(16).padStart(2, "0")).join("");
}

let sessionId;
try {
  sessionId = localStorage.getItem("viikko5-session");
  if (!/^[a-f0-9]{48}$/.test(sessionId || "")) {
    sessionId = newId();
    localStorage.setItem("viikko5-session", sessionId);
  }
} catch {
  sessionId = newId();
}

function bubble(role, content) {
  const element = document.createElement("div");
  element.className = `bubble ${role === "user" ? "user" : "assistant"}`;
  element.textContent = content;
  messages.append(element);
  return element;
}

function busy(value) {
  sendButton.disabled = value;
  clearButton.disabled = value;
  input.disabled = value;
}

async function loadHistory() {
  busy(true);
  try {
    const response = await fetch(`${base}/api/history/${sessionId}`);
    if (!response.ok) throw new Error("Keskusteluhistorian lataus epäonnistui.");
    const history = await response.json();
    for (const item of history) bubble(item.role, item.content);
    statusText.textContent = "Valmis.";
  } catch (error) {
    statusText.textContent = error.message;
  } finally {
    busy(false);
  }
}

form.addEventListener("submit", async event => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message) return;

  busy(true);
  bubble("user", message);
  input.value = "";
  const answer = bubble("assistant", "");
  statusText.textContent = "Malli vastaa…";
  let done = false;

  function processLine(line) {
    if (!line.trim()) return;
    const item = JSON.parse(line);
    if (item.error) throw new Error(item.error);
    if (item.token) answer.textContent += item.token;
    if (item.done) done = true;
  }

  try {
    const response = await fetch(`${base}/api/chat`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({session_id: sessionId, message}),
    });

    if (!response.ok) {
      if (response.status === 429) {
        throw new Error("Liian monta viestiä. Odota hetki ennen seuraavaa.");
      }
      const data = await response.json().catch(() => ({}));
      throw new Error(data.error || `Palvelinvirhe ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let pending = "";
    try {
      while (true) {
        const result = await reader.read();
        if (result.done) break;
        pending += decoder.decode(result.value, {stream: true});
        const lines = pending.split("\n");
        pending = lines.pop();
        for (const line of lines) processLine(line);
      }
      pending += decoder.decode();
      processLine(pending);
      if (!done) throw new Error("Yhteys katkesi ennen vastauksen valmistumista.");
    } finally {
      await reader.cancel().catch(() => {});
      reader.releaseLock();
    }

    statusText.textContent = "Vastaus tallennettu.";
  } catch (error) {
    if (!answer.textContent) answer.textContent = "Vastausta ei saatu.";
    statusText.textContent = error.message;
  } finally {
    busy(false);
    input.focus();
  }
});

clearButton.addEventListener("click", async () => {
  if (!confirm("Poistetaanko tämän keskustelun tallennetut viestit?")) return;
  busy(true);
  try {
    const response = await fetch(`${base}/api/history/${sessionId}`, {
      method: "DELETE",
    });
    if (!response.ok) throw new Error("Poistaminen epäonnistui.");
    messages.replaceChildren();
    statusText.textContent = "Keskustelu poistettu.";
  } catch (error) {
    statusText.textContent = error.message;
  } finally {
    busy(false);
  }
});

loadHistory();
