import re
import time
import os

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from datetime import datetime, timedelta, timezone
import traceback
from dotenv import load_dotenv
import random

# AI 라이브러리
from google import genai
from google.genai import types
from ollama import Client as OllamaClient
from supabase import create_client, Client as SupabaseClient

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# ---------------------------------------------------------
# 1. 환경 변수 및 하이브리드 AI 설정
# ---------------------------------------------------------
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: SupabaseClient = create_client(SUPABASE_URL, SUPABASE_KEY)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY")
ollama_client = OllamaClient(
    host="https://ollama.com",
    headers={'Authorization': f'Bearer {OLLAMA_API_KEY}'}
)

CRON_SECRET = os.getenv("CRON_SECRET")
DRAFT_MODEL = os.getenv("DRAFT_MODEL")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL")

# ---------------------------------------------------------
# 2. 방명록 DB 설정
# ---------------------------------------------------------
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

KST = timezone(timedelta(hours=9))
def get_kst_now():
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M")

class Post(Base):
    __tablename__ = "posts"
    id = Column(Integer, primary_key=True, index=True)
    content = Column(String)
    password = Column(String)
    created_at = Column(String, default=get_kst_now)

class DraftNote(Base):
    __tablename__ = "draft_notes"
    id = Column(Integer, primary_key=True, index=True)
    source_file = Column(String) 
    suggestion = Column(String)
    content = Column(String)
    upvotes = Column(Integer, default=0)
    created_at = Column(String, default=get_kst_now)

Base.metadata.create_all(bind=engine)

class SearchRequest(BaseModel):
    question: str

class GenerateRequest(BaseModel):
    question: str
    context: str

class VoteRequest(BaseModel):
    action: str

class GenerateRequest(BaseModel):
    question: str
    context: str
    mode: str = "express"

# ---------------------------------------------------------
# 3. 라우터 설정
# ---------------------------------------------------------
# 1. 메인 페이지
@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    try:
        # 조회수(view_count) 내림차순으로 상위 100개 문서 가져오기
        response = supabase.table("obsidian_documents") \
            .select("id, file_name, view_count") \
            .order("view_count", desc=True) \
            .limit(100) \
            .execute()
        
        top_notes = response.data
        total_notes = len(top_notes) # 전체 지식의 양 (상위 100개 기준)

        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "total_notes": total_notes,
                "top_notes": top_notes # 템플릿으로 데이터 전달
            }
        )
    except Exception as e:
        print(f"🚨 메인 페이지 로드 에러: {e}")
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"total_notes": 0, "top_notes": []}
        )

# 2. 커뮤니티 페이지
@app.get("/community", response_class=HTMLResponse) # URL을 /community로 변경
def read_community(request: Request):
    db = SessionLocal()
    posts = db.query(Post).order_by(Post.id.desc()).all()
    db.close()
    return templates.TemplateResponse(
        request=request, 
        name="community.html", # 파일명 업데이트
        context={"posts": posts}
    )

# 3. Drafts 페이지
@app.get("/drafts", response_class=HTMLResponse)
def read_drafts(request: Request):
    db = SessionLocal()
    drafts = db.query(DraftNote).order_by(DraftNote.id.desc()).all()
    db.close()
    return templates.TemplateResponse(
        request=request, 
        name="drafts.html", 
        context={"drafts": drafts}
    )

# [API 1] 검색 전용 엔드포인트 (빠름)
@app.post("/api/search")
async def api_search(request: SearchRequest):
    try:
        
        # 1. 질문 임베딩 생성 - Retry 로직 (안정성 확보)
        max_retries = 3
        question_embedding = None
        
        for attempt in range(max_retries):
            try:
                result = gemini_client.models.embed_content(
                    model=EMBEDDING_MODEL,
                    contents=request.question,
                    config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY")
                )
                question_embedding = result.embeddings[0].values
                break  # 성공 시 루프 탈출
                
            except Exception as e:
                error_str = str(e)
                if "503" in error_str and attempt < max_retries - 1:
                    sleep_time = 2 ** attempt
                    print(f"⚠️ 임베딩 서버 과부하 (503). {sleep_time}초 후 재시도... ({attempt+1}/{max_retries})")
                    time.sleep(sleep_time)
                else:
                    raise e
        
        if not question_embedding:
            raise Exception("임베딩 생성에 최종 실패했습니다.")
        
        # 2. 자식 테이블에서 관련 처ㅇ크15개 검색
        response = supabase.rpc("match_chunks", {
            "query_embedding": question_embedding,
            "match_threshold": 0.3, 
            "match_count": 15 
        }).execute()
        
        # 3. 부모 문서 ID 중복 제거 (Top 3 추출)
        unique_doc_ids = []
        seen_ids = set()
        
        for chunk in response.data:
            doc_id = chunk["document_id"]
            if doc_id not in seen_ids:
                unique_doc_ids.append(doc_id)
                seen_ids.add(doc_id)
                
            if len(unique_doc_ids) == 3: 
                break
                
        # 4. 부모 테이블에서 문서 전체 가져오기 & 조회수 증가
        final_docs = []
        if unique_doc_ids:
            docs_response = supabase.table("obsidian_documents").select("id, file_name, full_content, view_count").in_("id", unique_doc_ids).execute()
            
            for doc in docs_response.data:
                final_docs.append({
                    "file_name": doc["file_name"],
                    "content": doc["full_content"] # 🌟 스마트 청크 대신 원본 전체 텍스트 사용!
                })
                
                # 조회수 1 증가
                current_count = doc.get("view_count") or 0
                supabase.table("obsidian_documents") \
                    .update({"view_count": current_count + 1}) \
                    .eq("id", doc["id"]) \
                    .execute()
            
        return {"docs": final_docs}
    
    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        print(f"🚨 검색 에러 상세 로그:\n{error_msg}")
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=500, content={"error": str(e)})

# [API 2] 답변 생성 전용 엔드포인트
@app.post("/api/generate")
async def api_generate(request: GenerateRequest):
    try:        
        has_korean = bool(re.search(r'[\u3130-\u318F\uAC00-\uD7A3]', request.question))
        language_instruction = "한국어로 답하세요." if has_korean else "Please answer in English."
        
        # 1. 모드 설정
        mode_settings = {
            "express": {
                "provider": os.getenv("FAST_MODEL_PROVIDER"),
                "model": os.getenv("FAST_MODEL"),
                "prompt": "Quickly and concisely summarize the core points using ONLY the information provided in the [References]."
            },
            "deep": {
                "provider": os.getenv("HEAVY_MODEL_PROVIDER"),
                "model": os.getenv("HEAVY_MODEL"),
                "prompt": "Analyze the provided [References] in great depth and explain them logically. However, you must adhere to the content and scope specified in the literature without adding external claims."
            },
            "critical": {
                "provider": os.getenv("HEAVY_MODEL_PROVIDER"),
                "model": os.getenv("HEAVY_MODEL"),
                "prompt": "Answer based on the provided [References], but approach the topic critically from the perspective of a senior researcher(PhD-level). If you identify limitations in the literature, you are explicitly encouraged to draw upon your broader academic knowledge outside the provided references. However, you MUST clearly distinguish between the information found in the [References] and the external knowledge you introduce."
            }
        }

        settings = mode_settings.get(request.mode, mode_settings["express"])
        provider = settings["provider"]
        target_model = settings["model"]
        behavior_prompt = settings["prompt"]

        system_prompt = f"You are an assistant for an economics researcher. {behavior_prompt} {language_instruction}\n\n[References]\n{request.context}"
        
        if provider == "ollama":
            ai_response = ollama_client.chat(model=target_model, messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": request.question}
            ])
            return {"answer": ai_response['message']['content'], "thought": ""}
            
        elif provider == "gemini":
            combined_prompt = f"{system_prompt}\n\nUser Question: {request.question}"
            gen_config = types.GenerateContentConfig()
            
            if request.mode in ["deep", "critical"]:
                gen_config.thinking_config = types.ThinkingConfig(
                    include_thoughts=True
                )
        
            max_retries = 3
            ai_response = None
            
            for attempt in range(max_retries):
                try:
                    ai_response = gemini_client.models.generate_content(
                        model=target_model,
                        contents=combined_prompt,
                        config=gen_config
                    )
                    break 
                except Exception as e:
                    if "503" in str(e) and attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                    elif "503" in str(e):
                        fallback_model = os.getenv("FALLBACK_MODEL")
                        fallback_res = ollama_client.chat(model=fallback_model, messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": request.question}
                        ])
                        return {"answer": fallback_res['message']['content'], "thought": "⚠️ Gemini 서버 과부하로 로컬 모델 우회 답변입니다."}
                    else:
                        raise e 
                        
            if ai_response:
                raw_answer = ""
                thought_process = "" 
                
                if ai_response.candidates and ai_response.candidates[0].content.parts:
                    for part in ai_response.candidates[0].content.parts:
                        if not part.text:
                            continue
                        
                        if part.thought:
                            thought_process += part.text + "\n\n"
                        else:
                            raw_answer += part.text
                            
                return {"answer": raw_answer, "thought": thought_process.strip()}
            else:
                raise Exception("서버 통신에 최종 실패했습니다.")
                
        else:
            raise ValueError(f"지원하지 않는 AI Provider 입니다: {provider}")

    except Exception as e:
        print(f"🚨 생성 에러: {traceback.format_exc()}")
        return {"error": str(e)}

@app.get("/api/generate-daily-draft")
async def generate_daily_draft(secret: str = ""):
    if secret != CRON_SECRET:
        return JSONResponse(status_code=401, content={"error": "접근 권한이 없습니다."})

    try:
        # 🌟 수정: 부모 테이블(obsidian_documents)에서 파일명과 전체 내용을 가져옵니다.
        response = supabase.table("obsidian_documents").select("file_name, full_content").execute()
        if not response.data:
            return {"status": "error", "message": "도서관에 책이 없습니다."}
        
        random_doc = random.choice(response.data)
        
        prompt = f"""You are an expert research assistant specializing in advanced economics and mathematics.
        Based on the concepts in the [Original Note] below, generate a new document that explores advanced mathematical/economic applications, theoretical extensions, or novel academic insights.
        
        The output MUST be written entirely in professional, academic English.
        You MUST strictly follow the exact structure below. Do not add any conversational filler.

        Title: (Provide a descriptive filename, e.g., Advanced_Optimal_Taxation.md)

        Explanation: (Briefly explain the core idea of this new note in plain text. Do NOT use markdown format here.)

        ===SPLIT===
        
        (Write the complete document here. This section must be written in pure Markdown format, ready to be added directly to a database. Use appropriate headers, and LaTeX for math enclosed in $ or $$. Do NOT wrap this section in ```markdown code blocks.)
        
        ***
        (Append a metadata section (Parent Path, Sequence, Related Notes, and Source) that exactly mirrors the formatting of the [Original Note]. Thoughtfully adapt the links to fit this new extension.)
        
        [Original Note: {random_doc['file_name']}]
        {random_doc['full_content']} 
        """
        
        ai_response = gemini_client.models.generate_content(
            model=DRAFT_MODEL,
            contents=prompt
        )
        
        full_content = ""
        if ai_response.candidates and ai_response.candidates[0].content.parts:
            for part in ai_response.candidates[0].content.parts:
                if part.text:
                    full_content += part.text
        
        parts = full_content.split("===SPLIT===")
        suggestion_text = parts[0].strip() # 윗부분 (Title, Explanation)
        draft_text = parts[1].strip() if len(parts) > 1 else "" # 아랫부분 (Markdown 본문)
        
        db = SessionLocal()
        new_draft = DraftNote(
            source_file=random_doc['file_name'],
            suggestion=suggestion_text,
            content=draft_text
        )
        db.add(new_draft)
        db.commit()
        db.close()
        
        return RedirectResponse(url="/", status_code=303)
    
    except Exception as e:
        print(f"🚨 새벽 자동화 에러: {e}")
        return {"error": str(e)}

@app.post("/post")
def create_post(content: str = Form(...), password: str = Form(...)):
    db = SessionLocal()
    new_post = Post(content=content, password=password)
    db.add(new_post)
    db.commit()
    db.close()
    return RedirectResponse(url="/", status_code=303)

@app.post("/delete/{post_id}")
def delete_post(post_id: int, password: str = Form(...)):
    db = SessionLocal()
    post_to_delete = db.query(Post).filter(Post.id == post_id).first()
    if post_to_delete and post_to_delete.password == password:
        db.delete(post_to_delete)
        db.commit()
    db.close()
    return RedirectResponse(url="/", status_code=303)

@app.post("/api/vote/{draft_id}")
async def vote_draft(draft_id: int, request: VoteRequest):
    db = SessionLocal()
    draft = db.query(DraftNote).filter(DraftNote.id == draft_id).first()
    
    if not draft:
        db.close()
        return JSONResponse(status_code=404, content={"error": "노트를 찾을 수 없습니다."})
    
    # 1. 점수 증감
    if request.action == "up":
        draft.upvotes += 1
    elif request.action == "down":
        draft.upvotes -= 1
        
    # 2. 삭제 조건 검사
    if draft.upvotes < -5:
        db.delete(draft) # DB에서 행 삭제
        db.commit()
        db.close()
        return {"deleted": True} # 삭제되었다는 신호만 보냄
        
    db.commit()
    new_votes = draft.upvotes
    db.close()
    
    return {"deleted": False, "upvotes": new_votes}