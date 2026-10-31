import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { KiteSetupBanner } from "./KiteSetupBanner";

describe("KiteSetupBanner", () => {
    it("explains the requirement and exposes an alert role", () => {
        render(<KiteSetupBanner onConfigure={() => {}} />);
        expect(screen.getByRole("alert")).toHaveTextContent("Zerodha Kite Connect Setup Required");
    });

    it("calls onConfigure when the button is pressed", async () => {
        const onConfigure = vi.fn();
        render(<KiteSetupBanner onConfigure={onConfigure} />);
        await userEvent.click(screen.getByRole("button", { name: /configure kite credentials/i }));
        expect(onConfigure).toHaveBeenCalledTimes(1);
    });
});
