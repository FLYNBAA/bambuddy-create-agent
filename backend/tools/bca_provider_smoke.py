"""Explicit BCA provider smoke runner.

Runs no paid operation unless the operator supplies --confirm-paid. The running
BCA server supplies credentials from its initial environment values or Agent
Services plaintext configuration; this client never reads .env files or prints
credential values.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

import httpx


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--api-key", default=os.environ.get("BCA_SMOKE_API_KEY", ""))
    parser.add_argument("--token", default=os.environ.get("BCA_SMOKE_BEARER_TOKEN", ""))
    parser.add_argument("--confirm-paid", action="store_true")
    args = parser.parse_args()

    headers = {"Authorization": f"Bearer {args.token}"} if args.token else {"X-API-Key": args.api_key} if args.api_key else {}
    base = args.base_url.rstrip("/") + "/api/v1/creator"
    async with httpx.AsyncClient(timeout=30, headers=headers) as client:
        config = await client.get(f"{base}/config")
        config.raise_for_status()
        configured = config.json().get("configured", {})
        print("Provider configuration:", configured)
        if not args.confirm_paid:
            print("No paid provider call was made. Re-run with --confirm-paid only after approving billed image generation.")
            return 0
        if not all(configured.get(key) for key in ("deepseek", "image")):
            print("DeepSeek and Image provider configuration are required for the paid image smoke.", file=sys.stderr)
            return 2
        created = await client.post(f"{base}/sessions")
        created.raise_for_status()
        session_id = created.json()["session_id"]
        try:
            prepared = await client.post(
                f"{base}/sessions/{session_id}/prepare",
                files={"message": (None, "主体：英短猫；风格：Q版；作品类型：桌面摆件")},
            )
            prepared.raise_for_status()
            if prepared.json().get("status") != "ready_for_images":
                print("Preparation did not produce a complete creative brief.", file=sys.stderr)
                return 3
            submitted = await client.post(f"{base}/sessions/{session_id}/images/generate")
            submitted.raise_for_status()
            print(f"Direct four-image generation accepted for session {session_id}.")
            return 0
        finally:
            # Do not delete a queued/running billed session: its persisted record is
            # evidence for the operator to inspect in the BCA card workflow.
            pass


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
