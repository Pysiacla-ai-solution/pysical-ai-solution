import os
from pathlib import Path
from dotenv import load_dotenv

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

# --------------------
# 환경 변수 로드
# --------------------
ROOT_DIR = Path(__file__).resolve().parents[2]  # voice-ai-code
load_dotenv(ROOT_DIR / ".env")

# --------------------
# 경로 설정
# --------------------
ISAACLAB_ROOT = ROOT_DIR / "external"
DOCS_DIR = ISAACLAB_ROOT / "docs"

if not DOCS_DIR.exists():
    raise RuntimeError(f"docs 디렉터리를 찾지 못했습니다: {DOCS_DIR}")

DATA_DIR = ROOT_DIR / "app" / "data"
FAISS_DIR = DATA_DIR / "faiss"

DATA_DIR.mkdir(parents=True, exist_ok=True)
FAISS_DIR.mkdir(parents=True, exist_ok=True)

# --------------------
# 파일 수집
# --------------------
def collect_docs_files():
    exts = {".rst", ".md"}
    return [
        p for p in DOCS_DIR.rglob("*")
        if p.is_file() and p.suffix.lower() in exts
    ]

def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore")

# --------------------
# Ingest
# --------------------
def main():
    files = collect_docs_files()
    print(f"docs files found: {len(files)}")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=900,
        chunk_overlap=120,
    )

    docs = []
    for p in files:
        text = read_text(p).strip()
        if len(text) < 50:
            continue

        chunks = splitter.split_text(text)
        for i, chunk in enumerate(chunks):
            chunk = chunk.strip()
            if len(chunk) < 50:
                continue

            docs.append(
                Document(
                    page_content=chunk,
                    metadata={
                        "source_type": "isaaclab",
                        "source_file": str(p.relative_to(DOCS_DIR)),
                        "chunk_id": i,
                    },
                )
            )

    if not docs:
        raise RuntimeError("docs에서 생성된 chunk가 0개입니다.")

    print(f"Total chunks created: {len(docs)}")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY가 설정되어 있지 않습니다. .env 또는 환경변수를 확인하세요.")

    embeddings = OpenAIEmbeddings(openai_api_key=api_key)

    # --------------------
    # 기존 FAISS 로드 후 누적, 없으면 새로 생성
    # --------------------
    index_path = FAISS_DIR / "index.faiss"

    if index_path.exists():
        vectorstore = FAISS.load_local(
            str(FAISS_DIR),
            embeddings,
            allow_dangerous_deserialization=True,  # 로컬 신뢰 환경에서만
        )
        vectorstore.add_documents(docs)
        print("Loaded existing FAISS index and appended documents.")
    else:
        vectorstore = FAISS.from_documents(docs, embeddings)
        print("Created new FAISS index.")

    # 같은 FAISS_DIR에 다시 저장
    vectorstore.save_local(str(FAISS_DIR))
    print(f"Saved FAISS to: {FAISS_DIR}")
    print("docs vectorized & saved successfully.")

if __name__ == "__main__":
    main()
