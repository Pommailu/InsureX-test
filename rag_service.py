import os
import glob
import time
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional
from pypdf import PdfReader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_chroma import Chroma

import config

def get_embedding_function() -> GoogleGenerativeAIEmbeddings:
    """Initialize Google Gemini Embeddings with retry configuration."""
    return GoogleGenerativeAIEmbeddings(
        model=config.GOOGLE_EMBEDDING_MODEL,
        google_api_key=config.GOOGLE_API_KEY,
    )

def load_all_pdfs(data_dir: str = config.DATA_DIR) -> List[Document]:
    """
    Load all PDF files from the data directory.
    Extracts text per page and captures source metadata.
    """
    documents = []
    pdf_files = glob.glob(os.path.join(data_dir, "*.pdf"))
    
    if not pdf_files:
        print(f"[RAG] Warning: No PDF files found in {data_dir}")
        return documents

    print(f"[RAG] Loading {len(pdf_files)} PDF document(s) from {data_dir}...")
    for pdf_path in pdf_files:
        filename = os.path.basename(pdf_path)
        try:
            reader = PdfReader(pdf_path)
            print(f"[RAG] Reading '{filename}' ({len(reader.pages)} pages)...")
            for page_idx, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                cleaned_text = text.strip()
                if cleaned_text:
                    doc = Document(
                        page_content=cleaned_text,
                        metadata={
                            "source": filename,
                            "page": page_idx + 1,
                            "total_pages": len(reader.pages)
                        }
                    )
                    documents.append(doc)
        except Exception as e:
            print(f"[RAG] Error reading {filename}: {e}")
            
    print(f"[RAG] Successfully extracted {len(documents)} total page documents.")
    return documents

def split_documents(documents: List[Document], chunk_size: int = 1000, chunk_overlap: int = 150) -> List[Document]:
    """
    Splits documents into smaller semantic chunks suitable for Thai and English insurance text.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", " ", ""]
    )
    chunks = splitter.split_documents(documents)
    for i, chunk in enumerate(chunks):
        chunk.metadata["chunk_id"] = f"{chunk.metadata.get('source', 'doc')}_p{chunk.metadata.get('page', 0)}_c{i}"
    print(f"[RAG] Created {len(chunks)} text chunks for vector indexing.")
    return chunks

class RAGService:
    def __init__(self, persist_dir: str = config.CHROMA_PERSIST_DIR):
        self.persist_dir = persist_dir
        self.embeddings = get_embedding_function()
        self.vector_store: Optional[Chroma] = None
        self._init_vector_store()

    def _init_vector_store(self):
        """Load existing Chroma vector store or build a new one."""
        # Check if collection exists and has documents
        has_existing = False
        if os.path.exists(self.persist_dir) and os.listdir(self.persist_dir):
            try:
                test_store = Chroma(
                    persist_directory=self.persist_dir,
                    embedding_function=self.embeddings,
                    collection_name="insurex_knowledge"
                )
                if test_store._collection.count() > 0:
                    self.vector_store = test_store
                    has_existing = True
                    print(f"[RAG] Loaded existing ChromaDB with {test_store._collection.count()} vectors.")
            except Exception as e:
                print(f"[RAG] Could not load existing Chroma index ({e}). Rebuilding...")

        if not has_existing:
            print(f"[RAG] Initializing new vector store at {self.persist_dir}...")
            self.build_index()

    def build_index(self, force_reload: bool = False):
        """Load PDFs, split into chunks, and save to ChromaDB with rate-limit friendly batching."""
        if force_reload and os.path.exists(self.persist_dir):
            import shutil
            shutil.rmtree(self.persist_dir, ignore_errors=True)
            print(f"[RAG] Cleaned index directory at {self.persist_dir}")

        docs = load_all_pdfs()
        if not docs:
            print("[RAG] No documents to index.")
            return

        chunks = split_documents(docs)
        print(f"[RAG] Indexing {len(chunks)} chunks into ChromaDB with safe batching...")
        
        # Initialize an empty Chroma collection first
        self.vector_store = Chroma(
            persist_directory=self.persist_dir,
            embedding_function=self.embeddings,
            collection_name="insurex_knowledge"
        )

        batch_size = 5
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            max_retries = 5
            for attempt in range(max_retries):
                try:
                    self.vector_store.add_documents(batch)
                    print(f"[RAG] Indexed batch {i // batch_size + 1}/{(len(chunks) + batch_size - 1) // batch_size} ({len(batch)} chunks)")
                    time.sleep(1.5)  # Safe delay to prevent hitting RPM limit
                    break
                except Exception as e:
                    if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                        wait_sec = (attempt + 1) * 8
                        print(f"[RAG] Rate limit reached. Waiting {wait_sec}s before retry (attempt {attempt + 1}/{max_retries})...")
                        time.sleep(wait_sec)
                    else:
                        print(f"[RAG] Error adding batch: {e}")
                        time.sleep(3)
                        if attempt == max_retries - 1:
                            raise e

        count = self.vector_store._collection.count()
        print(f"[RAG] Indexing completed! Total vectors in collection: {count}")

    def search(self, query: str, top_k: int = config.TOP_K_RESULTS, threshold: float = config.RAG_DISTANCE_THRESHOLD) -> Tuple[List[Document], bool]:
        """
        Search for relevant context using cosine similarity / distance.
        Returns:
            Tuple[List[Document], bool]:
                - list of matching documents with metadata
                - is_found: True if relevant documents passed threshold, False if no answer found
        """
        if not self.vector_store:
            return [], False

        try:
            # Chroma returns (Document, distance) where lower distance means closer similarity
            results_with_scores = self.vector_store.similarity_search_with_score(query, k=top_k)
            
            relevant_docs = []
            for doc, score in results_with_scores:
                doc.metadata["distance"] = float(score)
                # Filter by distance threshold
                if score <= threshold:
                    relevant_docs.append(doc)
            
            is_found = len(relevant_docs) > 0
            return relevant_docs, is_found
        except Exception as e:
            print(f"[RAG] Search error: {e}")
            return [], False

    def format_context(self, docs: List[Document]) -> str:
        """Formats retrieved documents into a context block with citations."""
        if not docs:
            return "ไม่พบข้อมูลที่ตรงกันในฐานความรู้ (No matching documents found)"
            
        formatted_chunks = []
        for i, doc in enumerate(docs, 1):
            src = doc.metadata.get("source", "เอกสาร")
            page = doc.metadata.get("page", "-")
            content = doc.page_content.strip()
            formatted_chunks.append(f"--- [เอกสารอ้างอิงชุดที่ {i}: {src} หน้า {page}] ---\n{content}")
        
        return "\n\n".join(formatted_chunks)

# Singleton instance
_rag_instance: Optional[RAGService] = None

def get_rag_service() -> RAGService:
    global _rag_instance
    if _rag_instance is None:
        _rag_instance = RAGService()
    return _rag_instance

if __name__ == "__main__":
    import sys
    force = "--reindex" in sys.argv
    if force:
        rag = RAGService()
        rag.build_index(force_reload=True)
    else:
        rag = get_rag_service()

    # Test queries
    test_queries = [
        "โปรโมชั่นประกันชีวิต FWD มีสิทธิพิเศษอะไรบ้าง และผ่อน 0% ได้กี่เดือน?",
        "ประกันภัย อุ่นใจ ประจำไตรมาส 3 ให้สิทธิประโยชน์หรือของสมนาคุณอะไรบ้าง?",
        "วันนี้อากาศที่ดาวอังคารเป็นอย่างไร?" # Out of scope test for error handling
    ]
    
    print("\n" + "="*60)
    print("TESTING RAG RETRIEVAL & ERROR HANDLING")
    print("="*60)
    for q in test_queries:
        print(f"\n[QUERY]: {q}")
        docs, found = rag.search(q)
        print(f"[FOUND RELEVANT DOCS]: {found} (Count: {len(docs)})")
        if found:
            for d in docs[:2]:
                print(f" -> Source: {d.metadata.get('source')} (Page {d.metadata.get('page')}, Distance: {d.metadata.get('distance'):.4f})")
                print(f"    Excerpt: {d.page_content[:160]}...")
        else:
            print(" -> [ERROR HANDLING]: Query out of knowledge base. System correctly reported NOT FOUND.")
