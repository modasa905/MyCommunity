import os
from google import genai
from google.genai import types
from supabase import create_client, Client
from dotenv import load_dotenv

# ---------------------------------------------------------
# 🛠️ 1. 환경 설정
# ---------------------------------------------------------
OBSIDIAN_VAULT_PATH = "/Users/nakjun/Library/CloudStorage/GoogleDrive-modasa905@gmail.com/내 드라이브/My_Obs/40. Study"

load_dotenv()
# Supabase 세팅
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Gemini 세팅
# .env 파일의 내용을 로드
# 환경 변수 가져오기
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

# 모델 설정
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL")

# ---------------------------------------------------------
# 2. 핵심 함수들
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
# 3. 실행 부분
# ---------------------------------------------------------
if __name__ == "__main__":
    print("지식 베이스 구축을 시작합니다...\n")
    
    print("기존 데이터를 초기화합니다... ")
    supabase.table("obsidian_notes").delete().neq("id", 0).execute()
    
    all_files = get_all_md_files(OBSIDIAN_VAULT_PATH)
    print(f"총 {len(all_files)}개의 마크다운 파일을 찾았습니다.\n")
    
    total_chunks_inserted = 0
    for file_path in all_files:
        file_name = os.path.basename(file_path)
        # 확장자(.md)를 제거한 순수 제목만 추출
        clean_title = os.path.splitext(file_name)[0] 
        content = read_md_content(file_path)
        if not content: continue
            
        chunks = chunk_text(content)
        print(f"[{file_name}] 처리 중... ({len(chunks)}개 조각)")
        
        # 핵심 수정: enumerate를 사용하여 청크의 순번(i)을 가져옵니다.
        for i, chunk in enumerate(chunks):
            if not chunk.strip(): continue
            
            # 핵심 수정: 청크 맨 앞에 문서 제목과 순번을 주입합니다.
            enriched_chunk = f"[Document: {clean_title} | Part: {i+1} of {len(chunks)}]\n{chunk}"
            
            # 임베딩 생성 시 원본 chunk가 아닌 '강화된 청크'를 먹입니다.
            vector = get_gemini_embedding(enriched_chunk)
            
            # DB에 저장할 때도 '강화된 청크'를 content로 저장합니다.
            data = {
                "file_name": file_name, 
                "content": enriched_chunk, 
                "embedding": vector
            }
            supabase.table("obsidian_notes").insert(data).execute()
            total_chunks_inserted += 1
            
    print("\n 모든 작업이 완료되었습니다!")
    print(f" 총 {total_chunks_inserted}개의 지식 조각이 Gemini 좌표로 저장되었습니다.")