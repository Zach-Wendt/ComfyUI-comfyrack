import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const ID = "comfyrack.ShareOnTailnet";
let syncing = false;

function toast(severity, summary, detail) {
  app.extensionManager.toast.add({ severity, summary, detail, life: 8000 });
}

async function call(enabled) {
  const res = await api.fetchApi("/comfyrack/share", {
    method: enabled === undefined ? "GET" : "POST",
    body: enabled === undefined ? undefined : JSON.stringify({ enabled }),
  });
  return res.json();
}

function set(value) {
  syncing = true;
  app.ui.settings.setSettingValue(ID, value);
  syncing = false;
}

app.registerExtension({
  name: "comfyrack.share",
  settings: [
    {
      id: ID,
      name: "Share this ComfyUI on my tailnet",
      type: "boolean",
      defaultValue: false,
      tooltip: "Runs `tailscale serve` for this ComfyUI so your other machines on your tailnet can reach it.",
      async onChange(value, old) {
        if (syncing || old === undefined) return;
        const r = await call(value);
        if (r.ok) {
          toast("success", value ? "Shared on your tailnet" : "No longer shared", r.url);
        } else {
          toast("error", r.error, r.fix);
          set(!value);
        }
      },
    },
  ],
  async setup() {
    // The stored switch can drift from what Tailscale actually serves: show the real state.
    const r = await call();
    if (r.ok) set(r.shared);
  },
});
