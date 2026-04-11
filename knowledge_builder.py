import os
from google import genai
from google.genai import types
from supabase import create_client, Client
from dotenv import load_dotenv

# ---------------------------------------------------------
# 🛠️ 1. 환경 설정
# ---------------------------------------------------------
OBSIDIAN_VAULT_PATH = "/Users/nakjun/Library/CloudStorage/GoogleDrive-modasa905@gmail.com/내 드라이브/My_Obs/40. Study"

# Supabase 세팅
SUPABASE_URL = "https://zdthschzdnshnnhtdrbc.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpkdGhzY2h6ZG5zaG5uaHRkcmJjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzUwNjMwOTgsImV4cCI6MjA5MDYzOTA5OH0.7cyBUlTrU1azmWr-5xKzSCseLplX5oLIeFPOS3YbwJM"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Gemini 세팅 (임베딩 전용)
# .env 파일의 내용을 로드
load_dotenv()
# 환경 변수 가져오기
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

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
        model="gemini-embedding-001",
        contents=text,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")
    )
    return result.embeddings[0].values

# ---------------------------------------------------------
# 🚀 3. 실행 부분 (데이터 쏟아붓기!)
# ---------------------------------------------------------
if __name__ == "__main__":
    print("🚀 하이브리드 지식 베이스 구축을 시작합니다...\n")
    
    print("🧹 기존 데이터를 초기화합니다... (Nomic -> Gemini 지도 교체)")
    supabase.table("obsidian_notes").delete().neq("id", 0).execute()
    
    all_files = get_all_md_files(OBSIDIAN_VAULT_PATH)
    print(f"📂 총 {len(all_files)}개의 마크다운 파일을 찾았습니다.\n")
    
    total_chunks_inserted = 0
    for file_path in all_files:
        file_name = os.path.basename(file_path)
        content = read_md_content(file_path)
        if not content: continue
            
        chunks = chunk_text(content)
        print(f"⏳ [{file_name}] 처리 중... ({len(chunks)}개 조각)")
        
        for chunk in chunks:
            if not chunk.strip(): continue
            vector = get_gemini_embedding(chunk)
            data = {"file_name": file_name, "content": chunk, "embedding": vector}
            supabase.table("obsidian_notes").insert(data).execute()
            total_chunks_inserted += 1
            
    print("\n🎉 모든 작업이 완료되었습니다!")
    print(f"📚 총 {total_chunks_inserted}개의 지식 조각이 Gemini 좌표로 저장되었습니다.")