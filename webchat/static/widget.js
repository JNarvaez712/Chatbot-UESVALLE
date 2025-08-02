function toggleChat() {
  const chatWindow = document.getElementById("chatWindow");

  const chatBox = document.getElementById("chatBox");
  const mensajeBienvenida = `<div class="mensaje bot">👋 Hola, soy el chatbot de UESVALLE. ¿En qué puedo ayudarte hoy?</div>`;

  if (chatWindow.style.display === "flex") {
    chatWindow.style.display = "none";
    chatBox.innerHTML = ""; // limpiar cuando se cierra
  } else {
    chatWindow.style.display = "flex";
    if (!chatBox.innerHTML.includes("Hola, soy el chatbot de UESVALLE")) {
      chatBox.innerHTML += mensajeBienvenida;
    }
  }
}


async function sendMessage() {
  const input = document.getElementById("userInput");
  const chatBox = document.getElementById("chatBox");
  const text = input.value.trim();
  if (!text) return;

  chatBox.innerHTML += `<div class="mensaje user">${text}</div>`;
  input.value = "";

  const res = await fetch(`/preguntar?q=${encodeURIComponent(text)}`);
  const data = await res.json();

  chatBox.innerHTML += `<div class="mensaje bot">${data.respuesta}</div>`;
  chatBox.scrollTop = chatBox.scrollHeight;
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

