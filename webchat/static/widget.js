function el(tag, className) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  return n;
}

/** Convierte URLs y correos en <a>, de forma segura */
function linkifyText(text) {
  const container = document.createElement("span");
  const urlRegex = /\b((?:https?:\/\/|www\.)[^\s<]+)|([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})/gi;

  let lastIndex = 0;
  let match;
  while ((match = urlRegex.exec(text)) !== null) {
    // texto previo
    if (match.index > lastIndex) {
      container.appendChild(document.createTextNode(text.slice(lastIndex, match.index)));
    }
    const token = match[0];
    let href = token;

    if (token.includes("@") && !token.startsWith("http")) {
      href = `mailto:${token}`;
    } else if (!token.startsWith("http")) {
      href = `https://${token}`;
    }

    const a = document.createElement("a");
    a.href = href;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.textContent = token;
    container.appendChild(a);

    lastIndex = urlRegex.lastIndex;
  }
  // resto
  if (lastIndex < text.length) {
    container.appendChild(document.createTextNode(text.slice(lastIndex)));
  }
  return container;
}

function addMessage(role, text) {
  const msg = el("div", `mensaje ${role}`);
  msg.appendChild(linkifyText(String(text || "").trim()));
  const chatBox = document.getElementById("chatBox");
  chatBox.appendChild(msg);
  chatBox.scrollTop = chatBox.scrollHeight;
}

function toggleChat() {
  const chatWindow = document.getElementById("chatWindow");
  const chatBox = document.getElementById("chatBox");
  const isOpen = chatWindow.style.display === "flex";

  if (isOpen) {
    chatWindow.style.display = "none";
    return;
  }

  chatWindow.style.display = "flex";
  if (!chatBox.dataset.greeted) {
    addMessage("bot", "👋 Hola, soy el chatbot de UESVALLE. ¿En qué puedo ayudarte hoy?");
    chatBox.dataset.greeted = "1";
  }
}

async function sendMessage() {
  const input = document.getElementById("userInput");
  const text = input.value.trim();
  if (!text) return;

  addMessage("user", text);
  input.value = "";

  // indicador simple "escribiendo…"
  const thinking = el("div", "mensaje bot");
  thinking.textContent = "…";
  document.getElementById("chatBox").appendChild(thinking);

  try {
    const res = await fetch(`/preguntar?q=${encodeURIComponent(text)}`);
    const data = await res.json();
    thinking.remove();
    addMessage("bot", (data && data.respuesta) ? data.respuesta : "No pude obtener respuesta.");
  } catch (e) {
    thinking.remove();
    addMessage("bot", "Error de conexión. Intenta más tarde.");
  }
}

window.addEventListener("load", () => {
  const input = document.getElementById("userInput");
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
});

