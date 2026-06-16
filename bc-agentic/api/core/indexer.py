import os
import hashlib
from pathlib import Path
from typing import Optional
import chromadb
from chromadb.config import Settings as ChromaSettings

from api.settings import settings as app_settings

SUPPORTED_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java",
    ".c", ".cpp", ".h", ".cs", ".rb", ".php", ".swift", ".kt",
}

MAX_CHUNK_SIZE = 1500  # characters


def get_chroma_client() -> chromadb.HttpClient:
    return chromadb.HttpClient(
        host=app_settings.CHROMA_HOST,
        port=app_settings.CHROMA_PORT,
    )


def _chunk_file(file_path: str, content: str) -> list[dict]:
    """Split file into chunks at function/class boundaries when possible."""
    lines = content.split("\n")
    chunks = []
    current_chunk_lines = []
    current_start = 0

    for i, line in enumerate(lines):
        # Break at function/class boundaries in Python
        is_boundary = (
            line.startswith("def ") or
            line.startswith("class ") or
            line.startswith("async def ") or
            line.startswith("function ") or
            line.startswith("export function ") or
            line.startswith("export default ") or
            line.startswith("export class ")
        )

        if is_boundary and current_chunk_lines and len("\n".join(current_chunk_lines)) > MAX_CHUNK_SIZE // 2:
            chunks.append({
                "file": file_path,
                "start_line": current_start,
                "end_line": i - 1,
                "content": "\n".join(current_chunk_lines),
            })
            current_chunk_lines = [line]
            current_start = i
        else:
            current_chunk_lines.append(line)

        # Also split very long chunks
        if len("\n".join(current_chunk_lines)) > MAX_CHUNK_SIZE:
            chunks.append({
                "file": file_path,
                "start_line": current_start,
                "end_line": i,
                "content": "\n".join(current_chunk_lines),
            })
            current_chunk_lines = []
            current_start = i + 1

    if current_chunk_lines:
        chunks.append({
            "file": file_path,
            "start_line": current_start,
            "end_line": len(lines) - 1,
            "content": "\n".join(current_chunk_lines),
        })

    return chunks


def index_repo(repo_path: str, repo_id: str, commit_sha: str = "") -> dict:
    """Parse and index a repository into ChromaDB."""
    chroma = get_chroma_client()
    collection_name = f"repo_{repo_id.replace('-', '_')}"

    # Delete existing collection if re-indexing
    try:
        chroma.delete_collection(collection_name)
    except Exception:
        pass

    collection = chroma.create_collection(
        name=collection_name,
        metadata={"repo_id": repo_id, "commit_sha": commit_sha},
    )

    all_chunks = []
    file_count = 0

    for root, dirs, files in os.walk(repo_path):
        # Skip hidden dirs and common ignore patterns
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in {"node_modules", "__pycache__", "venv", ".venv", "dist", "build"}]

        for filename in files:
            ext = Path(filename).suffix
            if ext not in SUPPORTED_EXTENSIONS:
                continue

            filepath = os.path.join(root, filename)
            rel_path = os.path.relpath(filepath, repo_path)

            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except Exception:
                continue

            if not content.strip():
                continue

            chunks = _chunk_file(rel_path, content)
            all_chunks.extend(chunks)
            file_count += 1

    # Batch upsert into ChromaDB
    if all_chunks:
        ids = [
            hashlib.sha256(f"{c['file']}:{c['start_line']}".encode()).hexdigest()
            for c in all_chunks
        ]
        documents = [c["content"] for c in all_chunks]
        metadatas = [
            {"file": c["file"], "start_line": c["start_line"], "end_line": c["end_line"]}
            for c in all_chunks
        ]
        collection.add(ids=ids, documents=documents, metadatas=metadatas)

    return {"file_count": file_count, "chunk_count": len(all_chunks)}


def search_codebase(query: str, repo_id: str, n_results: int = 5) -> list[dict]:
    """Semantic search over the indexed codebase."""
    if not repo_id:
        return []

    chroma = get_chroma_client()
    collection_name = f"repo_{repo_id.replace('-', '_')}"

    try:
        collection = chroma.get_collection(collection_name)
        results = collection.query(query_texts=[query], n_results=n_results)
    except Exception:
        return []

    output = []
    if results and results["documents"]:
        for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
            output.append({
                "file": meta.get("file", ""),
                "start_line": meta.get("start_line", 0),
                "content": doc,
            })

    return output
