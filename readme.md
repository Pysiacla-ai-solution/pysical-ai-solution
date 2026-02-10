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

(이부분은 도익님 코드로 변경 필요)






