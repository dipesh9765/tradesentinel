import { describe, expect, it } from "vitest";
import { errorMessage } from "./errors";

describe("errorMessage", () => {
    it("reads the message of an Error", () => {
        expect(errorMessage(new Error("boom"))).toBe("boom");
    });

    it("passes strings through", () => {
        expect(errorMessage("plain failure")).toBe("plain failure");
    });

    it("falls back for unknown values and empty messages", () => {
        expect(errorMessage(undefined)).toBe("Unexpected error");
        expect(errorMessage({ code: 1 }, "custom")).toBe("custom");
        expect(errorMessage(new Error(""), "fallback")).toBe("fallback");
    });
});
