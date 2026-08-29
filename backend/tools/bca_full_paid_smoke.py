"""Explicit billed BCA smoke runner with safe print-stage resumption.

The full path performs paid image, Hunyuan, and Meshy work only after the
operator passes --confirm-paid. When print analysis needs an issue
acknowledgment, resume the same completed session with --session-id rather than
starting another billed image/3D run.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time

import httpx


async def wait_for(client: httpx.AsyncClient, path: str, predicate, timeout: int):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        response = await client.get(path)
        response.raise_for_status()
        last = response.json()
        if predicate(last):
            return last
        await asyncio.sleep(3)
    raise TimeoutError(f"Timed out waiting for {path}; last status={last.get('status') if last else 'unknown'}")


def print_issue_acknowledgment_required(session: dict) -> bool:
    report = session["print_analysis"].get("report") or {}
    return report.get("status") != "healthy"


async def generate_print_file(client: httpx.AsyncClient, base: str, session_id: str, args) -> dict:
    session = await client.get(f"{base}/sessions/{session_id}")
    session.raise_for_status()
    current = session.json()
    if current["status"] != "completed":
        raise RuntimeError("Session must have a completed persisted GLB before print generation.")
    if current["print_analysis"]["status"] != "succeeded":
        raise RuntimeError("Print analysis must succeed before print generation.")
    if current["print_file"]["status"] != "not_started":
        raise RuntimeError("Print generation has already started or completed; do not resubmit a paid Meshy job.")

    requires_acknowledgment = print_issue_acknowledgment_required(current)
    if requires_acknowledgment and not args.acknowledge_print_issues:
        raise RuntimeError(
            "Print analysis is not healthy. Review its report, then continue this exact session with "
            f"--session-id {session_id} --confirm-paid --acknowledge-print-issues."
        )

    generated = await client.post(
        f"{base}/sessions/{session_id}/print/generate",
        json={"max_colors": 4, "acknowledge_issues": requires_acknowledgment},
    )
    generated.raise_for_status()
    printed = await wait_for(
        client,
        f"{base}/sessions/{session_id}",
        lambda body: body["print_file"]["status"] in {"succeeded", "failed"},
        args.print_timeout,
    )
    if printed["print_file"]["status"] == "failed":
        raise RuntimeError(f"Multi-color 3MF failed: {printed['print_file'].get('error')}")
    return printed


async def complete_post_print_steps(client: httpx.AsyncClient, root: str, base: str, session_id: str, args) -> None:
    current = (await client.get(f"{base}/sessions/{session_id}")).json()
    if current["geometry_status"] == "not_started":
        geometry = await client.post(f"{base}/sessions/{session_id}/print/geometry")
        geometry.raise_for_status()
        current = await wait_for(
            client,
            f"{base}/sessions/{session_id}",
            lambda body: body["geometry_status"] in {"succeeded", "failed"},
            120,
        )
    if current["geometry_status"] != "succeeded":
        raise RuntimeError("Geometry 3MF conversion failed")

    spool_id: int | None = None
    try:
        if not args.seed_calibration_spool:
            return
        calibration_status = current["color_calibration"]["status"]
        if calibration_status == "not_started":
            spool_response = await client.post(
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
            spool_response.raise_for_status()
            spool_id = spool_response.json()["id"]
            calibrated = await client.post(f"{base}/sessions/{session_id}/print/calibrate")
            calibrated.raise_for_status()
            current = await wait_for(
                client,
                f"{base}/sessions/{session_id}",
                lambda body: body["color_calibration"]["status"] in {"succeeded", "failed"},
                args.print_timeout,
            )
            calibration_status = current["color_calibration"]["status"]
        if calibration_status != "succeeded":
            raise RuntimeError(f"Color calibration failed: {current['color_calibration'].get('error')}")
        task_response = await client.post(f"{base}/sessions/{session_id}/task", json={"mode": "multicolor"})
        task_response.raise_for_status()
    finally:
        if spool_id is not None:
            removed = await client.delete(f"{root}/inventory/spools/{spool_id}")
            removed.raise_for_status()


async def run_full_chain(client: httpx.AsyncClient, root: str, base: str, args) -> int:
    session = await client.post(f"{base}/sessions")
    session.raise_for_status()
    session_id = session.json()["session_id"]
    try:
        prepared = await client.post(
            f"{base}/sessions/{session_id}/prepare",
            files={"message": (None, "主体：英短猫；风格：Q版；作品类型：桌面摆件；要求：纯色、白色背景、适合打印")},
        )
        prepared.raise_for_status()
        if prepared.json().get("status") != "awaiting_image_confirmation":
            raise RuntimeError("Preparation did not reach image confirmation")

        accepted = await client.post(f"{base}/sessions/{session_id}/confirm-image")
        accepted.raise_for_status()
        images = await wait_for(
            client,
            f"{base}/sessions/{session_id}",
            lambda body: body["status"] in {"awaiting_image_selection", "failed"},
            args.image_timeout,
        )
        if images["status"] == "failed":
            raise RuntimeError(f"Image stage failed: {images.get('error')}")
        if len(images["generated_images"]) != 4:
            raise RuntimeError("Image stage did not persist exactly four images")

        selected = await client.post(f"{base}/sessions/{session_id}/select-image", json={"image_index": 0})
        selected.raise_for_status()
        accepted = await client.post(f"{base}/sessions/{session_id}/confirm-3d")
        accepted.raise_for_status()
        model = await wait_for(
            client,
            f"{base}/sessions/{session_id}",
            lambda body: body["status"] in {"completed", "failed"},
            args.model_timeout,
        )
        if model["status"] == "failed":
            raise RuntimeError(f"3D stage failed: {model.get('error')}")

        analysis = await client.post(f"{base}/sessions/{session_id}/print/analyze")
        analysis.raise_for_status()
        analyzed = await wait_for(
            client,
            f"{base}/sessions/{session_id}",
            lambda body: body["print_analysis"]["status"] in {"succeeded", "failed"},
            args.print_timeout,
        )
        if analyzed["print_analysis"]["status"] == "failed":
            raise RuntimeError(f"Print analysis failed: {analyzed['print_analysis'].get('error')}")

        await generate_print_file(client, base, session_id, args)
        await complete_post_print_steps(client, root, base, session_id, args)
        print(f"BCA paid chain reached persisted GLB and 3MF artifacts for session {session_id}.")
        if args.seed_calibration_spool:
            print("Color calibration and calibrated-artifact task creation succeeded.")
        else:
            print("Color calibration requires --seed-calibration-spool or existing active Bambuddy inventory.")
        return 0
    except Exception:
        print(f"Inspect session {session_id}; use --session-id {session_id} only to resume print generation.", file=sys.stderr)
        raise


async def run_print_resume(client: httpx.AsyncClient, root: str, base: str, args) -> int:
    session_id = args.session_id
    await generate_print_file(client, base, session_id, args)
    await complete_post_print_steps(client, root, base, session_id, args)
    print(f"BCA print stage completed for existing session {session_id} without repeating image or 3D generation.")
    return 0


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--api-key", default=os.environ.get("BCA_SMOKE_API_KEY", ""))
    parser.add_argument("--confirm-paid", action="store_true")
    parser.add_argument("--acknowledge-print-issues", action="store_true")
    parser.add_argument("--session-id", help="Resume only the Meshy print stage for this existing completed session.")
    parser.add_argument("--seed-calibration-spool", action="store_true")
    parser.add_argument("--image-timeout", type=int, default=300)
    parser.add_argument("--model-timeout", type=int, default=960)
    parser.add_argument("--print-timeout", type=int, default=960)
    args = parser.parse_args()
    if not args.confirm_paid:
        print("Refusing paid chain. Re-run with --confirm-paid after approving the applicable provider charge.")
        return 2


    if args.acknowledge_print_issues and not args.session_id:
        parser.error("--acknowledge-print-issues is valid only with --session-id after reviewing that session's analysis.")
    headers = {"X-API-Key": args.api_key} if args.api_key else {}
    root = args.base_url.rstrip("/") + "/api/v1"
    base = root + "/creator"
    async with httpx.AsyncClient(timeout=45, headers=headers) as client:
        config = await client.get(f"{base}/config")
        config.raise_for_status()
        configured = config.json().get("configured", {})
        required = ("meshy", "deepseek") if args.session_id and args.seed_calibration_spool else ("meshy",) if args.session_id else ("deepseek", "image", "hunyuan", "meshy")
        if not all(configured.get(name) for name in required):
            print(f"Missing provider configuration: {configured}", file=sys.stderr)
            return 3
        if args.session_id:
            return await run_print_resume(client, root, base, args)
        return await run_full_chain(client, root, base, args)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
