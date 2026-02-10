import os #환경 변수(OpenAI API Key) 접근용
from typing import Any, Dict, Optional, List, Tuple

from dotenv import load_dotenv #.env 파일 로드
from langchain_openai import ChatOpenAI #OpenAI GPT 모델을 LangChain 인터페이스로 사용
from langchain_core.messages import SystemMessage, HumanMessage #LLM 프롬프트 메시지 구조 정의
import os
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from langchain_openai import ChatOpenAI


from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.documents import Document
from textwrap import shorten


from app.utils import vectorstore_state  #서버 전역 FAISS 벡터스토어 접근용 (RAG 핵심)

# =========================================================
# LLM
load_dotenv()

def get_llm():
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다.")
    return ChatOpenAI( #키 없으면 서버 설정 오류로 즉시 실패
        model="gpt-4o",
        temperature=0.3,
        openai_api_key=key,
    )


# =========================================================
# System Prompt
# =========================================================
def build_system_prompt(mode: str) -> str:
    if mode == "spec":
        return (
            "You are an expert in defining specifications for robotics and automation projects "
            "based on NVIDIA Isaac Sim and Isaac Lab. "
            "Based on the user's requirements, you logically structure and explain the components "
            "of a robot learning environment, such as Action, Observation, Reward, and Termination."
        )

    if mode == "params":
        return (
            "You are an expert in designing robot learning parameters in NVIDIA Isaac Sim and Isaac Lab environments. "
            "Your goal is to propose realistic parameter ranges that prioritize reinforcement learning stability "
            "and reliable convergence."
        )

    if mode == "template":
        return (
            "You are an assistant specialized in creating documentation and configuration templates "
            "for robot learning and automation projects. "
            "You generate structured outputs that users can directly copy and use."
        )

    return "You are a helpful assistant specialized in NVIDIA Isaac Sim / Isaac Lab robotics learning workflows."

# =========================================================
# 출력 함수 (Top-k 분리 + score 출력)
# =========================================================
def print_retrieval(results: List[Tuple[Document, float]], max_preview_chars: int = 350):
    """
    results: List[Tuple[Document, float]] from similarity_search_with_score
    - score는 FAISS 설정에 따라 '거리' 또는 '유사도 성격'일 수 있어 라벨을 score로 둠.
    """
    print("\n" + "=" * 60)
    print("🔍 [RETRIEVED CONTEXT - TOP RESULTS]")
    print("=" * 60)

    for rank, (doc, score) in enumerate(results, start=1):
        src = doc.metadata.get("source_file", "unknown")
        chunk = doc.metadata.get("chunk_id", "?")
        print(f"\n--- [#{rank}] score: {score:.6f} | {src} | chunk {chunk} ---")

        preview = doc.page_content.strip().replace("\n", " ")
        preview = shorten(preview, width=max_preview_chars, placeholder=" ...")
        print(preview)

    print("\n" + "=" * 60 + "\n")


def print_full_docs(results: List[Tuple[Document, float]]):
    """Top-k 문서 chunk 전체 내용을 rank별로 분리 출력"""
    print("\n" + "=" * 60)
    print("📄 [FULL CHUNKS - TOP RESULTS]")
    print("=" * 60)

    for rank, (doc, score) in enumerate(results, start=1):
        src = doc.metadata.get("source_file", "unknown")
        chunk = doc.metadata.get("chunk_id", "?")
        print(f"\n========== [#{rank}] score: {score:.6f} | {src} | chunk {chunk} ==========")
        print(doc.page_content.rstrip())
        print("=" * 60)

    print("\n" + "=" * 60 + "\n")


def docs_to_context(docs: List[Document]) -> str:
    blocks = []
    for d in docs:
        src = d.metadata.get("source_file", "unknown")
        chunk = d.metadata.get("chunk_id", "?")
        blocks.append(f"[{src} | chunk {chunk}]\n{d.page_content}")
    return "\n\n".join(blocks)

def docs_to_sources(docs: List[Document]) -> List[str]:
    seen = set()
    out = []
    for d in docs:
        s = f"{d.metadata.get('source_file','unknown')} | chunk {d.metadata.get('chunk_id','?')}"
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out

# =========================================================
# ✅ 디버그 출력 (프롬프트/컨텍스트)
# =========================================================
def print_prompt_debug(
    system_prompt: str,
    user_prompt: str,
    context: str,
    sources: List[str],
    max_context_chars: int = 0,
):
    """
    - system_prompt, user_prompt: LLM에 전달되는 원문
    - context: RAG context (user_prompt에도 포함되어 있지만 따로 분리 출력)
    - sources: 어떤 chunk가 들어갔는지 확인용
    - max_context_chars:
        0이면 전체 출력,
        0보다 크면 context를 그 길이로 잘라 미리보기로 출력
    """
    print("\n" + "#" * 90)
    print("🧪 [DEBUG] PROMPT INPUTS TO LLM")
    print("#" * 90)

    print("\n[SOURCES]")
    print("-" * 90)
    if sources:
        for s in sources:
            print("-", s)
    else:
        print("(no sources)")

    print("\n[SYSTEM PROMPT]")
    print("-" * 90)
    print(system_prompt)

    print("\n[CONTEXT]")
    print("-" * 90)
    if context:
        if max_context_chars and len(context) > max_context_chars:
            print(context[:max_context_chars] + "\n... (truncated)")
        else:
            print(context)
    else:
        print("(empty context)")

    print("\n[USER PROMPT (FULL)]")
    print("-" * 90)
    print(user_prompt)

    print("\n" + "#" * 90 + "\n")



# =========================================================
# RAG 실행
# =========================================================
async def run_assistant_query( 
    mode: str,
    query: str,
    robot: Dict[str, Any],
    user: Optional[Dict[str, Any]] = None,
    top_k: int = 3,
    print_full_chunks: bool = False,     # ✅ chunk 전체 출력 옵션
    debug_prompt: bool = True,           # ✅ 프롬프트/컨텍스트 디버그 출력 옵션
    debug_context_max_chars: int = 0,    # ✅ 0이면 context 전체 출력, 아니면 잘라서 출력
    ) -> Dict[str, Any]:

    llm = get_llm()
    system_prompt = build_system_prompt(mode)


    context = ""
    sources: List[str] = []
    results: List[Tuple[Document, float]] = []

    if vectorstore_state.VECTORSTORE is not None:
        vs = vectorstore_state.VECTORSTORE
        print("vs is None?", vs is None)
        print("vs type:", type(vs))

        # 인덱스 차원
        print("faiss dim:", vs.index.d)

        # 쿼리 임베딩 차원
        q_emb = vs.embedding_function.embed_query(query)
        print("query emb dim:", len(q_emb))
        print("query sample:", q_emb[:5])
        results = vectorstore_state.VECTORSTORE.similarity_search_with_score(query, k=top_k)

        # ✅ Top-k 요약 출력 + 필요 시 전체 chunk 출력
        if results:
            print_retrieval(results, max_preview_chars=350)
            if print_full_chunks:
                print_full_docs(results)

        docs = [doc for (doc, _score) in results]
        if docs:
            context = docs_to_context(docs)
            sources = docs_to_sources(docs)
    
    if context:
        user_prompt = f"""
Based on the following context, answer the question in detail.

Instructions:
- Actively use the context if it is directly relevant to the question.
- If the context does not contain sufficient information, you may also rely on general knowledge to answer.
- When combining context-based information with general knowledge, do not exaggerate.
- If any part of the answer is uncertain or inferred, clearly indicate it as "estimated" or "inferred".

[Context]
{context}

[User Question]
{query}

[Robot Info]
{robot}
"""
    else:
        user_prompt = f"""
Answer the following question.
(Since there are no reference documents provided, respond based on general knowledge and reasoning. If any part of the answer is uncertain, clearly indicate it as "estimated".)

[User Question]
{query}

[Robot Info]
{robot}
"""

    # ✅ 디버그: LLM에 들어가는 프롬프트/컨텍스트 출력
    if debug_prompt:
        print_prompt_debug(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            context=context,
            sources=sources,
            max_context_chars=debug_context_max_chars,
        )

    # ✅ 실제 invoke (system/user 메시지 변수로 분리)
    system_msg = SystemMessage(content=system_prompt)
    human_msg = HumanMessage(content=user_prompt)

    answer = llm.invoke([system_msg, human_msg]).content
    print("\n🧠 ANSWER:\n", answer)
    print("\n📚 SOURCES:")
    for s in sources:
        print("-", s)

    raw_retrieval=[
            {
                "rank": i + 1,
                "score": float(score),
                "source_file": doc.metadata.get("source_file", "unknown"),
                "chunk_id": doc.metadata.get("chunk_id", "?"),
            }
            for i, (doc, score) in enumerate(results)
        ]
    print("\n📌 Retrieval summary:")
    for r in raw_retrieval:
        print(f"- #{r['rank']} score={r['score']:.6f} | {r['source_file']} | chunk {r['chunk_id']}")

    return {
        "answer": answer,
        "sources": sources,
    }







# =========================================================
# 실행
# =========================================================
# if __name__ == "__main__":
#     result = execute_rag_query(
#         mode="params",
#         query="I'm setting up ANYmal quadruped robot for rough terrain locomotion in Isaac Gym.What domain randomization parameters should I use for friction coefficient, mass distribution, and motor strength? What's the typical reward weight for velocity tracking vs energy consumption?",
#         robot={
#             "type": "quadruped",
#             "dof": 12,
#             "notes": "IsaacLab PPO training",
#         },
#         top_k=3,
#         print_full_chunks=True,         # True면 각 chunk 전체를 분리 출력
#         debug_prompt=True,             # ✅ True면 프롬프트/컨텍스트 디버그 출력
#         debug_context_max_chars=0,      # ✅ 0이면 context 전체 출력 (너무 길면 적당히 숫자 지정)
#     )

    
