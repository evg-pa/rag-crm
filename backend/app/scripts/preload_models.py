"""Pre-download embedding and reranker models at build time."""

import sys


def main() -> None:
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("huggingface_hub not available, skipping preload")
        return

    models = [
        "BAAI/bge-small-en-v1.5",
        "cross-encoder/ms-marco-MiniLM-L-6-v2",
    ]
    for model_id in models:
        try:
            print(f"Downloading {model_id}...")
            snapshot_download(model_id)
            print(f"  OK: {model_id}")
        except Exception as exc:
            print(f"  FAIL: {model_id}: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
