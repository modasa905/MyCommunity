import os
import shutil  # 🌟 파일 이동을 위한 라이브러리 추가
from google import genai
from google.genai import types
from supabase import create_client, Client
from dotenv import load_dotenv

# ---------------------------------------------------------
# 🛠️ 1. 환경 설정
# ---------------------------------------------------------
# Stage 폴더 경로 (여기서 파일을 읽습니다)
STAGE_FOLDER_PATH = "/Users/nakjun/Library/CloudStorage/GoogleDrive-modasa905@gmail.com/내 드라이브/My_Obs/42. Study Stage"

# 타겟 폴더 경로 (처리가 끝난 파일이 돌아갈 '40. Study' 폴더)
TARGET_FOLDER_PATH = "/Users/nakjun/Library/CloudStorage/GoogleDrive-modasa905@gmail.com/내 드라이브/My_Obs/40. Study"

load_dotenv()
# Supabase 세팅
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Gemini 세팅
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

# 모델 설정
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL")

# ---------------------------------------------------------
# 🧠 2. 핵심 함수들
# ---------------------------------------------------------
def get_all_md_files(directory_path):
    md_files = []
    for root, dirs, files in os.walk(directory_path):
        for file in files:
            if file.endswith(".md"):
                md_files.append(os.path.join(root, file))
    return md_files

def read_md_content(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"🚨 파일 읽기 에러 ({file_path}): {e}")
        return None

def chunk_text(text, chunk_size=500, overlap=50):
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks

def get_gemini_embedding(text):
    result = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")
    )
    return result.embeddings[0].values

# ---------------------------------------------------------
# 🚀 3. 실행 부분 (DB 덮어쓰기 + 자동 파일 이동)
# ---------------------------------------------------------
if __name__ == "__main__":
    print(f"🔍 Stage 폴더의 파일 동기화를 시작합니다...\n")
    
    stage_files = get_all_md_files(STAGE_FOLDER_PATH)
    
    if not stage_files:
        print("⚠️ Stage 폴더에 처리할 마크다운 파일이 없습니다.")
        exit()
        
    print(f"📂 총 {len(stage_files)}개의 타겟 파일을 발견했습니다.\n")
    
    total_chunks_inserted = 0
    for file_path in stage_files:
        file_name = os.path.basename(file_path)
        clean_title = os.path.splitext(file_name)[0] 
        
        # 1. DB의 기존 데이터 삭제
        print(f"🧹 [{file_name}] 기존 데이터가 있다면 삭제 중...")
        supabase.table("obsidian_notes").delete().eq("file_name", file_name).execute()
        
        content = read_md_content(file_path)
        if not content: continue
            
        chunks = chunk_text(content)
        print(f"⏳ [{file_name}] 새 데이터 임베딩 및 저장 중... ({len(chunks)}개 조각)")
        
        # 2. 임베딩 및 저장
        for i, chunk in enumerate(chunks):
            if not chunk.strip(): continue
            
            enriched_chunk = f"[Document: {clean_title} | Part: {i+1} of {len(chunks)}]\n{chunk}"
            vector = get_gemini_embedding(enriched_chunk)
            
            data = {
                "file_name": file_name, 
                "content": enriched_chunk, 
                "embedding": vector
            }
            supabase.table("obsidian_notes").insert(data).execute()
            total_chunks_inserted += 1
            
        # 🌟 3. DB 작업이 끝난 후 파일을 원래 폴더(40. Study)로 쏙! 이동시킵니다.
        target_path = os.path.join(TARGET_FOLDER_PATH, file_name)
        shutil.move(file_path, target_path) # 이미 같은 이름의 파일이 있으면 자동으로 덮어씁니다.
        print(f"📦 [{file_name}] 파일을 본래 폴더(40. Study)로 이동 완료!\n")
            
    print("🎉 Stage 폴더 동기화 및 파일 정리가 완벽하게 완료되었습니다!")
    print(f"📚 DB에 새롭게 덮어씌워진 지식 조각: {total_chunks_inserted}개")