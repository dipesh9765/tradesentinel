// Browser Native Web Notifications API Service (Windows / Desktop OS Notifications)

class NotificationManager {
  isSupported(): boolean {
    return typeof window !== "undefined" && "Notification" in window;
  }

  getPermission(): NotificationPermission {
    if (this.isSupported()) {
      return Notification.permission;
    }
    return "denied";
  }

  async requestPermission(): Promise<boolean> {
    if (!this.isSupported()) return false;
    try {
      const result = await Notification.requestPermission();
      return result === "granted";
    } catch (e) {
      console.warn("Error requesting notification permission:", e);
      return false;
    }
  }

  sendNotification(title: string, options?: { body?: string; tag?: string }, onClick?: () => void) {
    if (!this.isSupported()) return;

    if (Notification.permission === "granted") {
      this._createNotification(title, options, onClick);
    } else if (Notification.permission !== "denied") {
      Notification.requestPermission().then((permission) => {
        if (permission === "granted") {
          this._createNotification(title, options, onClick);
        }
      });
    }
  }

  private _createNotification(
    title: string,
    options?: { body?: string; tag?: string },
    onClick?: () => void
  ) {
    try {
      const notification = new Notification(title, {
        body: options?.body,
        tag: options?.tag || "tradesentinel-alert",
        icon: "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%2300f0ff'><path d='M13 2L3 14h9l-1 8 10-12h-9l1-8z'/></svg>",
        silent: false
      });

      notification.onclick = () => {
        window.focus();
        notification.close();
        if (onClick) onClick();
      };
    } catch (e) {
      console.warn("Could not display notification:", e);
    }
  }

  notifyTradeProposal(proposal: {
    symbol: string;
    instrument: string;
    signal_type: string;
    entry_price: number;
    stop_loss: number;
    target_1: number;
    risk_reward: string;
    confidence: number;
  }) {
    const action = proposal.signal_type.replace("_", " ");
    const title = `🚨 TradeSentinel: ${action} on ${proposal.instrument}`;
    const body = `Entry: ₹${proposal.entry_price} | SL: ₹${proposal.stop_loss} | Target: ₹${proposal.target_1} (R:R ${proposal.risk_reward} • Conf: ${proposal.confidence}%)\nClick to approve on dashboard.`;

    this.sendNotification(title, { body, tag: `proposal-${proposal.instrument}` });
  }

  notifyTradeExecuted(instrument: string, qty: number, price: number) {
    const title = `✅ Order Executed: ${instrument}`;
    const body = `Filled ${qty} Lot @ ₹${price}. Position is now monitored with Stop-Loss & Target.`;
    this.sendNotification(title, { body, tag: `executed-${instrument}` });
  }
}

export const notificationManager = new NotificationManager();
