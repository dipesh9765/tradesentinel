/** Thin wrapper over blocking browser dialogs so UI logic stays testable. */
export function showAlert(message: string): void {
    window.alert(message);
}
