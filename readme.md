## 실행 방법
0. .env파일 넣기 
1. maria db 도커에 띄우기 
    
    ```sql
    source demo-app/bin/activate
    cd mariadb_tmplt/
    docker compose -p maria_db -f maria_db.yaml up -d 
    -- port 3079로 접근 가능 
    ```
    
2. login page (인증 서버) running 
    
    ```sql
    source fast-rag-out/bin/activate
    cd **workplace
    ./gradlew build
    ./gradlew :app:run 
    
    --no-configuration-cache
    -- port 8080으로 접근 가능** 
    ```
    
3. front/back running
    
    ```sql
    source fast-rag-out/bin/activate    #voice-ai-code/requirements.txt을 통해서 버전 다시맞춰야함
    cd voice-ai-code
    uvicorn app.main:app --host 0.0.0.0 --port 8008
    
    --port 8008로 접근 가능 
    ```
    

1. 백터 디비 생성 (이미 생성해서 pass)
    
    ```sql
    cd voice-ai-code 
    python -m app.utils.ingest_isaaclab_repo
    ```
    

1. 로그인으로 인증 후 웹 접속 
    
    ```sql
    http://localhost:8080/ 
    
    -- 로그인 하지 않을경우 8008로 접근하지 못한다. 
    ```
    

## 코드 설명

<back>

```java
voice-ai-code/app/routers/         //
	assistant_router.py             //FastAPI에서 라우터를 만든다 
																	//jws인증후 

voice-ai-code/app/services/
	assistant_service.py           //OpenAI GPT 모델을 LangChain 인터페이스로 사용
																//쿼리를 rag검색후 그것을 활용해 output을 얻는다.
```

<front>

```java
voice-ai-code/app/static/     //
	index.htlm 
	parameter.html
	standard.html
	template.html
```

<RAG>

```java
voice-ai-code/app/utils/   //백터 
	ingest_isaaclab_repo.py  //docs에 있는 파일 임베딩후 저장 (누적)
	ingest_paper_repo.py   //papers에 있는 파일 임베딩후 저정 (누적)
	vectorstore_state.py //
	

voice-ai-code/data/faiss/     //백터 data 저장 공간
	index.faiss   
	index.pkl

voice-ai-code/external/        //RAG에 넣을 자료들을 모아둔다. 
	docs/                        //git자료 저장 (여기서 md, rst파일만을 가져와서 백터DB에저장)
	papers/                      //pdf자료 저장
```

—> 즉 ingest_isaaclab_repo.py를 활용해 백터디비 저장후
—> assistant_service.py에서 RAG검색을 한다. 









좋아. 4명 팀 기준으로 **“각자 브랜치 → PR로 main 합치기”** 방식 안내문을 그대로 팀원들한테 보내면 되게 정리해줄게.

---

## 팀 Git 협업 방법 (4명용, 브랜치 + PR)

### 원칙

* **main 브랜치는 항상 안정(실행되는 상태)** 유지
* **개인 작업은 무조건 브랜치에서**
* main에는 **PR(Pull Request)로만 merge**
* 급한 핫픽스도 원칙은 동일 (짧은 브랜치 → PR)

---

## 1) 처음 한 번만: repo 받기

```bash
git clone <repo_url>
cd <repo_folder>
```

---

## 2) 매일 작업 시작 루틴 (중요)

작업하기 전에 main 최신화부터:

```bash
git checkout main
git pull origin main
```

---

## 3) 브랜치 생성 규칙

각자 기능 단위로 브랜치 생성 (추천 네이밍):

* 기능 기준: `feature/<기능명>`

  * 예: `feature/rag-api`, `feature/faiss-index`, `feature/ui-page`
* 사람+기능 기준도 OK:

  * 예: `soyul/rag`, `minsu/backend`

브랜치 만들기:

```bash
git checkout -b feature/<my-work>
```

---

## 4) 작업 → 커밋

작업 후:

```bash
git add .
git commit -m "feat: <변경 내용 요약>"
```

커밋 메시지 예:

* `feat: add retrieval endpoint`
* `fix: prevent faiss segfault by limiting threads`
* `docs: update setup guide`

---

## 5) 브랜치 push

```bash
git push -u origin feature/<my-work>
```

---

## 6) PR 생성 (GitHub에서)

1. GitHub repo 들어가기
2. “Compare & pull request” 버튼 또는 Pull requests 탭
3. base: `main` / compare: `feature/<my-work>`
4. PR 설명에:

   * 무엇을 했는지
   * 어떻게 테스트했는지
   * 영향 범위(파일/모듈) 적기

---

## 7) PR Merge 규칙(추천)

* 최소 **1명 리뷰 후 merge**
* 충돌 나면 작성자가 해결
* PR이 너무 크면 쪼개기(한 PR = 한 기능)

---

## 8) main 업데이트 반영(작업 중간에도 자주)

main에 새로운 변경이 들어오면 내 브랜치에 반영:

```bash
git checkout feature/<my-work>
git fetch origin
git merge origin/main
```

(또는 rebase 써도 되지만 팀플은 merge가 더 안전/쉬움)

---

## 9) 절대 하면 안 되는 것

* ❌ main에 직접 push
* ❌ `.env`, `secrets/`, `data/faiss/`, `node_modules/` 같은 파일 커밋
* ❌ 큰 변경을 한 번에 커밋(커밋은 자주, PR은 기능 단위)

---

## 10) 추천 브랜치 분배(4명 예시)

* A: `feature/api`
* B: `feature/retrieval`
* C: `feature/training`
* D: `feature/ui`
  → 기능이 겹치면 파일 충돌이 늘어나니까 “영역” 나누면 좋음

---

원하면 이걸 팀에 붙여넣기 좋게 **짧은 버전(메신저용)**도 만들어줄까?

