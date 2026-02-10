from fastapi import APIRouter, Depends, HTTPException, status, Cookie
from jose import jwt, JWTError

from pydantic import BaseModel, Field #요청/응답 데이터 구조를 정의하기 위한 Pydantic 모델
from typing import Literal, List

from app.services.assistant_service import run_assistant_query #실제 RAG + LLM 처리를 담당하는 서비스 로직을 불러옴

router = APIRouter()

# Java 서버와 반드시 맞춰야 하는 설정
SECRET_KEY = "RANDOM_SECRET_KEY"   # Java JwtUtil.SECRET 과 동일
ALGORITHM = "HS256"
ISSUER = "simple-auth-server"         # Java JwtUtil.ISSUER 와 동일

def get_current_user( #JWT 쿠키를 검사해서 로그인한 사용자 정보를 가져오는 인증 함수
    access_token: str | None = Cookie(default=None, alias="ACCESS_TOKEN")
):
    """
    8080 Java 서버에서 발급한 ACCESS_TOKEN(JWT) 쿠키를 읽어
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

    # 필요하면 여기서 DB 조회 후 실제 User 객체를 리턴해도 됨
    return {"id": user_id, "username": username}



# 프론트 payload 고정 형태 그대로 모델링
class RobotInfo(BaseModel):
    type: str = ""
    dof: str = ""
    mass: str = ""
    notes: str = ""


class AssistantQueryRequest(BaseModel):  #프론트에서 보내는 요청 JSON 구조 정의 시작
    mode: Literal["spec", "params", "template"]
    query: str = Field(..., min_length=1, description="사용자 질문")
    robot: RobotInfo

class AssistantQueryResponse(BaseModel):  #프론트로 돌려줄 응답 구조 정의
    answer: str
    sources: List[str]

@router.post("/query", response_model=AssistantQueryResponse) #POST /api/assistant/query 엔드포인트 정의 , 응답은 AssistantResponse 형태로 강제
async def assistant_query_endpoint(
    payload: AssistantQueryRequest, #요청 JSON을 AssistantQuery 모델로 자동 파싱
    current_user: dict = Depends(get_current_user)  #  JWS 인증 수행 인증 실패 시 여기서 바로 401 반환
):
    """
    프론트 → POST /api/assistant/query
    payload:
    {
      "mode": "spec|params|template",
      "query": "사용자 질문",
      "robot": { "type": "", "dof": "", "mass": "", "notes": "" }
    }

    response:
    { "answer": "텍스트", "sources": ["출처1", "출처2"] }
    """
    # 입력 검증(추가 방어)
    q = payload.query.strip()
    if not q:
        raise HTTPException(status_code=422, detail="query는 비어있을 수 없습니다.")

    try:
        robot_dict=payload.robot.model_dump()
        print("robot_dict type:", type(robot_dict), robot_dict)
        result = await run_assistant_query(
            mode=payload.mode,
            query=payload.query.strip(),
            robot=payload.robot.model_dump(),
            user=current_user,
            top_k=3,   # 필요시 payload로 받아도 됨
            print_full_chunks=True,         
            debug_prompt=True,            
            debug_context_max_chars=0, 
        )
        print("result type:", type(result), result)
        return {"answer": result["answer"], "sources": result.get("sources", [])}

        
        

    except ValueError as e:
        # 서비스에서 "입력값 문제"로 ValueError 던지면 400 처리
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
