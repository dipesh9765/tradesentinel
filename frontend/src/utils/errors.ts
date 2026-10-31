/** Extracts a human-readable message from an unknown thrown value. */
export function errorMessage(err: unknown, fallback = "Unexpected error"): string {
    if (err instanceof Error && err.message) return err.message;
    if (typeof err === "string" && err) return err;
    return fallback;
}
