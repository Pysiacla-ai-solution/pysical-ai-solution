import os
from pathlib import Path
from dotenv import load_dotenv

from pypdf import PdfReader
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
PAPERS_DIR = ROOT_DIR / "external" / "papers"
if not PAPERS_DIR.exists():
    raise RuntimeError(f"papers 디렉터리를 찾지 못했습니다: {PAPERS_DIR}")

DATA_DIR = ROOT_DIR / "app" / "data"
FAISS_DIR = DATA_DIR / "faiss"
DATA_DIR.mkdir(parents=True, exist_ok=True)
FAISS_DIR.mkdir(parents=True, exist_ok=True)

# --------------------
# PDF 텍스트 추출
# --------------------
def extract_pdf_pages(pdf_path: Path):
    reader = PdfReader(str(pdf_path))
    pages = []
    for idx, page in enumerate(reader.pages, start=1):
        t = page.extract_text() or ""
        t = t.strip()
        if t:
            pages.append((idx, t))
    return pages

def collect_pdf_files():
    return [p for p in PAPERS_DIR.rglob("*.pdf") if p.is_file()]

# --------------------
# Ingest
# --------------------
def main():
    files = collect_pdf_files()
    print(f"PDF files found: {len(files)}")

    splitter = RecursiveCharacterTextSplitter(chunk_size=900, chunk_overlap=120)

    docs = []
    for pdf in files:
        pages = extract_pdf_pages(pdf)
        if not pages:
            continue

        chunk_id = 0
        for page_no, text in pages:
            for chunk in splitter.split_text(text):
                chunk = chunk.strip()
                if len(chunk) < 50:
                    continue

                docs.append(
                    Document(
                        page_content=chunk,
                        metadata={
                            "source_type": "papers",
                            "source_file": str(pdf.relative_to(PAPERS_DIR)),  # papers 기준 상대경로
                            "page": page_no,
                            "chunk_id": chunk_id,
                        },
                    )
                )
                chunk_id += 1

    if not docs:
        raise RuntimeError("PDF에서 생성된 chunk가 0개입니다. (텍스트 추출 실패 가능)")

    print(f"Total chunks created: {len(docs)}")

    embeddings = OpenAIEmbeddings(openai_api_key=os.getenv("OPENAI_API_KEY"))

    # --------------------
    # 기존 FAISS 로드 후 누적
    # --------------------
    index_path = FAISS_DIR / "index.faiss"
    if index_path.exists():
        vectorstore = FAISS.load_local(
            str(FAISS_DIR),
            embeddings,
            allow_dangerous_deserialization=True,
        )
        vectorstore.add_documents(docs)
        print("Loaded existing FAISS and appended documents.")
    else:
        vectorstore = FAISS.from_documents(docs, embeddings)
        print("Created new FAISS index.")

    vectorstore.save_local(str(FAISS_DIR))
    print(f"Saved FAISS to: {FAISS_DIR}")

if __name__ == "__main__":
    main()
