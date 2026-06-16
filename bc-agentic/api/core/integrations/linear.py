import httpx
from api.settings import settings

LINEAR_API_URL = "https://api.linear.app/graphql"


async def get_issues(team_id: str, label: str = "bc-agent") -> list[dict]:
    """Fetch Linear issues with a specific label."""
    query = """
    query Issues($teamId: String!, $filter: IssueFilter) {
      issues(filter: $filter) {
        nodes {
          id
          title
          description
          url
          team { id name }
          labels { nodes { name } }
        }
      }
    }
    """
    variables = {
        "teamId": team_id,
        "filter": {
            "team": {"id": {"eq": team_id}},
            "labels": {"name": {"eq": label}},
        },
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            LINEAR_API_URL,
            json={"query": query, "variables": variables},
            headers={"Authorization": settings.LINEAR_API_KEY or ""},
        )
        data = response.json()

    return data.get("data", {}).get("issues", {}).get("nodes", [])


async def update_issue_status(issue_id: str, state_id: str) -> dict:
    """Update an issue's state in Linear."""
    mutation = """
    mutation UpdateIssue($id: String!, $stateId: String!) {
      issueUpdate(id: $id, input: { stateId: $stateId }) {
        success
        issue { id title }
      }
    }
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            LINEAR_API_URL,
            json={"query": mutation, "variables": {"id": issue_id, "stateId": state_id}},
            headers={"Authorization": settings.LINEAR_API_KEY or ""},
        )
        return response.json()


async def comment_on_issue(issue_id: str, body: str) -> dict:
    """Post a comment on a Linear issue."""
    mutation = """
    mutation CreateComment($issueId: String!, $body: String!) {
      commentCreate(input: { issueId: $issueId, body: $body }) {
        success
        comment { id }
      }
    }
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            LINEAR_API_URL,
            json={"query": mutation, "variables": {"issueId": issue_id, "body": body}},
            headers={"Authorization": settings.LINEAR_API_KEY or ""},
        )
        return response.json()
