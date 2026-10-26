import { describe, expect, it } from "vitest";
import { extractRequestToken } from "./api";

describe("extractRequestToken", () => {
    it("returns a bare token unchanged", () => {
        expect(extractRequestToken("  abc123  ")).toBe("abc123");
    });

    it("pulls the token out of a full redirect URL", () => {
        const url = "http://127.0.0.1:5173/?request_token=AbC_12-3&action=login&status=success";
        expect(extractRequestToken(url)).toBe("AbC_12-3");
    });

    it("pulls the token out of a pasted query string", () => {
        expect(extractRequestToken("action=login&request_token=xyz789")).toBe("xyz789");
    });

    it("handles empty input", () => {
        expect(extractRequestToken("")).toBe("");
    });
});
