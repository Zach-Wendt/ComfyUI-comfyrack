"""comfyrack: read-only HTTP routes for comfyrack / Superflow fleets.

The pack registers two GET routes on ComfyUI's own route table, which ComfyUI
mirrors under /api for us:

    GET /comfyrack/info      -> ComfyUI version, devices, queue, packs, models
    GET /comfyrack/outputs   -> newest-first listing of the output directory

and one route for the "Share this ComfyUI on my tailnet" setting (this machine only):

    GET|POST /comfyrack/share -> tailscale serve status, or switch it on/off

It defines no nodes and patches nothing inside ComfyUI, so the node mappings
below are deliberately empty.
"""

import asyncio
import logging

try:  # ComfyUI loads this file as a package, so the helpers are its children...
    from .comfyrack_pack.info import collect_info
    from .comfyrack_pack import share
    from .comfyrack_pack.listing import DEFAULT_LIMIT, list_outputs
except ImportError:  # ...whereas pytest imports it as a bare module.
    from comfyrack_pack.info import collect_info
    from comfyrack_pack import share
    from comfyrack_pack.listing import DEFAULT_LIMIT, list_outputs

try:
    from aiohttp import web
    from server import PromptServer

    import folder_paths
except ImportError:
    # Imported outside ComfyUI: the helpers above stay usable, the routes do not exist.
    logging.getLogger(__name__).debug("comfyrack: ComfyUI server not importable, routes not registered")
    folder_paths = None
    web = None
    PromptServer = None
else:
    routes = PromptServer.instance.routes

    @routes.get("/comfyrack/info")
    async def comfyrack_info(request):
        # Collected inline, like ComfyUI's own /system_stats and /models/{folder}:
        # the torch calls must stay on the thread that owns the CUDA context.
        return web.json_response(collect_info())

    @routes.get("/comfyrack/outputs")
    async def comfyrack_outputs(request):
        query = request.rel_url.query
        try:
            limit = int(query.get("limit", DEFAULT_LIMIT))
            offset = int(query.get("offset", 0))
        except ValueError:
            return web.json_response({"error": "limit and offset must be integers"}, status=400)

        try:
            # The walk is synchronous and can touch thousands of entries.
            listing = await asyncio.to_thread(
                list_outputs, folder_paths.get_output_directory(), query.get("subfolder", ""), limit, offset
            )
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.json_response(listing)

    @routes.get("/comfyrack/share")
    @routes.post("/comfyrack/share")
    async def comfyrack_share(request):
        # GET reads, POST {"enabled": bool} switches. Loopback browsers only: this route runs a command.
        if not share.is_local_request(request.remote, request.headers):
            return web.json_response({"ok": False, "error": "this route is for this machine only"}, status=403)
        port = request.url.port or 8188
        try:
            if request.method == "GET":
                result = await asyncio.to_thread(share.status, port)
            else:
                enabled = bool((await request.json()).get("enabled"))
                result = await asyncio.to_thread(share.enable if enabled else share.disable, port)
        except share.ShareError as exc:
            return web.json_response({"ok": False, "error": str(exc), "fix": exc.fix})
        except ValueError:
            return web.json_response({"ok": False, "error": "body must be JSON"}, status=400)
        return web.json_response({"ok": True, **result})


WEB_DIRECTORY = "./web"
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
