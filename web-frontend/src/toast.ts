// A tiny toast helper reusing the server-rendered #toast element.

let timer: number | null = null;

export function showToast(message: string, persistent = false): HTMLElement | null {
  const toast = document.getElementById("toast");
  if (!toast) return null;
  toast.textContent = message;
  toast.classList.add("toast-show");
  if (timer !== null) window.clearTimeout(timer);
  toast.style.cursor = "default";
  toast.onclick = null;
  if (!persistent) {
    timer = window.setTimeout(() => toast.classList.remove("toast-show"), 2500);
  }
  return toast;
}
