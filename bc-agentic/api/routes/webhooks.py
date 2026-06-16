import hashlib
import hmac
import json
from fastapi import APIRouter, Request, HTTPException, Header
from typing import Optional

from api.settings import settings

router = APIRouter()


def verify_github_signature(payload: bytes, signature: str, secret: str) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None),
    x_github_event: Optional[str] = Header(None),
):
    payload = await request.body()

    if settings.GITHUB_WEBHOOK_SECRET:
        if not x_hub_signature_256:
            raise HTTPException(status_code=401, detail="Missing signature")
        if not verify_github_signature(payload, x_hub_signature_256, settings.GITHUB_WEBHOOK_SECRET):
            raise HTTPException(status_code=401, detail="Invalid signature")

    data = json.loads(payload)

    if x_github_event == "issues":
        action = data.get("action")
        issue = data.get("issue", {})
        labels = [l["name"] for l in issue.get("labels", [])]

        if action == "labeled" and "bc-agent" in labels:
            from api.worker import create_task_from_issue
            create_task_from_issue.delay(
                issue_number=issue["number"],
                title=issue["title"],
                body=issue.get("body", ""),
                repo_url=data["repository"]["html_url"],
                repo_full_name=data["repository"]["full_name"],
            )

    return {"status": "ok"}


@router.post("/gitlab")
async def gitlab_webhook(
    request: Request,
    x_gitlab_token: Optional[str] = Header(None),
):
    if settings.GITLAB_WEBHOOK_SECRET:
        if x_gitlab_token != settings.GITLAB_WEBHOOK_SECRET:
            raise HTTPException(status_code=401, detail="Invalid token")

    data = await request.json()
    event_type = data.get("object_kind")

    if event_type == "issue":
        attrs = data.get("object_attributes", {})
        labels = [l["title"] for l in data.get("labels", [])]

        if "bc-agent" in labels and attrs.get("action") == "update":
            from api.worker import create_task_from_issue
            project = data.get("project", {})
            create_task_from_issue.delay(
                issue_number=attrs["iid"],
                title=attrs["title"],
                body=attrs.get("description", ""),
                repo_url=project.get("web_url", ""),
                repo_full_name=project.get("path_with_namespace", ""),
            )

    return {"status": "ok"}
