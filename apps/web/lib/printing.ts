/**
 * Opens a sanitized PDF in a new tab and raises the browser's native print
 * dialog, which lists every printer actually connected to (or discoverable
 * from) the user's machine - USB, network, or virtual. This is the
 * standards-compliant way a web page can reach a real physical printer;
 * browsers do not expose printer enumeration to page JavaScript for
 * security reasons, so the native dialog is the correct integration point
 * rather than a custom picker.
 */
export function openAndPrint(url: string): void {
  const win = window.open(url, "_blank");
  if (!win) return; // popup blocked - the tab with the PDF is enough, user can print manually

  // Cross-origin windows only expose a handful of safe members (focus, close,
  // postMessage, print, location). We can't reliably detect when the native
  // PDF viewer has finished rendering, so we retry a couple of times.
  const tryPrint = () => {
    try {
      win.focus();
      win.print();
    } catch {
      // ignore - the viewer may not be ready yet, or the tab was closed
    }
  };
  setTimeout(tryPrint, 600);
  setTimeout(tryPrint, 1400);
}
