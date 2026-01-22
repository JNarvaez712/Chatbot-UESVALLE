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

function createBotRow(text) {
  const row = el("div", "row bot");
  const avatar = el("img", "avatar");
  avatar.src = "/static/img/Icono_chatbot.webp";
  avatar.alt = "UESLY";
  const msg = el("div", "mensaje bot");
  msg.appendChild(linkifyText(String(text || "").trim()));
  row.appendChild(avatar);
  row.appendChild(msg);
  return row;
}

function addMessage(role, text) {
  const chatBox = document.getElementById("chatBox");
  if (role === "bot") {
    const row = createBotRow(text);
    chatBox.appendChild(row);
  } else {
    const msg = el("div", `mensaje ${role}`);
    msg.appendChild(linkifyText(String(text || "").trim()));
    chatBox.appendChild(msg);
  }
  chatBox.scrollTop = chatBox.scrollHeight;
}

function toggleChat() {
  const chatWindow = document.getElementById("chatWindow");
  const chatBox = document.getElementById("chatBox");
  const launcher = document.getElementById("chatLauncher");
  const isOpen = chatWindow.style.display === "flex";

  if (isOpen) {
    chatWindow.style.display = "none";
    // devolver foco al launcher para accesibilidad
    if (launcher) launcher.focus();
    return;
  }

  chatWindow.style.display = "flex";
  if (!chatBox.dataset.greeted) {
    addMessage("bot", "Hola, soy Uesly. ¿En qué puedo ayudarte hoy?");
    chatBox.dataset.greeted = "1";
  }
  // enfocar el input al abrir
  const input = document.getElementById("userInput");
  if (input) input.focus();
}

async function sendMessage() {
  const input = document.getElementById("userInput");
  const text = input.value.trim();
  if (!text) return;

  addMessage("user", text);
  input.value = "";

  // indicador simple "escribiendo…"
  const thinkingRow = createBotRow("…");
  document.getElementById("chatBox").appendChild(thinkingRow);

  try {
    const res = await fetch(`/preguntar?q=${encodeURIComponent(text)}`);
    const data = await res.json();
    thinkingRow.remove();
    addMessage("bot", (data && data.respuesta) ? data.respuesta : "No pude obtener respuesta.");
    // mantener foco en el input tras responder
    const input2 = document.getElementById("userInput");
    if (input2) input2.focus();
  } catch (e) {
    thinkingRow.remove();
    addMessage("bot", "Error de conexión. Intenta más tarde.");
    const input2 = document.getElementById("userInput");
    if (input2) input2.focus();
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

  // Saludo inicial automático cuando se carga el widget
  const chatBox = document.getElementById("chatBox");
  if (chatBox && !chatBox.dataset.greeted) {
    addMessage("bot", "Hola, soy tu Asistente Virtual de la UESVALLE. ¿En qué puedo ayudarte hoy?");
    chatBox.dataset.greeted = "1";
  }
});

