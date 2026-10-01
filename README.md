# ComfyUI-comfyrack

A thin ComfyUI custom-node pack for
[comfyrack](https://github.com/Zach-Wendt/comfyrack) / Superflow fleets.

It defines **no nodes**, patches nothing inside ComfyUI and adds no dependencies.
It contributes two read-only GET routes that a fleet controller can poll to answer
"is this machine alive, what does it have installed, and what has it produced?"

Routes registered on `PromptServer.instance.routes` are automatically mirrored by
ComfyUI under `/api`, so every route below is available at both paths.

## Install

Once the pack is in the Comfy registry, install it with ComfyUI-Manager:
open Manager, choose "Custom Nodes Manager", search for "comfyrack", click Install, then restart ComfyUI.

Until then, install it with git:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/Zach-Wendt/ComfyUI-comfyrack
# restart ComfyUI; the pack needs no requirements
```

The startup log shows a normal, empty import for the pack (`IMPORT FAILED` must
not appear). Nothing is added to the node graph.

## Setting: Share this ComfyUI on my tailnet

Settings has a switch, "Share this ComfyUI on my tailnet". It runs `tailscale serve` for ComfyUI's port, so
your other machines on your [Tailscale](https://tailscale.com/download) tailnet can reach it. It does the same
as `comfyrack share`: it checks Tailscale is signed in, checks ComfyUI answers, then starts the serve.
A toast shows the address, or the one-line fix. The switch is off until you turn it on.

The route behind it, `GET|POST /comfyrack/share`, runs a command, so it answers only a browser on the
same machine. Requests that arrive through the tailnet get 403.

## `GET /comfyrack/info`

Everything is read on the spot; nothing is cached, stored or written.

```json
{
  "pack_version": "0.1.0",
  "comfyui_version": "0.37.0",
  "hostname": "gpu-box",
  "devices": [
    { "name": "cuda:0", "vram_total": 25769803776, "vram_free": 8053063680 }
  ],
  "queue": { "running": 1, "pending": 2 },
  "custom_node_packs": [
    "ComfyUI-comfyrack",
    "PackA",
    "PackB",
    "single.py"
  ],
  "models": {
    "checkpoints": ["sdxl.safetensors"],
    "loras": ["detail-tweaker.safetensors"]
  }
}
```

* `devices` — the torch device ComfyUI will run on, with total and free memory in
  bytes (`vram_total` is the device capacity, not the torch reservation).
* `queue` — how many prompts are running and waiting.
* `custom_node_packs` — sorted entry names from `custom_nodes/`: directories plus
  single-file `*.py` packs. `__pycache__`, dot-entries, `*.disabled` and
  non-`.py` files are skipped.
* `models` — file names per `folder_paths` model folder, `/`-separated.
  `custom_nodes` is not a model folder and is not included.

Any sub-collection that cannot be read (no CUDA, an unreadable model folder, a
queue that is mid-shutdown) is reported as `null` and the route still answers
`200` with the rest, so a controller never has to special-case a partial machine.

## `GET /comfyrack/outputs`

Query parameters: `subfolder` (relative to the output directory, default `""`),
`limit` (default `200`, clamped to `1..1000`), `offset` (default `0`).

```json
{
  "files": [
    {
      "filename": "ComfyUI_00042_.png",
      "subfolder": "ComfyUI",
      "type": "output",
      "size": 1812345,
      "mtime": 1758000000.0
    }
  ],
  "total": 137,
  "offset": 0,
  "limit": 200
}
```

* Sorted newest `mtime` first; `total` counts every visible file under the
  subfolder, not the page, so paging is stable. Equal mtimes break ties by
  subfolder then file name.
* Hidden files and directories (leading `.`) are skipped; a subfolder that does
  not exist yields an empty page.
* `filename`, `subfolder` and `type` are exactly the three query parameters of
  ComfyUI's core `GET /view`, so any listed file is one URL away:

  ```
  /view?filename=ComfyUI_00042_.png&subfolder=ComfyUI&type=output
  ```

* The directory walk runs in a worker thread, so a large output tree never blocks
  ComfyUI's event loop.
* A `subfolder` that would escape the output directory (`..`, or an absolute
  path) and a non-integer `limit`/`offset` return `400` with
  `{"error": "<reason>"}`.

## Security

**ComfyUI has no authentication.** Both routes are unauthenticated GET endpoints,
and ComfyUI's own `/view` already serves any output file unauthenticated.

These routes add to that exposure:

* `/comfyrack/outputs` reveals output file names, subfolder layout, sizes and
  modification times — which is often enough to infer prompts, client names and
  job schedules.
* `/comfyrack/info` reveals the hostname, the ComfyUI version, GPU model and VRAM
  sizing, plus the full list of installed custom-node packs and installed model
  file names (useful reconnaissance: it tells an attacker exactly which
  vulnerabilities apply).

Treat both routes as public information. Run ComfyUI **only on localhost, a
private network, or a tailnet/VPN with ACLs** — never bound to a public
interface. If the port must be reachable from outside, put an authenticating
reverse proxy in front of it and allowlist the two paths for the fleet
controller only. The pack is read-only, so if you would rather not expose it at
all, simply do not install it: nothing in comfyrack or Superflow depends on
these routes existing.

## Development

```bash
python -m pytest -q     # tests/test_listing.py, no ComfyUI required
```

`comfyrack_pack/listing.py` imports nothing from ComfyUI, which is what makes the
walker unit-testable in a plain interpreter.

## Report a problem

Open an issue with the bug form at <https://github.com/Zach-Wendt/ComfyUI-comfyrack/issues/new/choose>.
Every field is required: the exact command or action, the full output, what you expected, the versions, and
your operating system. Pull requests are open to collaborators only.

## License

MIT
