from __future__ import annotations

import hashlib

import pytest

from backend.app.services.creator_integration import CreatorController


@pytest.mark.asyncio
async def test_creator_artifact_download_preserves_large_3mf_body_at_app_boundary(
    async_client, monkeypatch, tmp_path
) -> None:
    """Guard FastAPI FileResponse byte integrity before the deployment proxy.

    The HTTPS/Nginx authentication path is a separate deployment acceptance
    check; this test only detects application-level truncation regressions.
    """
    import backend.app.services.creator_integration as integration
    from backend.app.main import app

    monkeypatch.setattr(integration.bambuddy_settings, "base_dir", tmp_path)
    controller = CreatorController()
    session = controller.agent.create_session()
    artifact = tmp_path / "bca-agent" / "print-files" / session.session_id / "print-calibrated.3mf"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    expected = b"3MF-STREAM-CHECK\n" * (5 * 1024 * 1024 // 17)
    artifact.write_bytes(expected)
    snapshot = controller.agent.get_session(session.session_id)
    snapshot.calibrated_print_file_path = str(artifact)
    controller.agent._repository.save(snapshot)

    previous = getattr(app.state, "bca_creator", None)
    app.state.bca_creator = controller
    try:
        response = await async_client.get(f"/api/v1/creator/sessions/{session.session_id}/calibrated-print-file")
    finally:
        if previous is None:
            delattr(app.state, "bca_creator")
        else:
            app.state.bca_creator = previous

    assert response.status_code == 200
    assert response.headers["content-length"] == str(len(expected))
    assert len(response.content) == len(expected)
    assert hashlib.sha256(response.content).hexdigest() == hashlib.sha256(expected).hexdigest()
