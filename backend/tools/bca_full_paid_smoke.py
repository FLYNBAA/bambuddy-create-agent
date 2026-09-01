"""Explicit billed end-to-end smoke runner for the direct BCA card workflow.

No Provider call is made unless the operator supplies ``--confirm-paid`` for
this invocation. The client reads no dotenv file and never prints credentials.
A supplied ``--session-id`` resumes calibration/analysis without repeating the
Image2 or Hunyuan stages.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time

import httpx


async def wait_for(client: httpx.AsyncClient, path: str, predicate, timeout: int) -> dict:
    deadline = time.monotonic() + timeout
    last: dict | None = None
    while time.monotonic() < deadline:
        response = await client.get(path)
        response.raise_for_status()
        last = response.json()
        if predicate(last):
            return last
        await asyncio.sleep(3)
    raise TimeoutError(f"Timed out waiting for {path}; last status={last.get('status') if last else 'unknown'}")


async def seed_smoke_spool(client: httpx.AsyncClient, root: str) -> int:
    response = await client.post(
        f"{root}/inventory/spools",
        json={
            "material": "PLA",
            "subtype": "Basic",
            "color_name": "BCA Smoke White",
            "rgba": "FFFFFFFF",
            "brand": "BCA Smoke",
            "label_weight": 1000,
            "core_weight": 250,
        },
    )
    response.raise_for_status()
    return int(response.json()["id"])


async def run_post_model(
    client: httpx.AsyncClient,
    root: str,
    base: str,
    session_id: str,
    args: argparse.Namespace,
) -> None:
    spool_id: int | None = None
    try:
        if args.seed_calibration_spool:
            spool_id = await seed_smoke_spool(client, root)
        mode = "multicolor" if args.seed_calibration_spool else "white"
        max_colors = 4 if mode == "multicolor" else 1

        current_response = await client.get(f"{base}/sessions/{session_id}")
        current_response.raise_for_status()
        current = current_response.json()
        if current["color_calibration"]["status"] != "succeeded":
            submitted = await client.post(
                f"{base}/sessions/{session_id}/print/calibrate",
                json={"mode": mode, "max_colors": max_colors},
            )
            submitted.raise_for_status()
            current = await wait_for(
                client,
                f"{base}/sessions/{session_id}",
                lambda body: body["color_calibration"]["status"] in {"succeeded", "failed"},
                args.print_timeout,
            )
        if current["color_calibration"]["status"] != "succeeded":
            raise RuntimeError(f"Print calibration failed: {current['color_calibration'].get('error')}")

        if current["print_analysis"]["status"] != "succeeded":
            submitted = await client.post(f"{base}/sessions/{session_id}/print/analyze")
            submitted.raise_for_status()
            current = await wait_for(
                client,
                f"{base}/sessions/{session_id}",
                lambda body: body["print_analysis"]["status"] in {"succeeded", "failed"},
                args.print_timeout,
            )
        if current["print_analysis"]["status"] != "succeeded":
            raise RuntimeError(f"Print analysis failed: {current['print_analysis'].get('error')}")
        if not isinstance(current["print_analysis"].get("score"), int):
            raise RuntimeError("Print analysis did not return a DeepSeek score")

        task_list = await client.get(f"{root}/bca-tasks")
        task_list.raise_for_status()
        existing = next(
            (task for task in task_list.json() if task.get("session_id") == session_id),
            None,
        )
        if existing is None:
            task = await client.post(
                f"{base}/sessions/{session_id}/task",
                json={
                    "customer_name": "BCA Smoke Customer",
                    "phone": "00000000000",
                    "address": "BCA smoke-test address",
                    "notes": "Automated billed end-to-end smoke",
                },
            )
            task.raise_for_status()
            if not task.json().get("task_id"):
                raise RuntimeError("Order submission did not create a task")
    finally:
        if spool_id is not None:
            removed = await client.delete(f"{root}/inventory/spools/{spool_id}")
            removed.raise_for_status()


async def run_full_chain(
    client: httpx.AsyncClient,
    root: str,
    base: str,
    args: argparse.Namespace,
) -> int:
    created = await client.post(f"{base}/sessions")
    created.raise_for_status()
    session_id = created.json()["session_id"]
    try:
        prepared = await client.post(
            f"{base}/sessions/{session_id}/prepare",
            files={"message": (None, "主体：英短猫；风格：Q版；作品类型：桌面摆件；要求：纯色、白色背景、适合打印")},
        )
        prepared.raise_for_status()
        if prepared.json().get("status") != "ready_for_images":
            raise RuntimeError("Preparation did not produce a complete creative brief")

        submitted = await client.post(f"{base}/sessions/{session_id}/images/generate")
        submitted.raise_for_status()
        images = await wait_for(
            client,
            f"{base}/sessions/{session_id}",
            lambda body: body["status"] in {"awaiting_image_selection", "failed"},
            args.image_timeout,
        )
        if images["status"] == "failed" or len(images.get("generated_images", [])) != 4:
            raise RuntimeError(f"Style-image stage failed: {images.get('error')}")

        submitted = await client.post(
            f"{base}/sessions/{session_id}/model/generate",
            json={"image_index": 0},
        )
        submitted.raise_for_status()
        model = await wait_for(
            client,
            f"{base}/sessions/{session_id}",
            lambda body: body["status"] in {"completed", "failed"},
            args.model_timeout,
        )
        if model["status"] == "failed" or not model.get("model_download_url"):
            raise RuntimeError(f"3D concept stage failed: {model.get('error')}")

        await run_post_model(client, root, base, session_id, args)
        print(f"BCA direct paid chain and order submission succeeded for session {session_id}.")
        return 0
    except Exception:
        print(
            f"Inspect session {session_id}; use --session-id {session_id} --confirm-paid to resume after the GLB stage.",
            file=sys.stderr,
        )
        raise


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--api-key", default=os.environ.get("BCA_SMOKE_API_KEY", ""))
    parser.add_argument("--token", default=os.environ.get("BCA_SMOKE_BEARER_TOKEN", ""))
    parser.add_argument("--confirm-paid", action="store_true")
    parser.add_argument("--session-id", help="Resume calibration and analysis for an existing completed GLB session.")
    parser.add_argument("--seed-calibration-spool", action="store_true")
    parser.add_argument("--image-timeout", type=int, default=300)
    parser.add_argument("--model-timeout", type=int, default=960)
    parser.add_argument("--print-timeout", type=int, default=960)
    args = parser.parse_args()
    if not args.confirm_paid:
        print("Refusing billed Provider calls. Re-run with --confirm-paid only after approving this invocation's charges.")
        return 2

    headers = {"Authorization": f"Bearer {args.token}"} if args.token else {"X-API-Key": args.api_key} if args.api_key else {}
    root = args.base_url.rstrip("/") + "/api/v1"
    base = root + "/creator"
    async with httpx.AsyncClient(timeout=45, headers=headers) as client:
        config = await client.get(f"{base}/config")
        config.raise_for_status()
        configured = config.json().get("configured", {})
        required = ("deepseek", "meshy") if args.session_id else ("deepseek", "image", "hunyuan", "meshy")
        if not all(configured.get(name) for name in required):
            print(f"Missing Provider configuration: {configured}", file=sys.stderr)
            return 3
        if args.session_id:
            await run_post_model(client, root, base, args.session_id, args)
            print(f"BCA calibration, analysis, and order submission succeeded for session {args.session_id}.")
            return 0
        return await run_full_chain(client, root, base, args)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
