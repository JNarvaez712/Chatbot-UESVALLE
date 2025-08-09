function el(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text !== undefined) n.textContent = text;
  return n;
}

function toggleChat() {
  const chatWindow = document.getElementById("chatWindow");
  const chatBox = document.getElementById("chatBox");

  const isOpen = chatWindow.style.display === "flex";
  chatWindow.style.display = isOpen ? "none" : "flex";

  if (!isOpen && !chatBox.dataset.greeted) {
    chatBox.appendChild(el("div", "mensaje bot", "👋 Hola, soy el chatbot de UESVALLE. ¿En qué puedo ayudarte hoy?"));
    chatBox.dataset.greeted = "1";
  }
  if (isOpen) {
    chatBox.innerHTML = "";
    delete chatBox.dataset.greeted;
  }
}

async function sendMessage() {
  const input = document.getElementById("userInput");
  const chatBox = document.getElementById("chatBox");
  const text = input.value.trim();
  if (!text) return;

  chatBox.appendChild(el("div", "mensaje user", text));
  input.value = "";

  try {
    const res = await fetch(`/preguntar?q=${encodeURIComponent(text)}`);
    const data = await res.json();
    const msg = data && data.respuesta ? data.respuesta : "No pude obtener respuesta.";
    chatBox.appendChild(el("div", "mensaje bot", msg));
  } catch (e) {
    chatBox.appendChild(el("div", "mensaje bot", "Error de conexión. Intenta más tarde."));
  } finally {
    chatBox.scrollTop = chatBox.scrollHeight;
  }
}

window.onload = function () {
  const input = document.getElementById("userInput");
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
};

