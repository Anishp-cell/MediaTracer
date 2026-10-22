"""End-to-end API tests with the real model: upload → index → search → preview/original → persistence."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

pytestmark = pytest.mark.model


def wait_job(client: TestClient, job_id: str, timeout: float = 600) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["status"] not in ("queued", "running"):
            return j
        time.sleep(0.3)
    raise TimeoutError(job_id)


def upload(client: TestClient, *paths) -> dict:
    files = [("files", (p.name, p.read_bytes())) for p in paths]
    r = client.post("/api/index", files=files)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def client(settings, model):
    with TestClient(create_app(settings, model=model)) as c:
        yield c


def test_health_and_capabilities(client):
    h = client.get("/api/health").json()
    assert h["model"]["state"] == "ready" and h["model"]["embedding_dim"] == 768
    caps = client.get("/api/capabilities").json()
    enabled = {e for a in caps["adapters"] if a["enabled"] for e in a["formats"]}
    assert {".jpg", ".png", ".pdf", ".mp4", ".wav", ".docx", ".pptx", ".csv", ".xlsx", ".md"} <= enabled


def test_empty_collection_and_validation(client):
    r = client.post("/api/search", json={"query": "anything"})
    assert r.status_code == 200
    body = r.json()
    assert body["results"] == [] and "empty" in body["notice"].lower()
    assert client.post("/api/search", json={"query": ""}).status_code == 422
    assert client.post("/api/search", json={"query": "x", "families": ["bogus"]}).status_code == 422


def test_rejects_unsupported_and_bad_files(client, tmp_path, samples):
    bad = tmp_path / "malware.exe"
    bad.write_bytes(b"MZ....")
    res = upload(client, bad, samples["empty_txt"])
    actions = {f["filename"]: f["action"] for f in res["files"]}
    assert actions == {"malware.exe": "rejected", "empty.txt": "rejected"}
    assert res["job_id"] is None
    # Corrupt content with a valid extension is accepted, then fails with a clear error.
    res = upload(client, samples["corrupt_pdf"])
    job = wait_job(client, res["job_id"])
    assert job["failed"] == 1 and job["errors"][0]["error"]
    f = client.get(f"/api/files/{res['files'][0]['file_id']}").json()
    assert f["status"] == "failed" and f["error"]


def test_full_journey_and_persistence(settings, model, samples):
    with TestClient(create_app(settings, model=model)) as c:
        res = upload(c, samples["pdf"], samples["png"], samples["csv"], samples["video"])
        job = wait_job(c, res["job_id"])
        assert job["status"] == "completed" and job["done"] == 4, job

        # PDF diagram query → page 2 rendered image, with an openable page URL.
        r = c.post("/api/search", json={"query": "diagram of a convolutional neural network", "families": ["document"]}).json()
        top = r["results"][0]
        assert top["filename"] == "paper.pdf" and top["locator"]["page"] == 2
        assert top["open_url"].endswith("#page=2")
        assert c.get(top["preview_url"]).headers["content-type"] == "image/jpeg"
        orig = c.get(top["original_url"])
        assert orig.status_code == 200 and orig.content[:5] == b"%PDF-"

        # Image query → the red circle image.
        r = c.post("/api/search", json={"query": "a red circle", "families": ["image"]}).json()
        assert r["results"][0]["filename"] == "red_circle.png"
        assert 0 < r["results"][0]["relative"] <= 1

        # Video query → frame inside the blue scene (8–12 s), and range-capable streaming.
        r = c.post("/api/search", json={"query": "a completely blue screen", "families": ["video"]}).json()
        frame = next(x for x in r["results"] if x["kind"] == "frame")
        assert 8.0 <= frame["locator"]["time"] < 12.0
        s = c.get(f"/api/files/{frame['file_id']}/stream", headers={"Range": "bytes=0-99"})
        assert s.status_code == 206 and len(s.content) == 100
        ref = c.post(f"/api/items/{frame['item_id']}/refine", json={"query": "a completely blue screen"}).json()
        assert 7.0 <= ref["best_time"] <= 12.0

        # Spreadsheet text query → csv rows with cell references.
        r = c.post("/api/search", json={"query": "units of Item 20", "families": ["spreadsheet"], "mode": "hybrid"}).json()
        assert r["results"][0]["locator"]["cell_range"].startswith("A")

        # Same content again → duplicate, no new job.
        again = upload(c, samples["png"])
        assert again["files"][0]["action"] == "duplicate" and again["job_id"] is None
        n_items = c.get("/api/health").json()["indexed_items"]

    # Restart: a new app over the same data dir searches immediately without re-indexing.
    with TestClient(create_app(settings, model=model)) as c2:
        h = c2.get("/api/health").json()
        assert h["indexed_files"] == 4 and h["indexed_items"] == n_items
        assert c2.get("/api/jobs").json()[0]["status"] == "completed"
        r = c2.post("/api/search", json={"query": "a red circle"}).json()
        assert r["results"][0]["filename"] == "red_circle.png"

        # Remove from index: results disappear; the upload copy is kept unless requested.
        fid = r["results"][0]["file_id"]
        stored = settings.uploads_dir / f"{fid}.png"
        assert c2.delete(f"/api/files/{fid}").json()["removed"]
        assert stored.exists()
        r = c2.post("/api/search", json={"query": "a red circle", "families": ["image"]}).json()
        assert all(x["file_id"] != fid for x in r["results"])
        assert c2.get(f"/api/files/{fid}").status_code == 404


def test_changed_upload_is_reindexed(client, tmp_path):
    p = tmp_path / "note.txt"
    p.write_text("The meeting is about gardening and tomatoes.", encoding="utf-8")
    first = upload(client, p)
    wait_job(client, first["job_id"])
    p.write_text("The meeting is about rockets and orbital mechanics.", encoding="utf-8")
    second = upload(client, p)
    assert second["files"][0]["action"] == "updated"
    assert second["files"][0]["file_id"] == first["files"][0]["file_id"]
    wait_job(client, second["job_id"])
    r = client.post("/api/search", json={"query": "space launch", "mode": "hybrid"}).json()
    assert "rockets" in r["results"][0]["text"]


def test_local_folder_index_and_rescan(client, tmp_path):
    folder = tmp_path / "docs"
    folder.mkdir()
    (folder / "a.md").write_text("# Recipes\n\nLentil soup with cumin.", encoding="utf-8")
    (folder / ".cache").mkdir()
    (folder / ".cache" / "hidden.md").write_text("# Hidden cache file", encoding="utf-8")
    res = client.post("/api/index/local", json={"paths": [str(folder)]}).json()
    assert [f["filename"] for f in res["files"]] == ["a.md"]  # hidden folders are skipped
    wait_job(client, res["job_id"])
    missing = client.post("/api/index/local", json={"paths": [str(tmp_path / "nope")]}).json()
    assert missing["files"][0]["action"] == "rejected" and missing["job_id"] is None
    res = client.post("/api/files/rescan").json()
    assert [f["action"] for f in res["files"]] == ["unchanged"] and res["job_id"] is None
    time.sleep(0.05)
    (folder / "a.md").write_text("# Recipes\n\nChocolate cake with berries.", encoding="utf-8")
    res = client.post("/api/files/rescan").json()
    assert [f["action"] for f in res["files"]] == ["updated"]
    wait_job(client, res["job_id"])
    assert (folder / "a.md").exists()  # originals are never modified or deleted
