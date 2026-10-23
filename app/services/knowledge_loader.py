import json
from pathlib import Path
from app.services.rag_service import index_chunks
from app.services.document_service import split_text

class KnowledgeBaseLoader:
    """
    Loads the KeepAI training knowledge base into the RAG system
    for enhanced responses and educational content
    """
    
    def __init__(self):
        self.dataset_path = Path(__file__).parent.parent.parent / "KeepAI_Training_Dataset"
        
    def load_knowledge_base(self, user_id: str = "system_knowledge"):
        """Load training knowledge base into RAG system"""
        kb_path = self.dataset_path / "knowledge_base"
        
        if not kb_path.exists():
            print("❌ Knowledge base not found")
            return False
        
        loaded_files = 0
        total_chunks = 0
        
        try:
            for md_file in kb_path.glob("*.md"):
                with open(md_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Process content into chunks
                chunks = split_text(content, chunk_size=800, overlap=100)
                
                if chunks:
                    # Index into RAG system with system user ID
                    file_id = f"kb_{md_file.stem}"
                    chunks_indexed = index_chunks(user_id, file_id, md_file.name, chunks)
                    total_chunks += chunks_indexed
                    loaded_files += 1
                    
                    print(f"✅ Loaded {md_file.name}: {chunks_indexed} chunks")
        
        except Exception as e:
            print(f"❌ Error loading knowledge base: {e}")
            return False
        
        print(f"🎓 Knowledge Base Loaded: {loaded_files} files, {total_chunks} chunks")
        return True
    
    def load_sample_training_data(self, user_id: str = "training_examples", limit: int = 50):
        """Load sample training examples as documents for better responses"""
        train_file = self.dataset_path / "datasets" / "keepai_train.jsonl"
        
        if not train_file.exists():
            print("❌ Training data not found")
            return False
        
        try:
            training_docs = []
            count = 0
            
            with open(train_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if count >= limit:
                        break
                        
                    if line.strip():
                        example = json.loads(line.strip())
                        
                        # Format as educational content
                        doc_content = f"""**Task:** {example.get('metadata', {}).get('task', 'Unknown')}
**Style:** {example.get('metadata', {}).get('style', 'Academic')}
**Input:** {example.get('input', '')}
**Response:** {example.get('output', '')}
"""
                        training_docs.append(doc_content)
                        count += 1
            
            # Split and index training examples
            all_content = "\n\n---\n\n".join(training_docs)
            chunks = split_text(all_content, chunk_size=600, overlap=80)
            
            if chunks:
                chunks_indexed = index_chunks(user_id, "training_examples", "KeepAI_Training_Examples.md", chunks)
                print(f"🤖 Training Examples Loaded: {chunks_indexed} chunks from {count} examples")
                return True
                
        except Exception as e:
            print(f"❌ Error loading training examples: {e}")
        
        return False

# Global knowledge loader
knowledge_loader = KnowledgeBaseLoader()

def initialize_knowledge_base():
    """Initialize the knowledge base on startup"""
    try:
        # Load knowledge base
        knowledge_loader.load_knowledge_base()
        
        # Load sample training examples
        knowledge_loader.load_sample_training_data(limit=30)
        
        print("🎓 KeepAI Knowledge System Initialized!")
        return True
        
    except Exception as e:
        print(f"❌ Failed to initialize knowledge base: {e}")
        return False