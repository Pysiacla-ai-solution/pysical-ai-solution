#### 다음 실습 코드는 학습 목적으로만 사용 바랍니다. 문의 : audit@korea.ac.kr 임성열 Ph.D.
#### 실습 코드는 완성된 상용 버전이 아니라 교육용으로 제작되었으며, 상용 서비스로 이용하려면 배포 목적에 따라서 보완이 필요합니다.

from fastapi import FastAPI, Depends, HTTPException, status, Cookie, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from starlette.staticfiles import StaticFiles
from jose import jwt, JWTError
from langchain_core.documents import Document

from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from pathlib import Path
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from app.utils import vectorstore_state


from app.routers.assistant_router import router as assistant_router
from app.routers.gpu_router import router as gpu_router

from pathlib import Path

from dotenv import load_dotenv
import os
os.environ["OMP_NUM_THREADS"] = "1"


# 0) 환경 변수 로드 (.env)

APP_DIR = Path(__file__).resolve().parent           # 
PROJECT_DIR = APP_DIR.parent                        # 

dotenv_path = APP_DIR / ".env"                      # app/.env
# dotenv_path = PROJECT_DIR / ".env"                # 루트에 두었다면 이 줄로 교체
load_dotenv(dotenv_path)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("API 키가 설정되지 않았습니다. .env 파일을 확인하세요.")


# 1) 경로 설정

STATIC_DIR = APP_DIR / "static"                     # HTML/CSS/JS, favicon 등 정적 리소스

INDEX_HTML   = STATIC_DIR / "index.html"
STANDARD_HTML     = STATIC_DIR / "standard.html"
PARAMETER_HTML     = STATIC_DIR / "parameter.html"
TEMPLATE_HTML = STATIC_DIR / "template.html"
ENV_HTML = STATIC_DIR / "env.html"
GPU_HTML = STATIC_DIR / "gpu.html"

STATIC_DIR.mkdir(parents=True, exist_ok=True)

# 2) FastAPI 앱

app = FastAPI()



@app.on_event("startup")
def load_faiss_on_startup():
    faiss_dir = Path(__file__).resolve().parent / "data" / "faiss"
    if not faiss_dir.exists():
        print("⚠️ FAISS index not found:", faiss_dir)
        return None

    # BGE 임베딩 — inject 코드와 동일한 설정
    model_name = "BAAI/bge-base-en-v1.5"
    encode_kwargs = {"normalize_embeddings": True}

    embeddings = HuggingFaceEmbeddings(
        model_name=model_name,
        model_kwargs={"device": "cpu"},
        encode_kwargs=encode_kwargs,
    )

    vectorstore_state.VECTORSTORE = FAISS.load_local(
        str(faiss_dir),
        embeddings,
        allow_dangerous_deserialization=True,
    )
    print("✅ FAISS VectorStore (BGE-Base + Cosine) loaded")

#     faiss_dir = Path(__file__).resolve().parent / "data" / "faiss"
#     if (faiss_dir / "index.faiss").exists():
#         embeddings = OpenAIEmbeddings()
#         vectorstore_state.VECTORSTORE = FAISS.load_local(
#             str(faiss_dir),
#             embeddings,
#             allow_dangerous_deserialization=True,  # 로컬 신뢰 환경에서만
#         )

# Java 서버와 반드시 맞춰야 하는 설정
SECRET_KEY = "RANDOM_SECRET_KEY"   # Java JwtUtil.SECRET 과 동일
ALGORITHM = "HS256"
ISSUER = "simple-auth-server"      # Java JwtUtil.ISSUER 와 동일

# 3) JWT 디코딩 의존성

def get_current_user(
    access_token: str | None = Cookie(default=None, alias="ACCESS_TOKEN")
):
    """
    8080 서버에서 발급한 ACCESS_TOKEN(JWT) 쿠키를 읽어
    현재 로그인 유저 정보를 반환하는 의존성.
    """
    if access_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated (no ACCESS_TOKEN cookie)",
        )

    try:
        payload = jwt.decode(
            access_token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            issuer=ISSUER,
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_id = payload.get("sub")
    username = payload.get("username")

    if user_id is None or username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    return {"id": user_id, "username": username}

# 4) (핵심) HTML은 "라우트"로만 제공 + Depends로 보호
#    - /index.html 직접 접근도 차단(=JWT 있어야만 열림)
#    - StaticFiles는 HTML이 아닌 정적 리소스(CSS/JS/이미지) 제공용으로만 사용

def _must_exist(p: Path, name: str):
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"{name} not found: {p}")

@app.get("/", include_in_schema=False)
async def root_page(current_user: dict = Depends(get_current_user)):
    _must_exist(INDEX_HTML, "index.html")
    return FileResponse(INDEX_HTML)

@app.get("/index.html", include_in_schema=False)
async def index_page(current_user: dict = Depends(get_current_user)):
    _must_exist(INDEX_HTML, "index.html")
    return FileResponse(INDEX_HTML)

@app.get("/standard.html", include_in_schema=False)
async def standard_page(current_user: dict = Depends(get_current_user)):
    _must_exist(STANDARD_HTML, "standard.html")
    return FileResponse(STANDARD_HTML)

@app.get("/parameter.html", include_in_schema=False)
async def parameter_page(current_user: dict = Depends(get_current_user)):
    _must_exist(PARAMETER_HTML, "parameter.html")
    return FileResponse(PARAMETER_HTML)

@app.get("/template.html", include_in_schema=False)
async def template_page(current_user: dict = Depends(get_current_user)):
    _must_exist(TEMPLATE_HTML, "template.html")
    return FileResponse(TEMPLATE_HTML)


@app.get("/env.html", include_in_schema=False)
async def env_page(current_user: dict = Depends(get_current_user)):
    _must_exist(ENV_HTML, "env.html")
    return FileResponse(ENV_HTML)

@app.get("/gpu.html", include_in_schema=False)
async def gpu_page(current_user: dict = Depends(get_current_user)):
    _must_exist(GPU_HTML, "gpu.html")
    return FileResponse(GPU_HTML)

# 5) 정적 파일 마운트
#    주의: StaticFiles(directory=STATIC_DIR)로 /static을 열면
#       /static/index.html 로 "직접 접근"이 가능해집니다.
#       따라서 HTML 파일은 반드시 "라우트"로만 제공하고,
#       정적 리소스는 별도 디렉터리로 분리하는 것이 안전합니다.
#
#    ▶ 권장 구조:
#       app/static/pages/*.html (라우트로만 제공)
#       app/static/assets/*     (mount로 제공)
#
#    여기서는 현재 구조(STATIC_DIR 하나)에 맞춰 최소 침습으로 구성합니다:
#    - /static 아래는 허용하되, /static/index.html 같은 HTML 직접 접근은 404로 막음
#      (아래 Middleware에서 HTML 파일명 요청을 차단)

@app.middleware("http")
async def block_direct_html_under_static(request: Request, call_next):
    # /static 경로로 HTML 파일을 직접 요청하는 것을 차단
    # (예: /static/index.html, 등)
    path = request.url.path
    if path.startswith("/static/") and path.lower().endswith(".html"):
        return Response(status_code=404)
    return await call_next(request)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")      # /static/*


# 6) CORS
#   - 인증 쿠키 기반이면 allow_origins="*" + allow_credentials=True 조합은 불가합니다.
#   - 현재 페이지(8008)에서만 API를 쓰는 구조라면 CORS를 널널하게 둘 필요가 없습니다.
#   - 필요 시 8080(인증 서버)와 연동하는 fetch가 있다면 정확한 origin만 허용하세요.

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8008",
        "http://127.0.0.1:8008",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 7) favicon 404 방지 (인증 없이도 204로 처리하고 싶으면 Depends 제거 가능)
#    - 현재 요구사항: 로그인 없이 접근 차단이므로 Depends 유지

@app.get("/favicon.ico", include_in_schema=False)
def favicon(current_user: dict = Depends(get_current_user)):
    ico = STATIC_DIR / "favicon.ico"
    if ico.exists():
        return FileResponse(
            ico,
            media_type="image/x-icon",
            headers={"Cache-Control": "public, max-age=86400"},
        )
    return Response(status_code=204)


# 8) 라우터 등록 (API도 JWT로 보호하려면 router 내부에서 Depends(get_current_user) 적용 권장)


app.include_router(assistant_router, prefix="/api/assistant")
app.include_router(gpu_router, prefix="/api/gpu")



# 9) 로컬 실행

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8008, reload=True)
    
# 1. 인증을 거치지 않고 직접 접근하는 차단 적용됨 : 아래 2개가 모두 막혀야 정상
# http://localhost:8008/index.html  → 401
# http://localhost:8008/static/index.html → 404 (미들웨어 차단)    
    
# python -m uvicorn app.main:app --port 8008
# 단계별 동작 테스트 Java 인증 후에..
# http://localhost:8008/index.html -> 
# http://localhost:8008/parameter.html -> 
# http://localhost:8008/template.html -> 
#
