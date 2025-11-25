# Integración del Chatbot UESVALLE vía iframe

Este documento provee el snippet oficial para insertar el chatbot (Hugging Face Space) en páginas del portal UESVALLE.

## Snippet recomendado
Usa sandbox para reducir superficie, carga diferida y política estricta de referrer.

```html
<iframe
  src="https://jnarvaez712-uesvalle-chatbot.hf.space/widget"
  title="Chatbot UESVALLE"
  style="border:0;width:100%;max-width:850px;height:450px;"
  loading="lazy"
  referrerpolicy="strict-origin-when-cross-origin"
  sandbox="allow-scripts allow-same-origin"
></iframe>
```

## Variante con acceso al portapapeles
Agregar si en el futuro se habilitan botones de copiar.

```html
<iframe
  src="https://jnarvaez712-uesvalle-chatbot.hf.space/widget"
  title="Chatbot UESVALLE"
  style="border:0;width:100%;max-width:850px;height:450px;"
  loading="lazy"
  referrerpolicy="strict-origin-when-cross-origin"
  sandbox="allow-scripts allow-same-origin allow-clipboard-write"
></iframe>
```

## Variante con contenedor centrado
Para layouts que necesitan ancho fijo y posible ajuste dinámico de altura.

```html
<div style="max-width:850px;margin:0 auto;">
  <iframe
    id="chatbot-frame"
    src="https://jnarvaez712-uesvalle-chatbot.hf.space/widget"
    title="Chatbot UESVALLE"
    style="border:0;width:100%;height:450px;"
    loading="lazy"
    referrerpolicy="strict-origin-when-cross-origin"
    sandbox="allow-scripts allow-same-origin"
  ></iframe>
</div>
```

Si el contenido del widget cambia dinámicamente y se implementa `postMessage`, se podría ajustar la altura:

```html
<script>
window.addEventListener("message", (e) => {
  if (e.origin === "https://jnarvaez712-uesvalle-chatbot.hf.space" && e.data?.height) {
    document.getElementById("chatbot-frame").style.height = e.data.height + "px";
  }
});
</script>
```

## Recomendaciones de Seguridad
- Restringir CORS en la API a dominios oficiales del portal cuando esté en producción.
- Mantener `sandbox` sin `allow-top-navigation` ni `allow-popups` para prevenir escapes.
- Evitar incluir tokens secretos en el iframe; para autenticación futura considerar integración directa vía JS y endpoints privados.

## Integración sin iframe (futuro)
El proyecto contiene assets en `webchat/static/`. Se podría exponer un paquete JS para inyectar el widget directamente y así compartir estilos del portal. No implementado aún.

---
Documento generado automáticamente. Actualizar si cambia la URL base del Space.
